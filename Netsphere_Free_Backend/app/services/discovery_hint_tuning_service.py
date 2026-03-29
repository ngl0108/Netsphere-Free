from __future__ import annotations

import re
from typing import Any, Dict, List

from app.services.oui_service import OUIService


class DiscoveryHintTuningService:
    _GENERIC_CHIPSET_TOKENS = (
        "intel",
        "broadcom",
        "realtek",
        "marvell",
        "mediatek",
        "ralink",
    )

    @staticmethod
    def _severity_rank(value: str) -> int:
        return {"high": 0, "medium": 1, "low": 2}.get(str(value or "medium").lower(), 1)

    @staticmethod
    def _vendor_key(value: Any) -> str:
        return str(value or "").strip().lower()

    @classmethod
    def _chipset_token(cls, raw_vendor: Any) -> str:
        text = cls._vendor_key(raw_vendor)
        for token in cls._GENERIC_CHIPSET_TOKENS:
            if token in text:
                return token
        return ""

    @staticmethod
    def _normalized_vendor_is_unknown(value: Any) -> bool:
        text = str(value or "").strip().lower()
        return not text or text in {"unknown", "generic", "generic_embedded_or_server"}

    @classmethod
    def _infer_vendor_from_event(cls, event: Dict[str, Any]) -> str:
        payload = dict(event.get("payload") or {})
        normalized_vendor = cls._vendor_key(payload.get("normalized_vendor") or event.get("normalized_vendor"))
        if normalized_vendor and normalized_vendor not in {"unknown", "generic", "generic_embedded_or_server"}:
            return normalized_vendor
        for driver in (
            payload.get("final_driver"),
            payload.get("chosen_driver"),
            event.get("final_driver"),
            event.get("chosen_driver"),
        ):
            vendor = OUIService.vendor_for_driver(str(driver or ""))
            if vendor:
                return cls._vendor_key(vendor)
        return ""

    @classmethod
    def _driver_from_event(cls, event: Dict[str, Any]) -> str:
        payload = dict(event.get("payload") or {})
        for driver in (
            payload.get("final_driver"),
            payload.get("chosen_driver"),
            event.get("final_driver"),
            event.get("chosen_driver"),
        ):
            value = str(driver or "").strip().lower()
            if value:
                return value
        return ""

    @classmethod
    def _neighbor_regex(cls, samples: List[str]) -> str:
        prefixes: List[str] = []
        for sample in samples:
            value = str(sample or "").strip()
            if not value:
                continue
            match = re.match(r"([A-Za-z]{2,6})[-_ ]?\d{2,4}", value)
            if not match:
                continue
            prefix = match.group(1).lower()
            if prefix not in prefixes:
                prefixes.append(prefix)
        if not prefixes:
            return ""
        escaped = [re.escape(prefix) for prefix in prefixes[:3]]
        return f"({'|'.join(escaped)})[-_ ]?\\d{{2,4}}"

    @classmethod
    def _seed_vendor_regex(cls, samples: List[str]) -> str:
        values: List[str] = []
        for sample in samples:
            value = cls._vendor_key(sample)
            if not value:
                continue
            if value not in values:
                values.append(value)
        if not values:
            return ""
        escaped = [re.escape(value) for value in values[:4]]
        return "|".join(escaped)

    @classmethod
    def build_recommendations(
        cls,
        *,
        benchmark: Dict[str, Any] | None,
        active_rules: List[Dict[str, Any]] | None = None,
    ) -> List[Dict[str, Any]]:
        benchmark = benchmark if isinstance(benchmark, dict) else {}
        active_rules = list(active_rules or [])
        by_vendor = list(benchmark.get("by_vendor") or [])
        by_driver = list(benchmark.get("by_driver") or [])
        opportunity_vendors = list(benchmark.get("opportunity_vendors") or [])
        opportunity_drivers = list(benchmark.get("opportunity_drivers") or [])

        active_rule_vendors = {
            str(item.get("vendor_family") or "").strip().lower()
            for item in active_rules
            if str(item.get("vendor_family") or "").strip()
        }
        driver_to_vendor = {
            str(item.get("driver") or "").strip().lower(): str(item.get("vendor") or "").strip().lower()
            for item in by_driver
            if str(item.get("driver") or "").strip()
        }

        recommendations: List[Dict[str, Any]] = []
        seen_keys = set()

        def add(kind: str, scope: str, title: str, description: str, severity: str, metrics: Dict[str, Any]) -> None:
            key = f"{kind}:{scope}:{title}"
            if key in seen_keys:
                return
            seen_keys.add(key)
            recommendations.append(
                {
                    "kind": kind,
                    "scope": scope,
                    "title": title,
                    "description": description,
                    "severity": severity,
                    "metrics": metrics,
                }
            )

        vendor_stats = {
            str(item.get("vendor") or "").strip().lower(): item
            for item in by_vendor
            if str(item.get("vendor") or "").strip()
        }

        for item in opportunity_vendors:
            vendor = str(item.get("vendor") or "").strip().lower()
            if not vendor:
                continue
            false_positive = int(item.get("false_positive") or 0)
            unknown_after_hint = int(item.get("unknown_after_hint") or 0)
            total = int(item.get("total") or 0)
            success_rate = float(item.get("success_rate_pct") or 0.0)
            if unknown_after_hint >= 1 and vendor not in active_rule_vendors:
                add(
                    "seed_rule_gap",
                    f"vendor:{vendor}",
                    f"{vendor} seed rule gap",
                    "Telemetry suggests this vendor repeatedly falls through hint-driven discovery without an active vendor-specific rule.",
                    "high" if unknown_after_hint >= 2 else "medium",
                    {
                        "total": total,
                        "unknown_after_hint": unknown_after_hint,
                        "success_rate_pct": success_rate,
                    },
                )
            if false_positive >= 1:
                add(
                    "vendor_false_positive",
                    f"vendor:{vendor}",
                    f"{vendor} false positive review",
                    "This vendor family is producing hint-driven misclassifications and should be reviewed for chipset or neighbor-pattern exceptions.",
                    "high" if false_positive >= 2 else "medium",
                    {
                        "total": total,
                        "false_positive": false_positive,
                        "success_rate_pct": success_rate,
                    },
                )

        for item in opportunity_drivers:
            driver = str(item.get("driver") or "").strip().lower()
            if not driver:
                continue
            false_positive = int(item.get("false_positive") or 0)
            unknown_after_hint = int(item.get("unknown_after_hint") or 0)
            total = int(item.get("total") or 0)
            success_rate = float(item.get("success_rate_pct") or 0.0)
            linked_vendor = driver_to_vendor.get(driver) or ""
            if false_positive >= 1:
                add(
                    "driver_false_positive",
                    f"driver:{driver}",
                    f"{driver} false positive hotspot",
                    "This driver is being selected too aggressively for hint-driven fallback and should have its score or matching conditions tightened.",
                    "high" if false_positive >= 2 else "medium",
                    {
                        "driver": driver,
                        "vendor": linked_vendor or None,
                        "total": total,
                        "false_positive": false_positive,
                        "success_rate_pct": success_rate,
                    },
                )
            if unknown_after_hint >= 1 and success_rate < 60.0:
                add(
                    "fixture_gap",
                    f"driver:{driver}",
                    f"{driver} fixture gap",
                    "Recent unknown-after-hint events suggest we need more real-output fixtures or neighbor-pattern rules for this driver family.",
                    "medium",
                    {
                        "driver": driver,
                        "vendor": linked_vendor or None,
                        "total": total,
                        "unknown_after_hint": unknown_after_hint,
                        "success_rate_pct": success_rate,
                    },
                )

        sorted_recommendations = sorted(
            recommendations,
            key=lambda item: (
                cls._severity_rank(str(item.get("severity") or "medium")),
                -int((item.get("metrics") or {}).get("false_positive", 0) or 0) - int((item.get("metrics") or {}).get("unknown_after_hint", 0) or 0),
                str(item.get("title") or ""),
            ),
        )
        return sorted_recommendations[:8]

    @classmethod
    def build_score_adjustments(
        cls,
        *,
        benchmark: Dict[str, Any] | None,
        active_rules: List[Dict[str, Any]] | None = None,
    ) -> List[Dict[str, Any]]:
        benchmark = benchmark if isinstance(benchmark, dict) else {}
        active_rules = [dict(item) for item in (active_rules or []) if isinstance(item, dict) and bool(item.get("is_active", True))]
        by_vendor = {
            str(item.get("vendor") or "").strip().lower(): dict(item)
            for item in list(benchmark.get("by_vendor") or [])
            if str(item.get("vendor") or "").strip()
        }
        by_driver = {
            str(item.get("driver") or "").strip().lower(): dict(item)
            for item in list(benchmark.get("by_driver") or [])
            if str(item.get("driver") or "").strip()
        }

        proposals: List[Dict[str, Any]] = []
        seen = set()

        def clamp(value: float, low: float, high: float) -> float:
            return max(low, min(high, value))

        for rule in active_rules:
            rule_key = str(rule.get("rule_key") or rule.get("rule_id") or "").strip()
            if not rule_key:
                continue
            vendor = str(rule.get("vendor_family") or "").strip().lower()
            drivers = [str(item or "").strip().lower() for item in list(rule.get("driver_overrides") or []) if str(item or "").strip()]
            vendor_stats = by_vendor.get(vendor, {})
            driver_stats = [by_driver.get(driver, {}) for driver in drivers if by_driver.get(driver)]
            total = int(vendor_stats.get("total") or sum(int(item.get("total") or 0) for item in driver_stats))
            if total <= 0:
                continue
            false_positive = int(vendor_stats.get("false_positive") or sum(int(item.get("false_positive") or 0) for item in driver_stats))
            unknown_after_hint = int(vendor_stats.get("unknown_after_hint") or max([int(item.get("unknown_after_hint") or 0) for item in driver_stats] or [0]))
            success_rate = float(
                vendor_stats.get("success_rate_pct")
                if "success_rate_pct" in vendor_stats
                else (sum(float(item.get("success_rate_pct") or 0.0) for item in driver_stats) / max(len(driver_stats), 1))
            )
            current_bonus = float(rule.get("score_bonus") or 0.0)
            delta = 0.0
            severity = "medium"
            reason = ""

            false_positive_rate = round((false_positive / max(total, 1)) * 100.0, 2)
            if false_positive >= 2 or false_positive_rate >= 20.0:
                delta = -0.06 if false_positive_rate < 35.0 else -0.1
                severity = "high" if false_positive_rate >= 25.0 or false_positive >= 3 else "medium"
                reason = "false_positive_pressure"
            elif success_rate >= 80.0 and false_positive == 0 and total >= 3:
                delta = 0.04
                severity = "low"
                reason = "high_confidence_success"
            elif unknown_after_hint >= 2 and false_positive == 0 and success_rate < 70.0:
                delta = 0.03
                severity = "medium"
                reason = "unknown_after_hint_pressure"
            else:
                continue

            proposed_bonus = round(clamp(current_bonus + delta, -0.25, 0.75), 3)
            if abs(proposed_bonus - current_bonus) < 0.015:
                continue

            dedupe_key = f"{rule_key}:{proposed_bonus}"
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            proposals.append(
                {
                    "kind": "score_adjustment",
                    "rule_key": rule_key,
                    "scope": f"rule:{rule_key}",
                    "vendor_family": vendor or None,
                    "drivers": drivers,
                    "title": f"{rule_key} score bonus {'increase' if proposed_bonus > current_bonus else 'decrease'}",
                    "description": (
                        "Recent telemetry suggests this rule should be tuned."
                        if reason != "high_confidence_success"
                        else "Recent hint successes support a slightly stronger score bonus for this rule."
                    ),
                    "severity": severity,
                    "reason": reason,
                    "current_score_bonus": round(current_bonus, 3),
                    "suggested_score_bonus": proposed_bonus,
                    "suggested_delta": round(proposed_bonus - current_bonus, 3),
                    "metrics": {
                        "total": total,
                        "success_rate_pct": round(success_rate, 2),
                        "false_positive": false_positive,
                        "false_positive_rate_pct": false_positive_rate,
                        "unknown_after_hint": unknown_after_hint,
                    },
                }
            )

        return sorted(
            proposals,
            key=lambda item: (
                cls._severity_rank(str(item.get("severity") or "medium")),
                -abs(float(item.get("suggested_delta") or 0.0)),
                str(item.get("rule_key") or ""),
            ),
        )[:8]

    @classmethod
    def build_alias_candidates(
        cls,
        *,
        telemetry_events: List[Dict[str, Any]] | None,
    ) -> List[Dict[str, Any]]:
        grouped: Dict[tuple[str, str, str], Dict[str, Any]] = {}
        for event in list(telemetry_events or []):
            payload = dict(event.get("payload") or {})
            raw_vendor = str(payload.get("raw_vendor") or "").strip()
            if not raw_vendor:
                continue
            if cls._chipset_token(raw_vendor):
                continue
            inferred_vendor = cls._infer_vendor_from_event(event)
            if not inferred_vendor:
                continue
            normalized_raw = OUIService.normalize_vendor_name(raw_vendor)
            if cls._vendor_key(normalized_raw) == inferred_vendor:
                continue
            driver = cls._driver_from_event(event)
            key = (cls._vendor_key(raw_vendor), inferred_vendor, driver)
            bucket = grouped.setdefault(
                key,
                {
                    "raw_vendor": raw_vendor,
                    "suggested_vendor_family": inferred_vendor,
                    "driver": driver or None,
                    "count": 0,
                    "events": [],
                },
            )
            bucket["count"] += 1
            bucket["events"].append(event)

        out: List[Dict[str, Any]] = []
        for bucket in grouped.values():
            if int(bucket.get("count") or 0) < 2:
                continue
            inferred = str(bucket.get("suggested_vendor_family") or "")
            raw_vendor = str(bucket.get("raw_vendor") or "")
            count = int(bucket.get("count") or 0)
            out.append(
                {
                    "kind": "alias_candidate",
                    "title": f"{raw_vendor} -> {inferred}",
                    "description": "Recent telemetry suggests this raw vendor string should be normalized into the same vendor family.",
                    "severity": "medium" if count < 4 else "high",
                    "raw_vendor": raw_vendor,
                    "suggested_vendor_family": inferred,
                    "driver": bucket.get("driver"),
                    "sample_count": count,
                }
            )
        return sorted(out, key=lambda item: (-int(item.get("sample_count") or 0), str(item.get("raw_vendor") or "")))[:6]

    @classmethod
    def build_seed_rule_drafts(
        cls,
        *,
        telemetry_events: List[Dict[str, Any]] | None,
        active_rules: List[Dict[str, Any]] | None = None,
    ) -> List[Dict[str, Any]]:
        active_rules = list(active_rules or [])
        existing_signatures = set()
        for rule in active_rules:
            vendor = cls._vendor_key(rule.get("vendor_family"))
            drivers = [cls._vendor_key(item) for item in list(rule.get("driver_overrides") or []) if cls._vendor_key(item)]
            raw_tokens = [cls._vendor_key(item) for item in list((rule.get("match_conditions") or {}).get("raw_vendor_contains") or []) if cls._vendor_key(item)]
            for driver in drivers or [""]:
                for token in raw_tokens or [""]:
                    existing_signatures.add((vendor, driver, token))

        grouped: Dict[tuple[str, str, str], Dict[str, Any]] = {}
        for event in list(telemetry_events or []):
            payload = dict(event.get("payload") or {})
            raw_vendor = str(payload.get("raw_vendor") or "").strip()
            chipset = cls._chipset_token(raw_vendor)
            if not chipset:
                continue
            inferred_vendor = cls._infer_vendor_from_event(event)
            driver = cls._driver_from_event(event)
            if not inferred_vendor or not driver:
                continue
            signature = (inferred_vendor, driver, chipset)
            if signature in existing_signatures:
                continue
            bucket = grouped.setdefault(
                signature,
                {
                    "vendor_family": inferred_vendor,
                    "driver": driver,
                    "chipset": chipset,
                    "count": 0,
                    "neighbor_names": [],
                    "seed_vendors": [],
                },
            )
            bucket["count"] += 1
            neighbor_name = str(payload.get("neighbor_name") or "").strip()
            if neighbor_name:
                bucket["neighbor_names"].append(neighbor_name)
            seed_vendor = str(payload.get("seed_vendor") or "").strip()
            if seed_vendor:
                bucket["seed_vendors"].append(seed_vendor)

        out: List[Dict[str, Any]] = []
        for bucket in grouped.values():
            count = int(bucket.get("count") or 0)
            if count < 2:
                continue
            vendor_family = str(bucket.get("vendor_family") or "")
            driver = str(bucket.get("driver") or "")
            chipset = str(bucket.get("chipset") or "")
            neighbor_regex = cls._neighbor_regex(list(bucket.get("neighbor_names") or []))
            seed_vendor_regex = cls._seed_vendor_regex(list(bucket.get("seed_vendors") or []))
            match_conditions: Dict[str, Any] = {
                "ssh_open": True,
                "raw_vendor_contains": [chipset],
            }
            if neighbor_regex:
                match_conditions["neighbor_name_regex"] = neighbor_regex
            if seed_vendor_regex:
                match_conditions["seed_vendor_regex"] = seed_vendor_regex
            out.append(
                {
                    "kind": "seed_rule_draft",
                    "title": f"{vendor_family} {chipset} seed rule draft",
                    "description": "Repeated chipset-based telemetry suggests a vendor-specific fallback rule should be added.",
                    "severity": "medium" if count < 4 else "high",
                    "sample_count": count,
                    "rule_key": f"draft-{vendor_family}-{chipset}-{driver}".replace("_", "-"),
                    "vendor_family": vendor_family,
                    "driver_overrides": [driver],
                    "match_conditions": match_conditions,
                }
            )
        return sorted(out, key=lambda item: (-int(item.get("sample_count") or 0), str(item.get("rule_key") or "")))[:6]

    @classmethod
    def build_false_positive_hotspots(
        cls,
        *,
        benchmark: Dict[str, Any] | None,
    ) -> List[Dict[str, Any]]:
        benchmark = benchmark if isinstance(benchmark, dict) else {}
        hotspots: List[Dict[str, Any]] = []
        for item in list(benchmark.get("by_driver") or []):
            total = int(item.get("total") or 0)
            false_positive = int(item.get("false_positive") or 0)
            success_rate = float(item.get("success_rate_pct") or 0.0)
            false_positive_rate = float(item.get("false_positive_rate_pct") or 0.0)
            unknown_after_hint = int(item.get("unknown_after_hint") or 0)
            if total < 3:
                continue
            if false_positive < 2 and false_positive_rate < 25.0:
                continue
            driver = str(item.get("driver") or "unknown")
            severity = "high" if false_positive >= 3 or false_positive_rate >= 35.0 else "medium"
            hotspots.append(
                {
                    "kind": "false_positive_hotspot",
                    "title": f"{driver} false-positive hotspot",
                    "description": "Recent hint outcomes show this driver still creates repeated false positives and should be reviewed or down-ranked.",
                    "severity": severity,
                    "driver": driver,
                    "metrics": {
                        "total": total,
                        "false_positive": false_positive,
                        "false_positive_rate_pct": round(false_positive_rate, 2),
                        "unknown_after_hint": unknown_after_hint,
                        "success_rate_pct": round(success_rate, 2),
                    },
                }
            )
        return sorted(
            hotspots,
            key=lambda item: (
                cls._severity_rank(str(item.get("severity") or "medium")),
                -int((item.get("metrics") or {}).get("false_positive") or 0),
                -float((item.get("metrics") or {}).get("false_positive_rate_pct") or 0.0),
                str(item.get("driver") or ""),
            ),
        )[:5]
