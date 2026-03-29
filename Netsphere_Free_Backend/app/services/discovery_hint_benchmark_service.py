from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict

from app.services.discovery_hint_telemetry_service import DiscoveryHintTelemetryService


class DiscoveryHintBenchmarkService:
    @classmethod
    def _summarize_items(cls, items: list[Dict[str, Any]]) -> Dict[str, Any]:
        total = len(items)
        success = 0
        false_positive = 0
        unknown_after_hint = 0
        by_vendor: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {"total": 0, "success": 0, "false_positive": 0, "unknown_after_hint": 0}
        )
        by_driver: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {"total": 0, "success": 0, "false_positive": 0, "unknown_after_hint": 0}
        )
        for item in items:
            event_type = str(item.get("event_type") or "").strip().lower()
            vendor = str(item.get("normalized_vendor") or "unknown").strip().lower() or "unknown"
            driver = str(item.get("final_driver") or item.get("chosen_driver") or "unknown").strip().lower() or "unknown"
            was_success = bool(item.get("success"))
            if was_success:
                success += 1
            if event_type == "hint_false_positive":
                false_positive += 1
                by_driver[driver]["false_positive"] += 1
            if event_type == "unknown_after_hint":
                unknown_after_hint += 1
                by_vendor[vendor]["unknown_after_hint"] += 1
                by_driver[driver]["unknown_after_hint"] += 1
            by_vendor[vendor]["total"] += 1
            by_driver[driver]["total"] += 1
            if was_success:
                by_vendor[vendor]["success"] += 1
                by_driver[driver]["success"] += 1
            if event_type == "hint_false_positive":
                by_vendor[vendor]["false_positive"] += 1

        attempted = max(total, 1)
        sorted_vendors = sorted(
            by_vendor.items(),
            key=lambda item: (-int(item[1]["total"]), -int(item[1]["success"]), item[0]),
        )
        sorted_drivers = sorted(
            by_driver.items(),
            key=lambda item: (-int(item[1]["total"]), -int(item[1]["success"]), item[0]),
        )
        opportunity_vendors = sorted(
            by_vendor.items(),
            key=lambda item: (
                -int(item[1]["unknown_after_hint"] + (item[1]["false_positive"] * 2)),
                -int(item[1]["total"]),
                item[0],
            ),
        )
        opportunity_drivers = sorted(
            by_driver.items(),
            key=lambda item: (
                -int(item[1]["unknown_after_hint"] + (item[1]["false_positive"] * 2)),
                -int(item[1]["total"]),
                item[0],
            ),
        )
        return {
            "summary": {
                "total": total,
                "success": success,
                "false_positive": false_positive,
                "unknown_after_hint": unknown_after_hint,
                "success_rate_pct": round((success / attempted) * 100.0, 2) if total else 0.0,
                "false_positive_rate_pct": round((false_positive / attempted) * 100.0, 2) if total else 0.0,
            },
            "by_vendor": [
                {
                    "vendor": vendor,
                    **stats,
                    "success_rate_pct": round((stats["success"] / max(stats["total"], 1)) * 100.0, 2),
                    "false_positive_rate_pct": round((stats["false_positive"] / max(stats["total"], 1)) * 100.0, 2),
                }
                for vendor, stats in sorted_vendors
            ],
            "by_driver": [
                {
                    "driver": driver,
                    **stats,
                    "success_rate_pct": round((stats["success"] / max(stats["total"], 1)) * 100.0, 2),
                    "false_positive_rate_pct": round((stats["false_positive"] / max(stats["total"], 1)) * 100.0, 2),
                }
                for driver, stats in sorted_drivers
            ],
            "opportunity_vendors": [
                {
                    "vendor": vendor,
                    **stats,
                    "success_rate_pct": round((stats["success"] / max(stats["total"], 1)) * 100.0, 2),
                }
                for vendor, stats in opportunity_vendors[:5]
                if int(stats["unknown_after_hint"] + stats["false_positive"]) > 0
            ],
            "opportunity_drivers": [
                {
                    "driver": driver,
                    **stats,
                    "success_rate_pct": round((stats["success"] / max(stats["total"], 1)) * 100.0, 2),
                }
                for driver, stats in opportunity_drivers[:5]
                if int(stats["unknown_after_hint"] + stats["false_positive"]) > 0
            ],
        }

    @classmethod
    def summarize_recent(cls, *, limit: int = 500) -> Dict[str, Any]:
        items = DiscoveryHintTelemetryService.list_recent(limit=limit, include_payload=False)
        return cls._summarize_items(items)

    @classmethod
    def summarize_trend(cls, *, window: int = 125) -> Dict[str, Any]:
        window = max(2, min(int(window or 125), 1000))
        items = DiscoveryHintTelemetryService.list_recent(limit=window * 2, include_payload=False)
        current_items = list(items[:window])
        previous_items = list(items[window : window * 2])
        current = cls._summarize_items(current_items)
        previous = cls._summarize_items(previous_items)
        current_summary = dict(current.get("summary") or {})
        previous_summary = dict(previous.get("summary") or {})
        return {
            "window": window,
            "current": current_summary,
            "previous": previous_summary,
            "delta": {
                "total": int(current_summary.get("total") or 0) - int(previous_summary.get("total") or 0),
                "success": int(current_summary.get("success") or 0) - int(previous_summary.get("success") or 0),
                "false_positive": int(current_summary.get("false_positive") or 0)
                - int(previous_summary.get("false_positive") or 0),
                "unknown_after_hint": int(current_summary.get("unknown_after_hint") or 0)
                - int(previous_summary.get("unknown_after_hint") or 0),
                "success_rate_pct": round(
                    float(current_summary.get("success_rate_pct") or 0.0)
                    - float(previous_summary.get("success_rate_pct") or 0.0),
                    2,
                ),
                "false_positive_rate_pct": round(
                    float(current_summary.get("false_positive_rate_pct") or 0.0)
                    - float(previous_summary.get("false_positive_rate_pct") or 0.0),
                    2,
                ),
            },
        }
