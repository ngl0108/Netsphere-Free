from __future__ import annotations

from datetime import datetime, timezone
import os
import re
from typing import Any, Callable, Dict, Iterable, List, Optional

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.discovery_hint_learning import DiscoveryHintRule


class DiscoveryHintRuleService:
    _override_rules: Optional[List[Dict[str, Any]]] = None
    _session_factory: Optional[Callable[[], Session]] = None
    _DRIVER_ALIAS_MAP = {
        "handreamnet_sg": "handream_sg",
    }

    @classmethod
    def _persistence_enabled(cls) -> bool:
        app_env = str(os.getenv("APP_ENV") or "").strip().lower()
        if app_env in {"test", "pytest"} and cls._session_factory is None:
            return False
        raw = os.getenv("DISCOVERY_HINT_RULES_PERSIST", "true")
        return str(raw or "").strip().lower() in {"1", "true", "yes", "y", "on"}

    @classmethod
    def _get_session_factory(cls) -> Callable[[], Session]:
        return cls._session_factory or SessionLocal

    @classmethod
    def set_session_factory_for_tests(cls, factory: Optional[Callable[[], Session]]) -> None:
        cls._session_factory = factory

    @classmethod
    def set_override_rules_for_tests(cls, rules: Optional[List[Dict[str, Any]]]) -> None:
        cls._override_rules = list(rules or []) if rules is not None else None

    @staticmethod
    def _ensure_aware(value: datetime | None) -> datetime | None:
        if not isinstance(value, datetime):
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    @classmethod
    def clear_for_tests(cls) -> None:
        cls._override_rules = None
        if not cls._persistence_enabled():
            return
        db = cls._get_session_factory()()
        try:
            db.query(DiscoveryHintRule).delete(synchronize_session=False)
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    @classmethod
    def upsert_rule(cls, rule: Dict[str, Any]) -> Optional[int]:
        if not cls._persistence_enabled() or not isinstance(rule, dict):
            return None
        rule_key = str(rule.get("rule_key") or rule.get("rule_id") or "").strip()
        if not rule_key:
            return None
        db = cls._get_session_factory()()
        try:
            row = db.query(DiscoveryHintRule).filter(DiscoveryHintRule.rule_key == rule_key).first()
            if row is None:
                row = DiscoveryHintRule(rule_key=rule_key, match_conditions={}, driver_overrides=[])
                db.add(row)
            row.vendor_family = str(rule.get("vendor_family") or "").strip() or None
            row.match_conditions = dict(rule.get("match_conditions") or {})
            row.driver_overrides = cls._normalize_driver_overrides(rule.get("driver_overrides") or [])
            row.score_bonus = float(rule.get("score_bonus") or 0.0)
            row.evidence_count = int(rule.get("evidence_count") or 0)
            row.source = str(rule.get("source") or "telemetry").strip() or "telemetry"
            row.is_active = bool(rule.get("is_active", True))
            row.expires_at = rule.get("expires_at")
            db.commit()
            db.refresh(row)
            return int(row.id)
        except Exception:
            db.rollback()
            return None
        finally:
            db.close()

    @classmethod
    def _load_rules_from_db(cls) -> List[Dict[str, Any]]:
        if not cls._persistence_enabled():
            return []
        db = cls._get_session_factory()()
        try:
            rows = db.query(DiscoveryHintRule).filter(DiscoveryHintRule.is_active.is_(True)).all()
            now = datetime.now(timezone.utc)
            out: List[Dict[str, Any]] = []
            for row in rows:
                expires_at = cls._ensure_aware(row.expires_at)
                if expires_at is not None and expires_at <= now:
                    continue
                out.append(
                    {
                        "rule_id": row.rule_key,
                        "vendor_family": row.vendor_family,
                        "match_conditions": dict(row.match_conditions or {}),
                        "driver_overrides": list(row.driver_overrides or []),
                        "score_bonus": float(row.score_bonus or 0.0),
                        "evidence_count": int(row.evidence_count or 0),
                        "source": row.source,
                    }
                )
            return out
        finally:
            db.close()

    @classmethod
    def list_rules_detailed(cls, *, include_inactive: bool = False) -> List[Dict[str, Any]]:
        if not cls._persistence_enabled():
            rules = list(cls._override_rules or [])
            return [
                {
                    "id": None,
                    "rule_key": str(rule.get("rule_key") or rule.get("rule_id") or ""),
                    "vendor_family": str(rule.get("vendor_family") or "").strip() or None,
                    "match_conditions": dict(rule.get("match_conditions") or {}),
                    "driver_overrides": cls._normalize_driver_overrides(rule.get("driver_overrides") or []),
                    "score_bonus": float(rule.get("score_bonus") or 0.0),
                    "evidence_count": int(rule.get("evidence_count") or 0),
                    "source": str(rule.get("source") or "override").strip() or "override",
                    "is_active": bool(rule.get("is_active", True)),
                    "expires_at": rule.get("expires_at"),
                    "created_at": None,
                    "updated_at": None,
                }
                for rule in rules
                if include_inactive or bool(rule.get("is_active", True))
            ]
        db = cls._get_session_factory()()
        try:
            query = db.query(DiscoveryHintRule)
            if not include_inactive:
                query = query.filter(DiscoveryHintRule.is_active.is_(True))
            rows = query.order_by(DiscoveryHintRule.rule_key.asc()).all()
            return [
                {
                    "id": int(row.id),
                    "rule_key": row.rule_key,
                    "vendor_family": row.vendor_family,
                    "match_conditions": dict(row.match_conditions or {}),
                    "driver_overrides": list(row.driver_overrides or []),
                    "score_bonus": float(row.score_bonus or 0.0),
                    "evidence_count": int(row.evidence_count or 0),
                    "source": row.source,
                    "is_active": bool(row.is_active),
                    "expires_at": cls._ensure_aware(row.expires_at),
                    "created_at": cls._ensure_aware(row.created_at),
                    "updated_at": cls._ensure_aware(row.updated_at),
                }
                for row in rows
            ]
        finally:
            db.close()

    @classmethod
    def _compute_version(cls, rules: List[Dict[str, Any]]) -> str:
        if not rules:
            return "0:0"
        latest = 0
        for rule in rules:
            ts = cls._ensure_aware(rule.get("updated_at")) or cls._ensure_aware(rule.get("created_at"))
            if ts is not None:
                latest = max(latest, int(ts.timestamp()))
        return f"{len(rules)}:{latest}"

    @classmethod
    def build_ota_snapshot(cls, *, since_version: Optional[str] = None) -> Dict[str, Any]:
        rules = cls.list_rules_detailed(include_inactive=False)
        version = cls._compute_version(rules)
        if since_version and str(since_version).strip() == version:
            return {
                "version": version,
                "generated_at": datetime.now(timezone.utc),
                "not_modified": True,
                "count": len(rules),
                "rules": [],
            }
        return {
            "version": version,
            "generated_at": datetime.now(timezone.utc),
            "not_modified": False,
            "count": len(rules),
            "rules": [
                {
                    "rule_key": str(rule.get("rule_key") or ""),
                    "vendor_family": rule.get("vendor_family"),
                    "match_conditions": dict(rule.get("match_conditions") or {}),
                    "driver_overrides": list(rule.get("driver_overrides") or []),
                    "score_bonus": float(rule.get("score_bonus") or 0.0),
                    "evidence_count": int(rule.get("evidence_count") or 0),
                    "source": rule.get("source"),
                    "expires_at": rule.get("expires_at"),
                }
                for rule in rules
            ],
        }

    @classmethod
    def replace_rules_for_source(cls, *, managed_source: str, rules: List[Dict[str, Any]]) -> Dict[str, int]:
        if not cls._persistence_enabled():
            cls._override_rules = list(rules or [])
            return {"upserted": len(rules or []), "deactivated": 0}
        clean_source = str(managed_source or "").strip() or "remote_ota"
        incoming = [dict(rule) for rule in (rules or []) if isinstance(rule, dict)]
        incoming_keys = {
            str(rule.get("rule_key") or rule.get("rule_id") or "").strip()
            for rule in incoming
            if str(rule.get("rule_key") or rule.get("rule_id") or "").strip()
        }
        db = cls._get_session_factory()()
        upserted = 0
        deactivated = 0
        try:
            for rule in incoming:
                rule_key = str(rule.get("rule_key") or rule.get("rule_id") or "").strip()
                if not rule_key:
                    continue
                row = db.query(DiscoveryHintRule).filter(DiscoveryHintRule.rule_key == rule_key).first()
                if row is None:
                    row = DiscoveryHintRule(rule_key=rule_key, match_conditions={}, driver_overrides=[])
                    db.add(row)
                row.vendor_family = str(rule.get("vendor_family") or "").strip() or None
                row.match_conditions = dict(rule.get("match_conditions") or {})
                row.driver_overrides = cls._normalize_driver_overrides(rule.get("driver_overrides") or [])
                row.score_bonus = float(rule.get("score_bonus") or 0.0)
                row.evidence_count = int(rule.get("evidence_count") or 0)
                row.source = clean_source
                row.is_active = bool(rule.get("is_active", True))
                row.expires_at = rule.get("expires_at")
                upserted += 1
            managed_rows = db.query(DiscoveryHintRule).filter(DiscoveryHintRule.source == clean_source).all()
            for row in managed_rows:
                if str(row.rule_key or "").strip() not in incoming_keys and bool(row.is_active):
                    row.is_active = False
                    deactivated += 1
            db.commit()
            return {"upserted": upserted, "deactivated": deactivated}
        except Exception:
            db.rollback()
            return {"upserted": 0, "deactivated": 0}
        finally:
            db.close()

    @classmethod
    def get_rules(cls) -> List[Dict[str, Any]]:
        rules = cls._load_rules_from_db()
        if cls._override_rules:
            rules.extend(list(cls._override_rules))
        return rules

    @classmethod
    def evaluate_overrides(
        cls,
        *,
        cache_hit: Dict[str, Any],
        raw_vendor: str,
        normalized_vendor: str,
        open_ports: Iterable[int],
    ) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for rule in cls.get_rules():
            if not isinstance(rule, dict):
                continue
            if not cls._matches(rule, cache_hit=cache_hit, raw_vendor=raw_vendor, normalized_vendor=normalized_vendor, open_ports=open_ports):
                continue
            drivers = cls._normalize_driver_overrides(rule.get("driver_overrides") or [])
            if not drivers:
                continue
            score_bonus = float(rule.get("score_bonus") or 0.0)
            for index, driver in enumerate(drivers):
                results.append(
                    {
                        "vendor_family": str(rule.get("vendor_family") or normalized_vendor or "rule_override"),
                        "driver": driver,
                        "score": round(max(0.05, 0.35 + score_bonus - (index * 0.04)), 3),
                        "reasons": ["central_rule_override", str(rule.get("rule_id") or "rule")],
                    }
                )
        return sorted(results, key=lambda item: float(item.get("score") or 0.0), reverse=True)

    @classmethod
    def _normalize_driver_name(cls, driver: Any) -> str:
        value = str(driver or "").strip()
        if not value:
            return ""
        return cls._DRIVER_ALIAS_MAP.get(value.lower(), value)

    @classmethod
    def _normalize_driver_overrides(cls, drivers: Iterable[Any]) -> List[str]:
        normalized: List[str] = []
        seen = set()
        for driver in list(drivers or []):
            value = cls._normalize_driver_name(driver)
            if not value:
                continue
            key = value.lower()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(value)
        return normalized

    @staticmethod
    def _matches(
        rule: Dict[str, Any],
        *,
        cache_hit: Dict[str, Any],
        raw_vendor: str,
        normalized_vendor: str,
        open_ports: Iterable[int],
    ) -> bool:
        conditions = rule.get("match_conditions") if isinstance(rule.get("match_conditions"), dict) else {}
        if conditions.get("ssh_open") is True and not any(int(port) in {22, 830} for port in open_ports if str(port).isdigit()):
            return False
        raw_vendor_contains = [str(x).lower() for x in (conditions.get("raw_vendor_contains") or []) if str(x or "").strip()]
        if raw_vendor_contains and not any(token in str(raw_vendor or "").lower() for token in raw_vendor_contains):
            return False
        normalized_vendor_equals = str(conditions.get("normalized_vendor_equals") or "").strip()
        if normalized_vendor_equals and normalized_vendor_equals != str(normalized_vendor or "").strip():
            return False
        neighbor_name_regex = str(conditions.get("neighbor_name_regex") or "").strip()
        if neighbor_name_regex:
            neighbor_name = str(cache_hit.get("neighbor_name") or "").strip()
            if not re.search(neighbor_name_regex, neighbor_name, re.IGNORECASE):
                return False
        seed_vendor_regex = str(conditions.get("seed_vendor_regex") or "").strip()
        if seed_vendor_regex:
            seed_vendor = str(cache_hit.get("seed_vendor") or "").strip()
            if not re.search(seed_vendor_regex, seed_vendor, re.IGNORECASE):
                return False
        return True
