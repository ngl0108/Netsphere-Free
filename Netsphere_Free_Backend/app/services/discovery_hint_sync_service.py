from __future__ import annotations

from datetime import datetime, timezone
import os
from typing import Any, Dict, Optional

import requests
from sqlalchemy.orm import Session

from app.models.settings import SystemSetting
from app.services.discovery_hint_rule_service import DiscoveryHintRuleService
from app.services.discovery_hint_telemetry_service import DiscoveryHintTelemetryService
from app.services.discovery_hint_tuning_service import DiscoveryHintTuningService


class DiscoveryHintSyncService:
    SETTING_RULE_VERSION_KEY = "discovery_hint_remote_rule_version"
    SETTING_PULL_AT_KEY = "discovery_hint_remote_rule_last_pull_at"
    SETTING_PULL_STATUS_KEY = "discovery_hint_remote_rule_last_pull_status"
    SETTING_LAST_EVENT_ID_KEY = "discovery_hint_remote_last_event_id"
    SETTING_PUSH_AT_KEY = "discovery_hint_remote_telemetry_last_push_at"
    SETTING_PUSH_STATUS_KEY = "discovery_hint_remote_telemetry_last_push_status"

    MANAGED_REMOTE_SOURCE = "remote_ota"
    SETTING_SCHEDULER_LAST_PULL_ATTEMPT_KEY = "discovery_hint_remote_scheduler_last_pull_attempt_at"
    SETTING_SCHEDULER_LAST_PUSH_ATTEMPT_KEY = "discovery_hint_remote_scheduler_last_push_attempt_at"

    @classmethod
    def _env(cls, key: str, default: str = "") -> str:
        return str(os.getenv(key, default) or default).strip()

    @classmethod
    def is_enabled(cls) -> bool:
        raw = cls._env("DISCOVERY_HINT_REMOTE_SYNC_ENABLED", "false").lower()
        return raw in {"1", "true", "yes", "y", "on"}

    @classmethod
    def _base_url(cls) -> str:
        return cls._env("DISCOVERY_HINT_REMOTE_BASE_URL", "").rstrip("/")

    @classmethod
    def _timeout(cls) -> float:
        raw = cls._env("DISCOVERY_HINT_REMOTE_TIMEOUT_SECONDS", "10")
        try:
            return max(3.0, float(raw))
        except Exception:
            return 10.0

    @classmethod
    def _batch_size(cls) -> int:
        raw = cls._env("DISCOVERY_HINT_REMOTE_PUSH_BATCH_SIZE", "100")
        try:
            return max(1, min(int(raw), 1000))
        except Exception:
            return 100

    @classmethod
    def pull_interval_seconds(cls) -> int:
        raw = cls._env("DISCOVERY_HINT_REMOTE_PULL_INTERVAL_SECONDS", "1800")
        try:
            return max(60, min(int(raw), 86400))
        except Exception:
            return 1800

    @classmethod
    def push_interval_seconds(cls) -> int:
        raw = cls._env("DISCOVERY_HINT_REMOTE_PUSH_INTERVAL_SECONDS", "300")
        try:
            return max(30, min(int(raw), 86400))
        except Exception:
            return 300

    @classmethod
    def _headers(cls) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        token = cls._env("DISCOVERY_HINT_REMOTE_BEARER_TOKEN", "")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    @classmethod
    def _get_setting(cls, db: Session, key: str, default: str = "") -> str:
        row = db.query(SystemSetting).filter(SystemSetting.key == str(key)).first()
        return str(getattr(row, "value", "") or default).strip()

    @classmethod
    def _set_setting(cls, db: Session, *, key: str, value: Any, description: str) -> None:
        row = db.query(SystemSetting).filter(SystemSetting.key == str(key)).first()
        if row is None:
            row = SystemSetting(key=str(key), value=str(value or ""), description=description, category="discovery_hint")
            db.add(row)
        else:
            row.value = str(value or "")
            row.description = description
            row.category = "discovery_hint"

    @classmethod
    def _unwrap_response_data(cls, response: requests.Response) -> Dict[str, Any]:
        data = response.json()
        if isinstance(data, dict) and "data" in data and isinstance(data["data"], dict):
            data = data["data"]
        return data if isinstance(data, dict) else {}

    @classmethod
    def pull_rule_snapshot(cls, db: Session) -> Dict[str, Any]:
        if not cls.is_enabled():
            return {"status": "disabled"}
        base_url = cls._base_url()
        if not base_url:
            return {"status": "disabled", "reason": "missing_base_url"}
        since_version = cls._get_setting(db, cls.SETTING_RULE_VERSION_KEY, "")
        params = {"since_version": since_version} if since_version else None
        url = f"{base_url}/api/v1/discovery/hints/rules/ota"
        try:
            response = requests.get(url, params=params, headers=cls._headers(), timeout=cls._timeout())
            response.raise_for_status()
            data = cls._unwrap_response_data(response)
        except Exception as exc:
            cls._set_setting(
                db,
                key=cls.SETTING_PULL_STATUS_KEY,
                value=f"failed:{exc}",
                description="Last remote discovery hint rule pull status",
            )
            db.commit()
            return {"status": "failed", "reason": str(exc)}
        if bool(data.get("not_modified")):
            cls._set_setting(
                db,
                key=cls.SETTING_PULL_AT_KEY,
                value=datetime.now(timezone.utc).isoformat(),
                description="When discovery hint rules were last pulled",
            )
            cls._set_setting(
                db,
                key=cls.SETTING_PULL_STATUS_KEY,
                value="not_modified",
                description="Last remote discovery hint rule pull status",
            )
            db.commit()
            return {"status": "not_modified", "version": str(data.get("version") or since_version)}
        result = DiscoveryHintRuleService.replace_rules_for_source(
            managed_source=cls.MANAGED_REMOTE_SOURCE,
            rules=list(data.get("rules") or []),
        )
        version = str(data.get("version") or "").strip()
        if version:
            cls._set_setting(
                db,
                key=cls.SETTING_RULE_VERSION_KEY,
                value=version,
                description="Last remote discovery hint rule version",
            )
        cls._set_setting(
            db,
            key=cls.SETTING_PULL_AT_KEY,
            value=datetime.now(timezone.utc).isoformat(),
            description="When discovery hint rules were last pulled",
        )
        cls._set_setting(
            db,
            key=cls.SETTING_PULL_STATUS_KEY,
            value=f"ok:{version or 'unknown'}",
            description="Last remote discovery hint rule pull status",
        )
        db.commit()
        return {
            "status": "ok",
            "version": version,
            "upserted": int(result.get("upserted") or 0),
            "deactivated": int(result.get("deactivated") or 0),
        }

    @classmethod
    def push_recent_telemetry(cls, db: Session) -> Dict[str, Any]:
        if not cls.is_enabled():
            return {"status": "disabled"}
        base_url = cls._base_url()
        if not base_url:
            return {"status": "disabled", "reason": "missing_base_url"}
        last_event_id = int(cls._get_setting(db, cls.SETTING_LAST_EVENT_ID_KEY, "0") or 0)
        events = DiscoveryHintTelemetryService.list_since_id(
            last_event_id=last_event_id,
            limit=cls._batch_size(),
            include_payload=True,
        )
        if not events:
            cls._set_setting(
                db,
                key=cls.SETTING_PUSH_AT_KEY,
                value=datetime.now(timezone.utc).isoformat(),
                description="When discovery hint telemetry was last pushed",
            )
            cls._set_setting(
                db,
                key=cls.SETTING_PUSH_STATUS_KEY,
                value="idle:0",
                description="Last remote discovery hint telemetry push status",
            )
            db.commit()
            return {"status": "idle", "uploaded": 0, "last_event_id": last_event_id}
        payload = {
            "events": [
                dict(event.get("payload") or {k: v for k, v in event.items() if k not in {"id", "created_at", "payload"}})
                for event in events
            ]
        }
        url = f"{base_url}/api/v1/discovery/hints/telemetry"
        try:
            response = requests.post(url, json=payload, headers=cls._headers(), timeout=cls._timeout())
            response.raise_for_status()
            data = cls._unwrap_response_data(response)
        except Exception as exc:
            cls._set_setting(
                db,
                key=cls.SETTING_PUSH_STATUS_KEY,
                value=f"failed:{exc}",
                description="Last remote discovery hint telemetry push status",
            )
            db.commit()
            return {"status": "failed", "reason": str(exc)}
        new_last_event_id = int(events[-1]["id"])
        cls._set_setting(
            db,
            key=cls.SETTING_LAST_EVENT_ID_KEY,
            value=str(new_last_event_id),
            description="Last uploaded discovery hint telemetry event id",
        )
        cls._set_setting(
            db,
            key=cls.SETTING_PUSH_AT_KEY,
            value=datetime.now(timezone.utc).isoformat(),
            description="When discovery hint telemetry was last pushed",
        )
        cls._set_setting(
            db,
            key=cls.SETTING_PUSH_STATUS_KEY,
            value=f"ok:{new_last_event_id}",
            description="Last remote discovery hint telemetry push status",
        )
        db.commit()
        return {
            "status": "ok",
            "accepted": int(data.get("accepted") or len(events)),
            "ingested": int(data.get("ingested") or 0),
            "uploaded": len(events),
            "last_event_id": new_last_event_id,
        }

    @classmethod
    def build_status_summary(cls, db: Session, *, benchmark_limit: int = 500) -> Dict[str, Any]:
        from app.services.discovery_hint_benchmark_service import DiscoveryHintBenchmarkService
        from app.services.discovery_hint_rule_service import DiscoveryHintRuleService

        rules = DiscoveryHintRuleService.list_rules_detailed(include_inactive=True)
        active_rules = [item for item in rules if bool(item.get("is_active"))]
        benchmark = DiscoveryHintBenchmarkService.summarize_recent(limit=benchmark_limit)
        benchmark_trend = DiscoveryHintBenchmarkService.summarize_trend(window=max(25, min(int(benchmark_limit or 500) // 2, 250)))
        telemetry_events = DiscoveryHintTelemetryService.list_recent(limit=min(int(benchmark_limit or 500), 250), include_payload=True)
        recommendations = DiscoveryHintTuningService.build_recommendations(
            benchmark=benchmark,
            active_rules=active_rules,
        )
        score_adjustments = DiscoveryHintTuningService.build_score_adjustments(
            benchmark=benchmark,
            active_rules=active_rules,
        )
        alias_candidates = DiscoveryHintTuningService.build_alias_candidates(
            telemetry_events=telemetry_events,
        )
        seed_rule_drafts = DiscoveryHintTuningService.build_seed_rule_drafts(
            telemetry_events=telemetry_events,
            active_rules=active_rules,
        )
        false_positive_hotspots = DiscoveryHintTuningService.build_false_positive_hotspots(
            benchmark=benchmark,
        )
        return {
            "sync": {
                "enabled": cls.is_enabled(),
                "base_url_configured": bool(cls._base_url()),
                "bearer_configured": bool(cls._env("DISCOVERY_HINT_REMOTE_BEARER_TOKEN", "")),
                "pull_interval_seconds": cls.pull_interval_seconds(),
                "push_interval_seconds": cls.push_interval_seconds(),
                "rule_version": cls._get_setting(db, cls.SETTING_RULE_VERSION_KEY, ""),
                "last_pull_at": cls._get_setting(db, cls.SETTING_PULL_AT_KEY, ""),
                "last_pull_status": cls._get_setting(db, cls.SETTING_PULL_STATUS_KEY, ""),
                "last_push_at": cls._get_setting(db, cls.SETTING_PUSH_AT_KEY, ""),
                "last_push_status": cls._get_setting(db, cls.SETTING_PUSH_STATUS_KEY, ""),
                "last_uploaded_event_id": int(cls._get_setting(db, cls.SETTING_LAST_EVENT_ID_KEY, "0") or 0),
                "scheduler_last_pull_attempt_at": cls._get_setting(db, cls.SETTING_SCHEDULER_LAST_PULL_ATTEMPT_KEY, ""),
                "scheduler_last_push_attempt_at": cls._get_setting(db, cls.SETTING_SCHEDULER_LAST_PUSH_ATTEMPT_KEY, ""),
            },
            "rules": {
                "total": len(rules),
                "active": len(active_rules),
                "version": DiscoveryHintRuleService._compute_version(active_rules),
            },
            "benchmark": benchmark,
            "benchmark_trend": benchmark_trend,
            "recommendations": recommendations,
            "score_adjustments": score_adjustments,
            "alias_candidates": alias_candidates,
            "seed_rule_drafts": seed_rule_drafts,
            "false_positive_hotspots": false_positive_hotspots,
        }
