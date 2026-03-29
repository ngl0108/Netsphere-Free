from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from sqlalchemy.orm import Session

from app.models.approval import ApprovalRequest
from app.models.device import Device, EventLog, Issue, SystemMetric
from app.models.settings import SystemSetting
from app.models.user import User
from app.services.webhook_service import WebhookService


class ClosedLoopService:
    SETTING_ENGINE_ENABLED = "closed_loop_engine_enabled"
    SETTING_AUTO_EXECUTE_ENABLED = "closed_loop_auto_execute_enabled"
    SETTING_EXECUTE_CHANGE_ACTIONS = "closed_loop_execute_change_actions"
    SETTING_DEFAULT_COOLDOWN_SECONDS = "closed_loop_default_cooldown_seconds"
    SETTING_DEFAULT_MAX_ACTIONS_PER_HOUR = "closed_loop_default_max_actions_per_hour"
    SETTING_RULES_JSON = "closed_loop_rules_json"

    ACTION_NOTIFY = "notify"
    ACTION_OPEN_APPROVAL = "open_approval"
    ACTION_RUN_SCAN = "run_scan"
    ACTION_TEMPLATE_DEPLOY = "template_deploy"
    ACTION_CLOUD_BOOTSTRAP = "cloud_bootstrap"
    ACTION_INTENT_APPLY = "intent_apply"
    ALLOWED_ACTIONS = {
        ACTION_NOTIFY,
        ACTION_OPEN_APPROVAL,
        ACTION_RUN_SCAN,
        ACTION_TEMPLATE_DEPLOY,
        ACTION_CLOUD_BOOTSTRAP,
        ACTION_INTENT_APPLY,
    }
    ALLOWED_OPERATORS = {">", ">=", "<", "<=", "==", "!=", "contains", "in"}

    @staticmethod
    def summarize_decisions(decisions: List[Dict[str, Any]] | None) -> Dict[str, int]:
        approvals_opened = 0
        for row in list(decisions or []):
            if not isinstance(row, dict):
                continue
            try:
                if int(row.get("approval_id") or 0) > 0:
                    approvals_opened += 1
            except Exception:
                continue
        return {
            "approvals_opened": int(approvals_opened),
        }

    @staticmethod
    def emit_evaluation_summary(
        db: Session,
        *,
        result: Dict[str, Any],
        dry_run: bool,
        source: str,
        site_id: int | None = None,
        device_id: int | None = None,
        issue_id: int | None = None,
        snapshot_summary: Dict[str, Any] | None = None,
        commit: bool = True,
    ) -> Dict[str, Any]:
        decisions = list(result.get("decisions") or []) if isinstance(result, dict) else []
        decision_summary = ClosedLoopService.summarize_decisions(decisions)
        payload = {
            "status": "ok",
            "dry_run": bool(dry_run),
            "triggered": int((result or {}).get("triggered") or 0),
            "executed": int((result or {}).get("executed") or 0),
            "blocked": int((result or {}).get("blocked") or 0),
            "approvals_opened": int(decision_summary.get("approvals_opened") or 0),
            "rules_total": int((result or {}).get("rules_total") or 0),
            "auto_execute_enabled": bool((result or {}).get("auto_execute_enabled")),
            "site_id": int(site_id) if site_id is not None else None,
            "device_id": int(device_id) if device_id is not None else None,
            "issue_id": int(issue_id) if issue_id is not None else None,
            "summary": dict(snapshot_summary or {}),
            "source": str(source or "closed_loop"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        db.add(
            EventLog(
                device_id=None,
                severity="info",
                event_id="CLOSED_LOOP_EVAL_SUMMARY",
                message=json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str),
                source="ClosedLoop",
                timestamp=datetime.now(),
            )
        )
        if commit:
            db.commit()
        return payload

    @staticmethod
    def _get_setting(db: Session, key: str, default: str) -> str:
        row = db.query(SystemSetting).filter(SystemSetting.key == str(key)).first()
        if not row or row.value is None:
            return str(default)
        return str(row.value)

    @staticmethod
    def _set_setting(
        db: Session,
        key: str,
        value: str,
        *,
        category: str = "closed_loop",
        description: str | None = None,
    ) -> None:
        row = db.query(SystemSetting).filter(SystemSetting.key == str(key)).first()
        if not row:
            row = SystemSetting(
                key=str(key),
                value=str(value),
                category=str(category),
                description=str(description or key),
            )
        else:
            row.value = str(value)
            if category:
                row.category = str(category)
            if description:
                row.description = str(description)
        db.add(row)

    @staticmethod
    def _get_bool(db: Session, key: str, default: bool) -> bool:
        raw = ClosedLoopService._get_setting(db, key, "true" if default else "false").strip().lower()
        return raw in {"1", "true", "yes", "y", "on"}

    @staticmethod
    def _get_int(db: Session, key: str, default: int, *, min_v: int, max_v: int) -> int:
        try:
            val = int(float(ClosedLoopService._get_setting(db, key, str(default)).strip()))
        except Exception:
            val = int(default)
        return max(min_v, min(max_v, int(val)))

    @staticmethod
    def engine_enabled(db: Session) -> bool:
        return ClosedLoopService._get_bool(db, ClosedLoopService.SETTING_ENGINE_ENABLED, False)

    @staticmethod
    def auto_execute_enabled(db: Session) -> bool:
        return ClosedLoopService._get_bool(db, ClosedLoopService.SETTING_AUTO_EXECUTE_ENABLED, False)

    @staticmethod
    def execute_change_actions_enabled(db: Session) -> bool:
        return ClosedLoopService._get_bool(db, ClosedLoopService.SETTING_EXECUTE_CHANGE_ACTIONS, False)

    @staticmethod
    def default_cooldown_seconds(db: Session) -> int:
        return ClosedLoopService._get_int(
            db,
            ClosedLoopService.SETTING_DEFAULT_COOLDOWN_SECONDS,
            300,
            min_v=5,
            max_v=86400,
        )

    @staticmethod
    def default_max_actions_per_hour(db: Session) -> int:
        return ClosedLoopService._get_int(
            db,
            ClosedLoopService.SETTING_DEFAULT_MAX_ACTIONS_PER_HOUR,
            12,
            min_v=1,
            max_v=1000,
        )

    @staticmethod
    def _hour_key(now: datetime) -> str:
        return now.astimezone(timezone.utc).strftime("%Y%m%d%H")

    @staticmethod
    def _state_key(rule_id: str) -> str:
        return f"closed_loop_rule_state:{str(rule_id).strip()}"

    @staticmethod
    def _load_state(db: Session, rule_id: str) -> Dict[str, Any]:
        row = db.query(SystemSetting).filter(SystemSetting.key == ClosedLoopService._state_key(rule_id)).first()
        if not row or not row.value:
            return {"last_action_at": None, "hour_bucket": None, "hour_count": 0}
        try:
            parsed = json.loads(str(row.value))
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
        return {"last_action_at": None, "hour_bucket": None, "hour_count": 0}

    @staticmethod
    def _save_state(db: Session, rule_id: str, state: Dict[str, Any]) -> None:
        ClosedLoopService._set_setting(
            db,
            ClosedLoopService._state_key(rule_id),
            json.dumps(state, ensure_ascii=False, separators=(",", ":"), default=str),
            category="closed_loop",
            description=f"closed-loop runtime state for {rule_id}",
        )

    @staticmethod
    def _read_path(signals: Dict[str, Any], path: str) -> Tuple[Any, bool]:
        current: Any = signals
        for part in [p for p in str(path or "").split(".") if p]:
            if isinstance(current, dict):
                if part not in current:
                    return None, False
                current = current.get(part)
                continue
            if isinstance(current, list) and part.isdigit():
                idx = int(part)
                if idx < 0 or idx >= len(current):
                    return None, False
                current = current[idx]
                continue
            return None, False
        return current, True

    @staticmethod
    def _to_float(value: Any) -> float:
        if isinstance(value, bool):
            return 1.0 if value else 0.0
        return float(value)

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except Exception:
            return float(default)

    @staticmethod
    def _eval_condition(lhs: Any, operator: str, rhs: Any) -> bool:
        op = str(operator or "").strip().lower()
        if op in {">", ">=", "<", "<=", "==", "!="}:
            try:
                l_num = ClosedLoopService._to_float(lhs)
                r_num = ClosedLoopService._to_float(rhs)
            except Exception:
                l_num = None
                r_num = None

            if op == "==":
                return lhs == rhs if l_num is None or r_num is None else l_num == r_num
            if op == "!=":
                return lhs != rhs if l_num is None or r_num is None else l_num != r_num
            if l_num is None or r_num is None:
                return False
            if op == ">":
                return l_num > r_num
            if op == ">=":
                return l_num >= r_num
            if op == "<":
                return l_num < r_num
            if op == "<=":
                return l_num <= r_num

        if op == "contains":
            if isinstance(lhs, str):
                return str(rhs) in lhs
            if isinstance(lhs, list):
                return rhs in lhs
            if isinstance(lhs, dict):
                return str(rhs) in lhs
            return False

        if op == "in":
            if isinstance(rhs, (list, tuple, set)):
                return lhs in rhs
            if isinstance(rhs, str):
                return str(lhs) in rhs
            return False

        return False

    @staticmethod
    def _normalize_rule(raw: Dict[str, Any], index: int) -> Tuple[Dict[str, Any], List[str]]:
        errors: List[str] = []
        if not isinstance(raw, dict):
            return {}, [f"rules[{index}] must be object"]

        rule_id = str(raw.get("id") or "").strip()
        if not rule_id:
            rule_id = f"rule-{index}"
        name = str(raw.get("name") or "").strip() or rule_id
        enabled = bool(raw.get("enabled", True))

        condition = raw.get("condition") if isinstance(raw.get("condition"), dict) else {}
        path = str(condition.get("path") or "").strip()
        operator = str(condition.get("operator") or "").strip()
        value = condition.get("value")

        if not path:
            errors.append(f"rules[{index}] condition.path is required")
        if operator not in ClosedLoopService.ALLOWED_OPERATORS:
            errors.append(
                f"rules[{index}] condition.operator must be one of {sorted(list(ClosedLoopService.ALLOWED_OPERATORS))}"
            )

        action = raw.get("action") if isinstance(raw.get("action"), dict) else {}
        action_type = str(action.get("type") or "").strip().lower()
        if action_type not in ClosedLoopService.ALLOWED_ACTIONS:
            errors.append(
                f"rules[{index}] action.type must be one of {sorted(list(ClosedLoopService.ALLOWED_ACTIONS))}"
            )

        cooldown_seconds = raw.get("cooldown_seconds")
        try:
            cooldown_seconds = int(cooldown_seconds) if cooldown_seconds is not None else None
        except Exception:
            errors.append(f"rules[{index}] cooldown_seconds must be integer")
            cooldown_seconds = None
        if cooldown_seconds is not None and cooldown_seconds < 0:
            errors.append(f"rules[{index}] cooldown_seconds must be >= 0")

        max_actions_per_hour = raw.get("max_actions_per_hour")
        try:
            max_actions_per_hour = int(max_actions_per_hour) if max_actions_per_hour is not None else None
        except Exception:
            errors.append(f"rules[{index}] max_actions_per_hour must be integer")
            max_actions_per_hour = None
        if max_actions_per_hour is not None and max_actions_per_hour < 1:
            errors.append(f"rules[{index}] max_actions_per_hour must be >= 1")

        normalized = {
            "id": rule_id,
            "name": name,
            "enabled": enabled,
            "source": str(raw.get("source") or "any").strip().lower() or "any",
            "condition": {"path": path, "operator": operator, "value": value},
            "action": {
                "type": action_type,
                "title": str(action.get("title") or "").strip() or name,
                "message": str(action.get("message") or "").strip() or f"Closed-loop action by rule {name}",
                "payload": action.get("payload") if isinstance(action.get("payload"), dict) else {},
            },
            "cooldown_seconds": cooldown_seconds,
            "max_actions_per_hour": max_actions_per_hour,
            "require_approval": bool(raw.get("require_approval", True)),
            "labels": [str(x).strip() for x in list(raw.get("labels") or []) if str(x).strip()],
        }
        return normalized, errors

    @staticmethod
    def _stable_json(value: Any) -> str:
        try:
            return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
        except Exception:
            return str(value)

    @staticmethod
    def _lint_normalized_rules(rules: List[Dict[str, Any]]) -> Dict[str, Any]:
        conflicts: List[Dict[str, Any]] = []
        warnings: List[Dict[str, Any]] = []
        enabled_rules = [r for r in list(rules or []) if bool(r.get("enabled", True))]

        by_condition: Dict[Tuple[str, str, str, str], List[Dict[str, Any]]] = {}
        by_semantic: Dict[Tuple[str, str, str, str, str, str, bool], List[Dict[str, Any]]] = {}

        for rule in enabled_rules:
            cond = rule.get("condition") if isinstance(rule.get("condition"), dict) else {}
            action = rule.get("action") if isinstance(rule.get("action"), dict) else {}
            payload = action.get("payload") if isinstance(action.get("payload"), dict) else {}

            source = str(rule.get("source") or "any").strip().lower() or "any"
            path = str(cond.get("path") or "").strip()
            operator = str(cond.get("operator") or "").strip()
            value_sig = ClosedLoopService._stable_json(cond.get("value"))
            action_type = str(action.get("type") or "").strip().lower()
            action_payload_sig = ClosedLoopService._stable_json(payload)
            require_approval = bool(rule.get("require_approval", True))

            rule_meta = {
                "id": str(rule.get("id") or ""),
                "name": str(rule.get("name") or ""),
                "source": source,
                "condition": {
                    "path": path,
                    "operator": operator,
                    "value": cond.get("value"),
                },
                "action": {
                    "type": action_type,
                    "payload": payload,
                },
                "require_approval": require_approval,
            }

            cond_key = (source, path, operator, value_sig)
            sem_key = cond_key + (action_type, action_payload_sig, require_approval)
            by_condition.setdefault(cond_key, []).append(rule_meta)
            by_semantic.setdefault(sem_key, []).append(rule_meta)

        for entries in by_condition.values():
            if len(entries) < 2:
                continue
            action_keys = {
                (
                    str((row.get("action") or {}).get("type") or "").strip().lower(),
                    ClosedLoopService._stable_json((row.get("action") or {}).get("payload") or {}),
                    bool(row.get("require_approval", True)),
                )
                for row in entries
            }
            if len(action_keys) < 2:
                continue

            ids = [str(row.get("id") or "") for row in entries]
            conflicts.append(
                {
                    "type": "condition_action_conflict",
                    "message": "Enabled rules share the same condition but define different actions.",
                    "rule_ids": ids,
                    "condition": (entries[0].get("condition") or {}),
                    "actions": [
                        {
                            "rule_id": str(row.get("id") or ""),
                            "action_type": str((row.get("action") or {}).get("type") or ""),
                            "require_approval": bool(row.get("require_approval", True)),
                        }
                        for row in entries
                    ],
                }
            )

        for entries in by_semantic.values():
            if len(entries) < 2:
                continue
            warnings.append(
                {
                    "type": "redundant_enabled_rules",
                    "message": "Multiple enabled rules have identical condition and action.",
                    "rule_ids": [str(row.get("id") or "") for row in entries],
                    "condition": (entries[0].get("condition") or {}),
                    "action": (entries[0].get("action") or {}),
                }
            )

        return {
            "rules_total": len(list(rules or [])),
            "rules_enabled": len(enabled_rules),
            "conflicts_count": len(conflicts),
            "warnings_count": len(warnings),
            "conflicts": conflicts,
            "warnings": warnings,
        }

    @staticmethod
    def get_rules(db: Session) -> List[Dict[str, Any]]:
        raw = ClosedLoopService._get_setting(db, ClosedLoopService.SETTING_RULES_JSON, "[]").strip()
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
        except Exception:
            return []
        if not isinstance(parsed, list):
            return []

        out: List[Dict[str, Any]] = []
        for idx, item in enumerate(parsed, start=1):
            normalized, errors = ClosedLoopService._normalize_rule(item, idx)
            if errors:
                continue
            out.append(normalized)
        return out

    @staticmethod
    def lint_saved_rules(db: Session) -> Dict[str, Any]:
        return ClosedLoopService._lint_normalized_rules(ClosedLoopService.get_rules(db))

    @staticmethod
    def lint_rules(rules: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not isinstance(rules, list):
            raise ValueError("rules must be list")
        normalized_rules: List[Dict[str, Any]] = []
        errors: List[str] = []
        seen_ids = set()
        for idx, item in enumerate(rules, start=1):
            normalized, row_errors = ClosedLoopService._normalize_rule(item, idx)
            if row_errors:
                errors.extend(row_errors)
                continue
            rid = normalized["id"]
            if rid in seen_ids:
                errors.append(f"duplicate rule id: {rid}")
                continue
            seen_ids.add(rid)
            normalized_rules.append(normalized)

        if errors:
            raise ValueError("; ".join(errors))
        return ClosedLoopService._lint_normalized_rules(normalized_rules)

    @staticmethod
    def save_rules(db: Session, rules: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not isinstance(rules, list):
            raise ValueError("rules must be list")
        normalized_rules: List[Dict[str, Any]] = []
        errors: List[str] = []
        seen_ids = set()
        for idx, item in enumerate(rules, start=1):
            normalized, row_errors = ClosedLoopService._normalize_rule(item, idx)
            if row_errors:
                errors.extend(row_errors)
                continue
            rid = normalized["id"]
            if rid in seen_ids:
                errors.append(f"duplicate rule id: {rid}")
                continue
            seen_ids.add(rid)
            normalized_rules.append(normalized)

        if errors:
            raise ValueError("; ".join(errors))
        lint = ClosedLoopService._lint_normalized_rules(normalized_rules)

        ClosedLoopService._set_setting(
            db,
            ClosedLoopService.SETTING_RULES_JSON,
            json.dumps(normalized_rules, ensure_ascii=False, separators=(",", ":"), default=str),
            category="closed_loop",
            description="Closed-loop rule definitions",
        )
        db.commit()
        return {"saved": len(normalized_rules), "rules": normalized_rules, "lint": lint}

    @staticmethod
    def status(db: Session) -> Dict[str, Any]:
        rules = ClosedLoopService.get_rules(db)
        lint = ClosedLoopService._lint_normalized_rules(rules)
        return {
            "engine_enabled": ClosedLoopService.engine_enabled(db),
            "auto_execute_enabled": ClosedLoopService.auto_execute_enabled(db),
            "execute_change_actions_enabled": ClosedLoopService.execute_change_actions_enabled(db),
            "default_cooldown_seconds": ClosedLoopService.default_cooldown_seconds(db),
            "default_max_actions_per_hour": ClosedLoopService.default_max_actions_per_hour(db),
            "rules_total": len(rules),
            "rules_enabled": sum(1 for r in rules if bool(r.get("enabled", True))),
            "rules_lint": {
                "conflicts_count": int(lint.get("conflicts_count") or 0),
                "warnings_count": int(lint.get("warnings_count") or 0),
                "top_conflicts": list(lint.get("conflicts") or [])[:3],
                "top_warnings": list(lint.get("warnings") or [])[:3],
            },
            "allowed_operators": sorted(list(ClosedLoopService.ALLOWED_OPERATORS)),
            "allowed_actions": sorted(list(ClosedLoopService.ALLOWED_ACTIONS)),
        }

    @staticmethod
    def build_signal_snapshot(
        db: Session,
        *,
        site_id: int | None = None,
        device_id: int | None = None,
    ) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        query = db.query(Device.id, Device.name, Device.site_id, Device.status).order_by(Device.id.asc())
        if site_id is not None:
            query = query.filter(Device.site_id == int(site_id))
        if device_id is not None:
            query = query.filter(Device.id == int(device_id))

        devices = query.all()
        device_rows: List[Dict[str, Any]] = []
        device_ids: List[int] = []
        for item in devices:
            did = int(getattr(item, "id", 0) or 0)
            if did <= 0:
                continue
            device_rows.append(
                {
                    "id": did,
                    "name": str(getattr(item, "name", "") or f"device-{did}"),
                    "site_id": int(getattr(item, "site_id", 0) or 0) or None,
                    "status": str(getattr(item, "status", "") or "unknown"),
                }
            )
            device_ids.append(did)

        latest_metric_by_device: Dict[int, Any] = {}
        if device_ids:
            metric_rows = (
                db.query(
                    SystemMetric.device_id,
                    SystemMetric.cpu_usage,
                    SystemMetric.memory_usage,
                    SystemMetric.traffic_in,
                    SystemMetric.traffic_out,
                    SystemMetric.timestamp,
                )
                .filter(SystemMetric.device_id.in_(device_ids))
                .order_by(SystemMetric.device_id.asc(), SystemMetric.timestamp.desc())
                .all()
            )
            for row in metric_rows:
                did = int(getattr(row, "device_id", 0) or 0)
                if did > 0 and did not in latest_metric_by_device:
                    latest_metric_by_device[did] = row

        devices_out: Dict[str, Any] = {}
        online_count = 0
        cpu_values: List[float] = []
        memory_values: List[float] = []
        traffic_in_values: List[float] = []
        traffic_out_values: List[float] = []

        for item in device_rows:
            did = int(item["id"])
            status = str(item["status"] or "unknown").strip().lower()
            if status == "online":
                online_count += 1

            metric = latest_metric_by_device.get(did)
            metrics_payload: Dict[str, Any] = {}
            if metric is not None:
                cpu = ClosedLoopService._safe_float(getattr(metric, "cpu_usage", 0.0), 0.0)
                memory = ClosedLoopService._safe_float(getattr(metric, "memory_usage", 0.0), 0.0)
                traffic_in = ClosedLoopService._safe_float(getattr(metric, "traffic_in", 0.0), 0.0)
                traffic_out = ClosedLoopService._safe_float(getattr(metric, "traffic_out", 0.0), 0.0)
                cpu_values.append(cpu)
                memory_values.append(memory)
                traffic_in_values.append(traffic_in)
                traffic_out_values.append(traffic_out)
                metrics_payload = {
                    "cpu_usage": cpu,
                    "memory_usage": memory,
                    "traffic_in": traffic_in,
                    "traffic_out": traffic_out,
                    "timestamp": str(getattr(metric, "timestamp", "") or ""),
                }

            devices_out[str(did)] = {
                "id": did,
                "name": item["name"],
                "site_id": item["site_id"],
                "status": status,
                "metrics": metrics_payload,
            }

        total = len(device_rows)
        summary = {
            "devices_total": total,
            "devices_online": int(online_count),
            "devices_offline": int(max(0, total - online_count)),
            "cpu_avg": round((sum(cpu_values) / len(cpu_values)), 2) if cpu_values else 0.0,
            "memory_avg": round((sum(memory_values) / len(memory_values)), 2) if memory_values else 0.0,
            "traffic_in_total": round(sum(traffic_in_values), 2) if traffic_in_values else 0.0,
            "traffic_out_total": round(sum(traffic_out_values), 2) if traffic_out_values else 0.0,
        }
        return {
            "generated_at": now.isoformat(),
            "filters": {"site_id": site_id, "device_id": device_id},
            "summary": summary,
            "devices": devices_out,
        }

    @staticmethod
    def _action_requires_direct_execution(action_type: str) -> bool:
        return str(action_type or "").strip().lower() in {
            ClosedLoopService.ACTION_RUN_SCAN,
            ClosedLoopService.ACTION_TEMPLATE_DEPLOY,
            ClosedLoopService.ACTION_CLOUD_BOOTSTRAP,
            ClosedLoopService.ACTION_INTENT_APPLY,
        }

    @staticmethod
    def _preview_status_priority(status: str) -> int:
        normalized = str(status or "").strip().lower()
        if normalized == "ready":
            return 0
        if normalized == "approval_required":
            return 1
        if normalized in {"blocked_cooldown", "blocked_rate_limit", "notify_not_configured"}:
            return 2
        if normalized == "auto_execute_disabled":
            return 3
        return 4

    @staticmethod
    def _as_utc(value: Any) -> datetime | None:
        if not isinstance(value, datetime):
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _metric_field(metric: Any, key: str, default: float = 0.0) -> float:
        try:
            value = metric.get(key, default) if isinstance(metric, dict) else getattr(metric, key, default)
        except Exception:
            value = default
        return ClosedLoopService._safe_float(value, default)

    @staticmethod
    def _metric_timestamp(metric: Any) -> str:
        try:
            value = metric.get("timestamp") if isinstance(metric, dict) else getattr(metric, "timestamp", "")
        except Exception:
            value = ""
        return str(value or "")

    @staticmethod
    def build_issue_signal_snapshot(
        issue: Issue,
        *,
        latest_metric: Any = None,
        issue_stats: Dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> Dict[str, Any]:
        now_dt = ClosedLoopService._as_utc(now) or datetime.now(timezone.utc)
        title = str(getattr(issue, "title", "") or "")
        description = str(getattr(issue, "description", "") or "")
        title_lower = title.lower()
        description_lower = description.lower()
        category = str(getattr(issue, "category", "system") or "system").strip().lower() or "system"
        severity = str(getattr(issue, "severity", "info") or "info").strip().lower() or "info"
        status = str(getattr(issue, "status", "active") or "active").strip().lower() or "active"
        device_id = int(getattr(issue, "device_id", 0) or 0) or None
        device = getattr(issue, "device", None)

        created_at = ClosedLoopService._as_utc(getattr(issue, "created_at", None))
        age_seconds = max(0, int((now_dt - created_at).total_seconds())) if created_at is not None else 0

        is_bgp = title_lower.startswith("bgp neighbor down")
        is_ospf = title_lower.startswith("ospf neighbor down")
        is_routing = bool(is_bgp or is_ospf or "routing" in title_lower)
        is_interface = bool(
            title_lower.startswith("interface errors")
            or title_lower.startswith("interface drops")
            or ("interface" in title_lower and "down" in title_lower)
        )
        is_link = bool("link" in title_lower or ("updown" in description_lower and "down" in description_lower))
        is_device_down = bool("device unreachable" in title_lower or "unreachable" in description_lower)
        is_traffic_drop = title_lower.startswith("dynamic traffic drop")
        is_cpu_spike = title_lower.startswith("dynamic cpu spike")
        is_memory_spike = title_lower.startswith("dynamic memory spike")
        is_root_cause = title_lower.startswith("root cause suspected")
        is_config_drift = "config drift" in title_lower
        is_config_change = "configuration changed" in title_lower
        is_hardware = any(token in title_lower for token in ["fan failure", "temperature critical", "power supply failure"])

        issue_kind = "generic"
        if is_root_cause:
            issue_kind = "root_cause"
        elif is_config_drift:
            issue_kind = "config_drift"
        elif is_config_change:
            issue_kind = "config_change"
        elif is_bgp:
            issue_kind = "bgp"
        elif is_ospf:
            issue_kind = "ospf"
        elif is_interface:
            issue_kind = "interface_health"
        elif is_link:
            issue_kind = "link_state"
        elif is_device_down:
            issue_kind = "device_down"
        elif is_traffic_drop:
            issue_kind = "traffic_drop"
        elif is_cpu_spike:
            issue_kind = "cpu_spike"
        elif is_memory_spike:
            issue_kind = "memory_spike"
        elif is_hardware:
            issue_kind = "hardware"

        signals = {
            "is_critical": severity == "critical",
            "is_warning": severity == "warning",
            "is_info": severity == "info",
            "is_routing": is_routing,
            "is_bgp": is_bgp,
            "is_ospf": is_ospf,
            "is_interface": is_interface,
            "is_link": is_link,
            "is_device_down": is_device_down,
            "is_performance": category == "performance" or bool(is_cpu_spike or is_memory_spike or is_traffic_drop),
            "is_config": category == "config" or bool(is_config_drift or is_config_change),
            "is_security": category == "security",
            "is_system": category == "system",
            "is_root_cause": is_root_cause,
            "is_hardware": is_hardware,
        }
        match_paths = [f"issue.signals.{key}" for key, value in signals.items() if bool(value)]
        match_paths.extend([
            "issue.severity",
            "issue.category",
            "issue.kind",
        ])

        stats = issue_stats if isinstance(issue_stats, dict) else {}
        by_device = stats.get("by_device") if isinstance(stats.get("by_device"), dict) else {}
        by_category = stats.get("by_category") if isinstance(stats.get("by_category"), dict) else {}
        by_severity = stats.get("by_severity") if isinstance(stats.get("by_severity"), dict) else {}
        active_counts = {
            "total": int(stats.get("total") or 0),
            "device": int(by_device.get(str(device_id)) or 0) if device_id is not None else 0,
            "category": int(by_category.get(category) or 0),
            "severity": int(by_severity.get(severity) or 0),
        }

        metrics_payload: Dict[str, Any] = {}
        if latest_metric is not None:
            metrics_payload = {
                "cpu_usage": ClosedLoopService._metric_field(latest_metric, "cpu_usage"),
                "memory_usage": ClosedLoopService._metric_field(latest_metric, "memory_usage"),
                "traffic_in": ClosedLoopService._metric_field(latest_metric, "traffic_in"),
                "traffic_out": ClosedLoopService._metric_field(latest_metric, "traffic_out"),
                "timestamp": ClosedLoopService._metric_timestamp(latest_metric),
            }

        device_payload = {
            "id": device_id,
            "name": str(getattr(device, "name", "") or ""),
            "hostname": str(getattr(device, "hostname", "") or ""),
            "status": str(getattr(device, "status", "") or "unknown").strip().lower() or "unknown",
            "site_id": int(getattr(device, "site_id", 0) or 0) or None,
            "device_type": str(getattr(device, "device_type", "") or ""),
            "model": str(getattr(device, "model", "") or ""),
            "os_version": str(getattr(device, "os_version", "") or ""),
            "metrics": metrics_payload,
        }

        return {
            "generated_at": now_dt.isoformat(),
            "summary": {
                "issue_active_total": int(active_counts["total"]),
                "issue_device_active": int(active_counts["device"]),
                "issue_category_active": int(active_counts["category"]),
                "issue_severity_active": int(active_counts["severity"]),
            },
            "issue": {
                "id": int(getattr(issue, "id", 0) or 0),
                "title": title,
                "description": description,
                "severity": severity,
                "category": category,
                "status": status,
                "is_read": bool(getattr(issue, "is_read", False)),
                "device_id": device_id,
                "kind": issue_kind,
                "age_seconds": int(age_seconds),
                "title_lower": title_lower,
                "signals": signals,
                "match_paths": match_paths,
                "active_counts": active_counts,
                "device": device_payload,
            },
        }

    @staticmethod
    def preview_issue_automation(
        db: Session,
        issue: Issue,
        *,
        latest_metric: Any = None,
        issue_stats: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        rules = ClosedLoopService.get_rules(db)
        engine_enabled = ClosedLoopService.engine_enabled(db)
        auto_exec = ClosedLoopService.auto_execute_enabled(db)
        execute_change_actions = ClosedLoopService.execute_change_actions_enabled(db)
        snapshot = ClosedLoopService.build_issue_signal_snapshot(
            issue,
            latest_metric=latest_metric,
            issue_stats=issue_stats,
        )

        if not engine_enabled:
            return {
                "engine_enabled": False,
                "auto_execute_enabled": bool(auto_exec),
                "direct_change_actions_enabled": bool(execute_change_actions),
                "rules_total": len(rules),
                "matched_rules": 0,
                "ready_rules": 0,
                "approval_rules": 0,
                "blocked_rules": 0,
                "disabled_rules": 0,
                "can_run": False,
                "primary_status": "engine_disabled",
                "next_action": "Enable closed-loop engine before using alert automation.",
                "primary_action": None,
                "decisions": [],
                "snapshot": snapshot,
            }

        default_cooldown = ClosedLoopService.default_cooldown_seconds(db)
        default_limit = ClosedLoopService.default_max_actions_per_hour(db)
        webhook_configured = WebhookService.enabled(db) and bool(WebhookService._url(db))

        matched = 0
        ready = 0
        approval = 0
        blocked = 0
        disabled = 0
        now = datetime.now(timezone.utc)
        now_hour = ClosedLoopService._hour_key(now)
        decisions: List[Dict[str, Any]] = []

        for rule in rules:
            if not bool(rule.get("enabled", True)):
                continue

            condition = rule.get("condition") if isinstance(rule.get("condition"), dict) else {}
            signal_value, exists = ClosedLoopService._read_path(snapshot, str(condition.get("path") or ""))
            if not exists:
                continue
            if not ClosedLoopService._eval_condition(signal_value, str(condition.get("operator") or ""), condition.get("value")):
                continue

            matched += 1
            action = rule.get("action") if isinstance(rule.get("action"), dict) else {}
            action_type = str(action.get("type") or "").strip().lower()
            requires_approval = bool(rule.get("require_approval", True))
            cooldown = int(rule.get("cooldown_seconds")) if rule.get("cooldown_seconds") is not None else default_cooldown
            rate_limit = (
                int(rule.get("max_actions_per_hour"))
                if rule.get("max_actions_per_hour") is not None
                else default_limit
            )

            state = ClosedLoopService._load_state(db, str(rule.get("id")))
            hour_bucket = str(state.get("hour_bucket") or "")
            hour_count = int(state.get("hour_count") or 0)
            if hour_bucket != now_hour:
                hour_bucket = now_hour
                hour_count = 0

            cooldown_blocked = False
            last_action_at = state.get("last_action_at")
            if last_action_at:
                try:
                    last_dt = datetime.fromisoformat(str(last_action_at))
                    last_dt = ClosedLoopService._as_utc(last_dt) or now
                    cooldown_blocked = (now - last_dt).total_seconds() < float(cooldown)
                except Exception:
                    cooldown_blocked = False
            rate_blocked = hour_count >= rate_limit

            decision = {
                "rule_id": rule.get("id"),
                "rule_name": rule.get("name"),
                "path": condition.get("path"),
                "signal_value": signal_value,
                "action_type": action_type,
                "action_title": str(action.get("title") or rule.get("name") or "").strip(),
                "requires_approval": requires_approval,
                "direct_execution_enabled": bool(execute_change_actions),
            }

            if cooldown_blocked:
                blocked += 1
                decision.update(
                    {
                        "status": "blocked_cooldown",
                        "execution_mode": "blocked",
                        "next_action": "Wait for the cooldown window to expire.",
                        "actionable": False,
                        "cooldown_seconds": int(cooldown),
                    }
                )
                decisions.append(decision)
                continue

            if rate_blocked:
                blocked += 1
                decision.update(
                    {
                        "status": "blocked_rate_limit",
                        "execution_mode": "blocked",
                        "next_action": "Hourly action rate limit reached for this rule.",
                        "actionable": False,
                        "max_actions_per_hour": int(rate_limit),
                    }
                )
                decisions.append(decision)
                continue

            if not auto_exec:
                disabled += 1
                decision.update(
                    {
                        "status": "auto_execute_disabled",
                        "execution_mode": "manual_review",
                        "next_action": "Enable auto execute before running alert automation.",
                        "actionable": False,
                    }
                )
                decisions.append(decision)
                continue

            if requires_approval or action_type == ClosedLoopService.ACTION_OPEN_APPROVAL:
                approval += 1
                decision.update(
                    {
                        "status": "approval_required",
                        "execution_mode": "approval",
                        "next_action": "Running this alert automation will open an approval request.",
                        "actionable": True,
                    }
                )
                decisions.append(decision)
                continue

            if action_type == ClosedLoopService.ACTION_NOTIFY and not webhook_configured:
                blocked += 1
                decision.update(
                    {
                        "status": "notify_not_configured",
                        "execution_mode": "blocked",
                        "next_action": "Configure webhook delivery before using notify actions.",
                        "actionable": False,
                    }
                )
                decisions.append(decision)
                continue

            if ClosedLoopService._action_requires_direct_execution(action_type) and not execute_change_actions:
                approval += 1
                decision.update(
                    {
                        "status": "approval_required",
                        "execution_mode": "approval",
                        "next_action": "Direct change execution is disabled, so this alert will go through approval.",
                        "actionable": True,
                        "direct_execution_enabled": False,
                    }
                )
                decisions.append(decision)
                continue

            ready += 1
            decision.update(
                {
                    "status": "ready",
                    "execution_mode": "notify" if action_type == ClosedLoopService.ACTION_NOTIFY else "direct_execute",
                    "next_action": "Ready to execute from this alert.",
                    "actionable": True,
                }
            )
            decisions.append(decision)

        decisions.sort(
            key=lambda row: (
                ClosedLoopService._preview_status_priority(str(row.get("status") or "")),
                str(row.get("rule_name") or ""),
            )
        )

        primary_status = "no_match"
        if ready > 0:
            primary_status = "auto_ready"
        elif approval > 0:
            primary_status = "approval_required"
        elif blocked > 0:
            primary_status = "blocked"
        elif disabled > 0:
            primary_status = "auto_execute_disabled"

        primary_decision = decisions[0] if decisions else None
        return {
            "engine_enabled": True,
            "auto_execute_enabled": bool(auto_exec),
            "direct_change_actions_enabled": bool(execute_change_actions),
            "rules_total": len(rules),
            "matched_rules": int(matched),
            "ready_rules": int(ready),
            "approval_rules": int(approval),
            "blocked_rules": int(blocked),
            "disabled_rules": int(disabled),
            "can_run": primary_status in {"auto_ready", "approval_required"},
            "primary_status": primary_status,
            "next_action": str((primary_decision or {}).get("next_action") or "No matching alert automation rule."),
            "primary_action": (
                {
                    "rule_id": primary_decision.get("rule_id"),
                    "rule_name": primary_decision.get("rule_name"),
                    "action_type": primary_decision.get("action_type"),
                    "action_title": primary_decision.get("action_title"),
                    "status": primary_decision.get("status"),
                }
                if isinstance(primary_decision, dict)
                else None
            ),
            "decisions": decisions,
            "snapshot": snapshot,
        }

    @staticmethod
    def _open_approval(
        db: Session,
        actor_user: User,
        *,
        rule: Dict[str, Any],
        signal_value: Any,
        reason: str,
        context: Dict[str, Any] | None = None,
    ) -> int:
        payload = {
            "source": "closed_loop",
            "rule_id": rule.get("id"),
            "action": rule.get("action"),
            "reason": reason,
            "signal_value": signal_value,
        }
        if isinstance(context, dict) and context:
            payload["context"] = context
        req = ApprovalRequest(
            title=f"[ClosedLoop] {rule.get('name')}",
            description=f"Auto-generated approval from closed-loop rule {rule.get('id')}",
            request_type="closed_loop_action",
            payload=payload,
            requester_id=int(getattr(actor_user, "id", 0) or 0),
            status="pending",
            requester_comment=f"Closed-loop triggered: {reason}",
        )
        db.add(req)
        db.flush()
        return int(req.id)

    @staticmethod
    def _execute_run_scan_action(
        db: Session,
        *,
        rule: Dict[str, Any],
        action: Dict[str, Any],
    ) -> Dict[str, Any]:
        payload = action.get("payload") if isinstance(action.get("payload"), dict) else {}
        cidr = str(payload.get("cidr") or "").strip()
        if not cidr:
            raise ValueError("run_scan action requires payload.cidr")

        site_id = payload.get("site_id")
        if site_id is not None and str(site_id).strip() != "":
            site_id = int(site_id)
        else:
            site_id = None

        snmp_profile_id = payload.get("snmp_profile_id")
        if snmp_profile_id is not None and str(snmp_profile_id).strip() != "":
            snmp_profile_id = int(snmp_profile_id)
        else:
            snmp_profile_id = None

        community = str(
            payload.get("community")
            or ClosedLoopService._get_setting(db, "default_snmp_community", "public")
            or "public"
        ).strip() or "public"
        snmp_version = str(payload.get("snmp_version") or "v2c").strip() or "v2c"
        try:
            snmp_port = int(payload.get("snmp_port") if payload.get("snmp_port") is not None else 161)
        except Exception:
            snmp_port = 161
        snmp_port = max(1, min(65535, int(snmp_port)))

        from app.services.discovery_service import DiscoveryService
        from app.tasks.discovery_dispatch import dispatch_discovery_scan

        service = DiscoveryService(db)
        job = service.create_scan_job(
            cidr=cidr,
            community=community,
            site_id=site_id,
            snmp_profile_id=snmp_profile_id,
            snmp_version=snmp_version,
            snmp_port=snmp_port,
        )
        idem_seed = str(payload.get("idempotency_key") or "").strip()
        if idem_seed:
            idempotency_key = f"closed-loop:{rule.get('id')}:run-scan:{idem_seed}"
        else:
            idempotency_key = f"closed-loop:{rule.get('id')}:run-scan:{int(job.id)}"
        dispatch = dispatch_discovery_scan(int(job.id), idempotency_key=idempotency_key)
        status = str(dispatch.get("status") or "").strip().lower()
        if status not in {"enqueued", "skipped"}:
            raise RuntimeError(f"discovery dispatch failed: {dispatch.get('reason') or status or 'unknown'}")
        return {
            "mode": "run_scan_dispatched",
            "job_id": int(job.id),
            "cidr": cidr,
            "site_id": site_id,
            "dispatch": dispatch,
        }

    @staticmethod
    def _execute_template_deploy_action(
        db: Session,
        *,
        rule: Dict[str, Any],
        action: Dict[str, Any],
        actor_user: User,
    ) -> Dict[str, Any]:
        payload = action.get("payload") if isinstance(action.get("payload"), dict) else {}
        try:
            template_id = int(payload.get("template_id"))
        except Exception:
            raise ValueError("template_deploy action requires payload.template_id")
        if template_id <= 0:
            raise ValueError("template_deploy action requires payload.template_id > 0")

        raw_device_ids = payload.get("device_ids")
        if not isinstance(raw_device_ids, list) or not raw_device_ids:
            raise ValueError("template_deploy action requires non-empty payload.device_ids list")
        device_ids: List[int] = []
        for v in raw_device_ids:
            try:
                did = int(v)
            except Exception:
                continue
            if did > 0 and did not in device_ids:
                device_ids.append(did)
        if not device_ids:
            raise ValueError("template_deploy action payload.device_ids has no valid positive integers")

        variables = payload.get("variables") if isinstance(payload.get("variables"), dict) else {}
        pre_check_commands = [str(c).strip() for c in list(payload.get("pre_check_commands") or []) if str(c).strip()]
        post_check_commands = [str(c).strip() for c in list(payload.get("post_check_commands") or []) if str(c).strip()]
        try:
            canary_count = max(0, int(payload.get("canary_count") if payload.get("canary_count") is not None else 0))
        except Exception:
            canary_count = 0
        try:
            wave_size = max(0, int(payload.get("wave_size") if payload.get("wave_size") is not None else 0))
        except Exception:
            wave_size = 0
        try:
            inter_wave_delay_seconds = float(
                payload.get("inter_wave_delay_seconds") if payload.get("inter_wave_delay_seconds") is not None else 0.0
            )
        except Exception:
            inter_wave_delay_seconds = 0.0
        inter_wave_delay_seconds = max(0.0, min(300.0, float(inter_wave_delay_seconds)))

        approval_id = payload.get("approval_id")
        if approval_id is not None and str(approval_id).strip() == "":
            approval_id = None
        if approval_id is not None:
            approval_id = int(approval_id)

        execution_id = str(payload.get("execution_id") or "").strip() or None
        idempotency_key = str(payload.get("idempotency_key") or "").strip()
        if not idempotency_key:
            idempotency_key = (
                f"closed-loop:{rule.get('id')}:template:{int(template_id)}:"
                f"{','.join(str(d) for d in sorted(device_ids))}"
            )

        from app.api.v1.endpoints.config_template import TemplateDeployRequest, deploy_template

        req = TemplateDeployRequest(
            device_ids=device_ids,
            variables=variables,
            save_pre_backup=bool(payload.get("save_pre_backup", True)),
            rollback_on_failure=bool(payload.get("rollback_on_failure", True)),
            prepare_device_snapshot=bool(payload.get("prepare_device_snapshot", True)),
            pre_check_commands=pre_check_commands,
            post_check_enabled=bool(payload.get("post_check_enabled", True)),
            post_check_commands=post_check_commands,
            canary_count=canary_count,
            wave_size=wave_size,
            stop_on_wave_failure=bool(payload.get("stop_on_wave_failure", True)),
            inter_wave_delay_seconds=inter_wave_delay_seconds,
            idempotency_key=idempotency_key,
            approval_id=approval_id,
            execution_id=execution_id,
        )
        out = deploy_template(template_id=template_id, req=req, db=db, current_user=actor_user)
        execution = out.get("execution") if isinstance(out, dict) else {}
        return {
            "mode": "template_deploy_dispatched",
            "template_id": int(template_id),
            "device_ids": device_ids,
            "execution": execution if isinstance(execution, dict) else {},
        }

    @staticmethod
    def _execute_cloud_bootstrap_action(
        db: Session,
        *,
        rule: Dict[str, Any],
        action: Dict[str, Any],
        actor_user: User,
        signal_value: Any,
        match_reason: str,
    ) -> Dict[str, Any]:
        payload = action.get("payload") if isinstance(action.get("payload"), dict) else {}

        raw_account_ids = payload.get("account_ids")
        account_ids: List[int] = []
        if isinstance(raw_account_ids, list):
            for v in raw_account_ids:
                try:
                    aid = int(v)
                except Exception:
                    continue
                if aid > 0 and aid not in account_ids:
                    account_ids.append(aid)

        raw_regions = payload.get("regions")
        regions: List[str] = []
        if isinstance(raw_regions, list):
            for v in raw_regions:
                text = str(v or "").strip()
                if text and text not in regions:
                    regions.append(text)
        raw_resource_ids = payload.get("resource_ids")
        resource_ids: List[str] = []
        seen_resource_ids: set[str] = set()
        if isinstance(raw_resource_ids, list):
            for v in raw_resource_ids:
                text = str(v or "").strip()
                key = text.lower()
                if text and key not in seen_resource_ids:
                    seen_resource_ids.add(key)
                    resource_ids.append(text)

        try:
            canary_count = max(0, int(payload.get("canary_count") if payload.get("canary_count") is not None else 0))
        except Exception:
            canary_count = 0
        try:
            wave_size = max(0, int(payload.get("wave_size") if payload.get("wave_size") is not None else 0))
        except Exception:
            wave_size = 0
        try:
            inter_wave_delay_seconds = float(
                payload.get("inter_wave_delay_seconds") if payload.get("inter_wave_delay_seconds") is not None else 0.0
            )
        except Exception:
            inter_wave_delay_seconds = 0.0
        inter_wave_delay_seconds = max(0.0, min(300.0, inter_wave_delay_seconds))

        approval_id = payload.get("approval_id")
        if approval_id is not None and str(approval_id).strip() == "":
            approval_id = None
        if approval_id is not None:
            approval_id = int(approval_id)

        execution_id = str(payload.get("execution_id") or "").strip() or None
        idempotency_key = str(payload.get("idempotency_key") or "").strip()
        if not idempotency_key:
            idempotency_key = f"closed-loop:{rule.get('id')}:cloud-bootstrap:{int(action.get('index') or 0)}"

        context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
        script_template = str(payload.get("script_template") or "").strip() or None
        dry_run = bool(payload.get("dry_run", True))

        from app.schemas.cloud import CloudBootstrapRunRequest
        from app.services.change_policy_service import ChangePolicyService
        from app.services.cloud_bootstrap_service import CloudBootstrapService

        if ChangePolicyService.requires_cloud_bootstrap_live_approval(
            db,
            dry_run=bool(dry_run),
            approval_id=(int(approval_id) if approval_id is not None else None),
        ):
            opened_approval_id = ClosedLoopService._open_approval(
                db,
                actor_user,
                rule=rule,
                signal_value=signal_value,
                reason=f"{match_reason} (policy: cloud_bootstrap_live_requires_approval)",
            )
            return {
                "mode": "approval_opened",
                "approval_id": int(opened_approval_id),
                "policy": "cloud_bootstrap_live_requires_approval",
                "direct_execution_enabled": True,
            }

        req = CloudBootstrapRunRequest(
            account_ids=account_ids or None,
            regions=regions or None,
            resource_ids=resource_ids or None,
            dry_run=bool(dry_run),
            pre_check_enabled=bool(payload.get("pre_check_enabled", True)),
            post_check_enabled=bool(payload.get("post_check_enabled", True)),
            rollback_on_failure=bool(payload.get("rollback_on_failure", True)),
            canary_count=int(canary_count),
            wave_size=int(wave_size),
            stop_on_wave_failure=bool(payload.get("stop_on_wave_failure", True)),
            inter_wave_delay_seconds=float(inter_wave_delay_seconds),
            idempotency_key=idempotency_key,
            force=bool(payload.get("force", False)),
            approval_id=(int(approval_id) if approval_id is not None else None),
            execution_id=execution_id,
            script_template=script_template,
            context=context,
        )
        out = CloudBootstrapService.run(
            db,
            tenant_id=getattr(actor_user, "tenant_id", None),
            owner_id=int(getattr(actor_user, "id", 0) or 0),
            req=req,
        )
        payload_out = out.model_dump() if hasattr(out, "model_dump") else (dict(out) if isinstance(out, dict) else {})
        return {
            "mode": "cloud_bootstrap_dispatched",
            "status": str(payload_out.get("status") or ""),
            "total_targets": int(payload_out.get("total_targets") or 0),
            "success_targets": int(payload_out.get("success_targets") or 0),
            "failed_targets": int(payload_out.get("failed_targets") or 0),
            "dry_run_targets": int(payload_out.get("dry_run_targets") or 0),
            "approval_id": payload_out.get("approval_id"),
            "execution_id": payload_out.get("execution_id"),
            "idempotency_key": payload_out.get("idempotency_key"),
        }

    @staticmethod
    def _execute_intent_apply_action(
        db: Session,
        *,
        rule: Dict[str, Any],
        action: Dict[str, Any],
        actor_user: User,
    ) -> Dict[str, Any]:
        payload = action.get("payload") if isinstance(action.get("payload"), dict) else {}

        intent_type = str(payload.get("intent_type") or "").strip().lower()
        if not intent_type:
            raise ValueError("intent_apply action requires payload.intent_type")

        raw_name = str(payload.get("name") or "").strip()
        if raw_name:
            name = raw_name
        else:
            name = f"closed-loop-{str(rule.get('id') or 'intent')[:40]}"

        spec = payload.get("spec") if isinstance(payload.get("spec"), dict) else {}
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        dry_run = bool(payload.get("dry_run", False))

        approval_id = payload.get("approval_id")
        if approval_id is not None and str(approval_id).strip() == "":
            approval_id = None
        if approval_id is not None:
            approval_id = int(approval_id)

        execution_id = str(payload.get("execution_id") or "").strip() or None
        idempotency_key = str(payload.get("idempotency_key") or "").strip()
        if not idempotency_key:
            idempotency_key = (
                f"closed-loop:{rule.get('id')}:intent:{intent_type}:{int(action.get('index') or 0)}"
            )

        from app.services.intent_service import IntentService

        if not IntentService.is_enabled(db):
            raise ValueError("intent engine is disabled")

        out = IntentService.apply_intent(
            db,
            {
                "intent_type": intent_type,
                "name": name,
                "spec": spec,
                "metadata": metadata,
                "dry_run": bool(dry_run),
                "approval_id": (int(approval_id) if approval_id is not None else None),
                "execution_id": execution_id,
                "idempotency_key": idempotency_key,
            },
            actor_user=actor_user,
        )
        status = str(out.get("status") or "").strip().lower()
        simulation = out.get("simulation") if isinstance(out.get("simulation"), dict) else {}
        return {
            "mode": "intent_apply_dispatched",
            "intent_type": intent_type,
            "intent_name": name,
            "intent_status": status,
            "execution_id": out.get("execution_id"),
            "approval_id": out.get("approval_id"),
            "risk_score": simulation.get("risk_score"),
            "apply_eligible": simulation.get("apply_eligible"),
            "message": out.get("message"),
        }

    @staticmethod
    def evaluate(
        db: Session,
        *,
        signals: Dict[str, Any],
        actor_user: User,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        if not ClosedLoopService.engine_enabled(db):
            return {
                "engine_enabled": False,
                "auto_execute_enabled": ClosedLoopService.auto_execute_enabled(db),
                "dry_run": bool(dry_run),
                "rules_total": 0,
                "triggered": 0,
                "executed": 0,
                "blocked": 0,
                "decisions": [],
                "message": "Closed-loop engine is disabled.",
            }

        rules = ClosedLoopService.get_rules(db)
        auto_exec = ClosedLoopService.auto_execute_enabled(db)
        execute_change_actions = ClosedLoopService.execute_change_actions_enabled(db)
        default_cooldown = ClosedLoopService.default_cooldown_seconds(db)
        default_limit = ClosedLoopService.default_max_actions_per_hour(db)

        decisions: List[Dict[str, Any]] = []
        triggered = 0
        executed = 0
        blocked = 0
        now = datetime.now(timezone.utc)
        now_hour = ClosedLoopService._hour_key(now)
        issue_ctx = signals.get("issue") if isinstance(signals.get("issue"), dict) else {}
        trigger_context = {
            "issue": {
                "id": issue_ctx.get("id"),
                "title": issue_ctx.get("title"),
                "severity": issue_ctx.get("severity"),
                "category": issue_ctx.get("category"),
                "device_id": issue_ctx.get("device_id"),
                "kind": issue_ctx.get("kind"),
            }
        } if issue_ctx else None

        for rule in rules:
            if not bool(rule.get("enabled", True)):
                continue
            condition = rule.get("condition") if isinstance(rule.get("condition"), dict) else {}
            signal_value, exists = ClosedLoopService._read_path(signals, str(condition.get("path") or ""))
            if not exists:
                decisions.append(
                    {
                        "rule_id": rule.get("id"),
                        "rule_name": rule.get("name"),
                        "status": "skipped_missing_signal",
                        "path": condition.get("path"),
                    }
                )
                continue

            matched = ClosedLoopService._eval_condition(signal_value, str(condition.get("operator") or ""), condition.get("value"))
            if not matched:
                decisions.append(
                    {
                        "rule_id": rule.get("id"),
                        "rule_name": rule.get("name"),
                        "status": "not_matched",
                        "path": condition.get("path"),
                        "signal_value": signal_value,
                    }
                )
                continue

            triggered += 1
            cooldown = int(rule.get("cooldown_seconds")) if rule.get("cooldown_seconds") is not None else default_cooldown
            rate_limit = (
                int(rule.get("max_actions_per_hour"))
                if rule.get("max_actions_per_hour") is not None
                else default_limit
            )

            state = ClosedLoopService._load_state(db, str(rule.get("id")))
            last_action_at = state.get("last_action_at")
            hour_bucket = str(state.get("hour_bucket") or "")
            hour_count = int(state.get("hour_count") or 0)

            cooldown_blocked = False
            if last_action_at:
                try:
                    last_dt = datetime.fromisoformat(str(last_action_at))
                    delta = (now - last_dt).total_seconds()
                    if delta < float(cooldown):
                        cooldown_blocked = True
                except Exception:
                    cooldown_blocked = False

            if hour_bucket != now_hour:
                hour_bucket = now_hour
                hour_count = 0
            rate_blocked = hour_count >= rate_limit

            if cooldown_blocked:
                blocked += 1
                decisions.append(
                    {
                        "rule_id": rule.get("id"),
                        "rule_name": rule.get("name"),
                        "status": "blocked_cooldown",
                        "signal_value": signal_value,
                        "cooldown_seconds": cooldown,
                    }
                )
                continue

            if rate_blocked:
                blocked += 1
                decisions.append(
                    {
                        "rule_id": rule.get("id"),
                        "rule_name": rule.get("name"),
                        "status": "blocked_rate_limit",
                        "signal_value": signal_value,
                        "max_actions_per_hour": rate_limit,
                    }
                )
                continue

            action = rule.get("action") if isinstance(rule.get("action"), dict) else {}
            action_type = str(action.get("type") or "").strip().lower()

            if dry_run:
                decisions.append(
                    {
                        "rule_id": rule.get("id"),
                        "rule_name": rule.get("name"),
                        "status": "matched_dry_run",
                        "signal_value": signal_value,
                        "action": action,
                    }
                )
                continue

            if not auto_exec:
                decisions.append(
                    {
                        "rule_id": rule.get("id"),
                        "rule_name": rule.get("name"),
                        "status": "matched_auto_execute_disabled",
                        "signal_value": signal_value,
                        "action": action,
                    }
                )
                continue

            require_approval = bool(rule.get("require_approval", True))
            approval_id = None
            action_result: Dict[str, Any] = {}
            match_reason = (
                f"matched:{condition.get('path')} "
                f"{condition.get('operator')} {condition.get('value')}"
            )
            if issue_ctx:
                issue_id = issue_ctx.get("id")
                issue_title = str(issue_ctx.get("title") or "").strip()
                if issue_id:
                    match_reason += f" issue={issue_id}"
                if issue_title:
                    match_reason += f" title={issue_title[:80]}"

            try:
                if require_approval:
                    approval_id = ClosedLoopService._open_approval(
                        db,
                        actor_user,
                        rule=rule,
                        signal_value=signal_value,
                        reason=match_reason,
                        context=trigger_context,
                    )
                    action_result = {"mode": "approval_opened", "approval_id": approval_id}
                elif action_type == ClosedLoopService.ACTION_NOTIFY:
                    notify_data = {
                        "rule_id": rule.get("id"),
                        "signal_path": condition.get("path"),
                        "signal_value": signal_value,
                    }
                    if issue_ctx:
                        notify_data.update(
                            {
                                "issue_id": issue_ctx.get("id"),
                                "issue_title": issue_ctx.get("title"),
                                "issue_severity": issue_ctx.get("severity"),
                                "issue_category": issue_ctx.get("category"),
                                "issue_kind": issue_ctx.get("kind"),
                                "issue_device_id": issue_ctx.get("device_id"),
                            }
                        )
                    action_result = WebhookService.send(
                        db,
                        event_type="closed_loop",
                        title=str(action.get("title") or rule.get("name") or "Closed-loop action"),
                        message=str(action.get("message") or "Closed-loop notify action triggered."),
                        severity="warning",
                        source="closed_loop",
                        data=notify_data,
                    )
                    if not action_result.get("success"):
                        action_result["mode"] = "notify_failed"
                    else:
                        action_result["mode"] = "notify_sent"
                elif action_type == ClosedLoopService.ACTION_OPEN_APPROVAL:
                    approval_id = ClosedLoopService._open_approval(
                        db,
                        actor_user,
                        rule=rule,
                        signal_value=signal_value,
                        reason=match_reason,
                        context=trigger_context,
                    )
                    action_result = {"mode": "approval_opened", "approval_id": approval_id}
                elif action_type == ClosedLoopService.ACTION_RUN_SCAN:
                    if not execute_change_actions:
                        approval_id = ClosedLoopService._open_approval(
                            db,
                            actor_user,
                            rule=rule,
                            signal_value=signal_value,
                            reason=match_reason,
                            context=trigger_context,
                        )
                        action_result = {
                            "mode": "approval_opened",
                            "approval_id": approval_id,
                            "direct_execution_enabled": bool(execute_change_actions),
                        }
                    else:
                        action_result = ClosedLoopService._execute_run_scan_action(
                            db,
                            rule=rule,
                            action=action,
                        )
                elif action_type == ClosedLoopService.ACTION_TEMPLATE_DEPLOY:
                    if not execute_change_actions:
                        approval_id = ClosedLoopService._open_approval(
                            db,
                            actor_user,
                            rule=rule,
                            signal_value=signal_value,
                            reason=match_reason,
                            context=trigger_context,
                        )
                        action_result = {
                            "mode": "approval_opened",
                            "approval_id": approval_id,
                            "direct_execution_enabled": bool(execute_change_actions),
                        }
                    else:
                        action_result = ClosedLoopService._execute_template_deploy_action(
                            db,
                            rule=rule,
                            action=action,
                            actor_user=actor_user,
                        )
                elif action_type == ClosedLoopService.ACTION_CLOUD_BOOTSTRAP:
                    if not execute_change_actions:
                        approval_id = ClosedLoopService._open_approval(
                            db,
                            actor_user,
                            rule=rule,
                            signal_value=signal_value,
                            reason=match_reason,
                            context=trigger_context,
                        )
                        action_result = {
                            "mode": "approval_opened",
                            "approval_id": approval_id,
                            "direct_execution_enabled": bool(execute_change_actions),
                        }
                    else:
                        action_result = ClosedLoopService._execute_cloud_bootstrap_action(
                            db,
                            rule=rule,
                            action=action,
                            actor_user=actor_user,
                            signal_value=signal_value,
                            match_reason=match_reason,
                        )
                elif action_type == ClosedLoopService.ACTION_INTENT_APPLY:
                    if not execute_change_actions:
                        approval_id = ClosedLoopService._open_approval(
                            db,
                            actor_user,
                            rule=rule,
                            signal_value=signal_value,
                            reason=match_reason,
                            context=trigger_context,
                        )
                        action_result = {
                            "mode": "approval_opened",
                            "approval_id": approval_id,
                            "direct_execution_enabled": bool(execute_change_actions),
                        }
                    else:
                        action_result = ClosedLoopService._execute_intent_apply_action(
                            db,
                            rule=rule,
                            action=action,
                            actor_user=actor_user,
                        )
                else:
                    action_result = {"mode": "no_op"}
            except Exception as e:
                blocked += 1
                decisions.append(
                    {
                        "rule_id": rule.get("id"),
                        "rule_name": rule.get("name"),
                        "status": "action_error",
                        "signal_value": signal_value,
                        "error": f"{type(e).__name__}: {e}",
                        "action": action,
                    }
                )
                continue

            state["last_action_at"] = now.isoformat()
            state["hour_bucket"] = now_hour
            state["hour_count"] = int(hour_count + 1)
            ClosedLoopService._save_state(db, str(rule.get("id")), state)

            executed += 1
            decisions.append(
                {
                    "rule_id": rule.get("id"),
                    "rule_name": rule.get("name"),
                    "status": "executed",
                    "signal_value": signal_value,
                    "action": action,
                    "result": action_result,
                    "approval_id": approval_id,
                }
            )

        db.commit()
        return {
            "engine_enabled": ClosedLoopService.engine_enabled(db),
            "auto_execute_enabled": bool(auto_exec),
            "dry_run": bool(dry_run),
            "rules_total": len(rules),
            "triggered": int(triggered),
            "executed": int(executed),
            "blocked": int(blocked),
            "decisions": decisions,
        }
