#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import MetaData, Table, delete, inspect as sa_inspect, insert, select

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import SessionLocal
from app.services.change_execution_service import ChangeExecutionService
from app.services.closed_loop_service import ClosedLoopService

try:
    from app.core import config as _APP_CONFIG
except Exception:
    _APP_CONFIG = None


SAMPLE_PROFILES: dict[str, dict[str, int]] = {
    "local": {
        "device_count": 8,
        "discovery_jobs": 30,
        "change_events": 100,
        "northbound_deliveries": 520,
        "autonomy_issues": 20,
        "autonomy_actions": 20,
    },
    "ci": {
        "device_count": 4,
        "discovery_jobs": 8,
        "change_events": 20,
        "northbound_deliveries": 40,
        "autonomy_issues": 6,
        "autonomy_actions": 6,
    },
}

SAMPLE_PREFIX = "ops-kpi-sample"
ISSUE_TITLE_PREFIX = "OpsKPI Sample Issue"
DISCOVERY_LOG_MARKER = "ops_kpi_sample_collection"
CHANGE_EVENT_SOURCE = "OpsKpiSample"
NORTHBOUND_EVENT_SOURCE = "OpsKpiSample"
AUTONOMY_SOURCE = "ops_kpi_sample"
SIGNAL_EVENT_SOURCE = "OpsKpiSample"


def _ensure_runtime() -> None:
    if not str(os.environ.get("FIELD_ENCRYPTION_KEY") or "").strip() and not str(os.environ.get("SECRET_KEY") or "").strip():
        derived_secret = str(getattr(_APP_CONFIG, "SECRET_KEY", "") or "").strip() if _APP_CONFIG is not None else ""
        if derived_secret:
            os.environ["SECRET_KEY"] = derived_secret


def _reflect_table(db: Any, name: str) -> Table:
    return Table(str(name), MetaData(), autoload_with=db.bind)


def _table_columns(db: Any, table_name: str) -> set[str]:
    try:
        inspector = sa_inspect(db.bind)
        return {str(col.get("name") or "").strip() for col in inspector.get_columns(str(table_name))}
    except Exception:
        return set()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _filter_row_for_columns(row: dict[str, Any], columns: set[str]) -> dict[str, Any]:
    return {key: value for key, value in dict(row or {}).items() if str(key) in columns}


def _cleanup_existing_samples(db: Any) -> dict[str, int]:
    summary = {
        "discovery_jobs_deleted": 0,
        "issues_deleted": 0,
        "event_logs_deleted": 0,
    }

    issue_table = _reflect_table(db, "issues")
    event_table = _reflect_table(db, "event_logs")
    discovery_table = _reflect_table(db, "discovery_jobs")
    discovered_table = _reflect_table(db, "discovered_devices")
    snapshot_table = _reflect_table(db, "topology_snapshots")

    discovery_job_ids = [
        int(row[0])
        for row in db.execute(
            select(discovery_table.c.id).where(discovery_table.c.logs == DISCOVERY_LOG_MARKER)
        ).all()
    ]
    if discovery_job_ids:
        db.execute(delete(discovered_table).where(discovered_table.c.job_id.in_(discovery_job_ids)))
        db.execute(delete(snapshot_table).where(snapshot_table.c.job_id.in_(discovery_job_ids)))
        deleted = db.execute(delete(discovery_table).where(discovery_table.c.id.in_(discovery_job_ids)))
        summary["discovery_jobs_deleted"] = int(getattr(deleted, "rowcount", 0) or 0)

    issue_title_col = issue_table.c.title if "title" in issue_table.c else None
    if issue_title_col is not None:
        deleted = db.execute(delete(issue_table).where(issue_title_col.like(f"{ISSUE_TITLE_PREFIX}%")))
        summary["issues_deleted"] = int(getattr(deleted, "rowcount", 0) or 0)

    event_deleted = 0
    event_deleted += int(
        getattr(
            db.execute(
                delete(event_table).where(
                    event_table.c.event_id == ChangeExecutionService.CHANGE_KPI_EVENT_ID,
                    event_table.c.source == CHANGE_EVENT_SOURCE,
                )
            ),
            "rowcount",
            0,
        )
        or 0
    )
    event_deleted += int(
        getattr(
            db.execute(
                delete(event_table).where(
                    event_table.c.event_id == "KPI_SAMPLE_SIGNAL",
                    event_table.c.source == SIGNAL_EVENT_SOURCE,
                )
            ),
            "rowcount",
            0,
        )
        or 0
    )
    event_deleted += int(
        getattr(
            db.execute(
                delete(event_table).where(
                    event_table.c.event_id == "NORTHBOUND_WEBHOOK_DELIVERY",
                    event_table.c.source == NORTHBOUND_EVENT_SOURCE,
                )
            ),
            "rowcount",
            0,
        )
        or 0
    )

    closed_loop_rows = db.execute(
        select(event_table.c.id, event_table.c.message).where(event_table.c.event_id == "CLOSED_LOOP_EVAL_SUMMARY")
    ).all()
    delete_ids = []
    for row in closed_loop_rows:
        try:
            payload = json.loads(str(getattr(row, "message", None) or row[1] or ""))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        if str(payload.get("source") or "").strip().lower() == AUTONOMY_SOURCE:
            delete_ids.append(int(getattr(row, "id", None) or row[0]))
    if delete_ids:
        event_deleted += int(
            getattr(db.execute(delete(event_table).where(event_table.c.id.in_(delete_ids))), "rowcount", 0) or 0
        )
    summary["event_logs_deleted"] = int(event_deleted)
    db.commit()
    return summary


def _get_or_create_sample_devices(db: Any, count: int) -> list[int]:
    device_table = _reflect_table(db, "devices")
    device_cols = _table_columns(db, "devices")
    existing = db.execute(
        select(device_table.c.id).where(device_table.c.name.like(f"{SAMPLE_PREFIX}-dev-%")).order_by(device_table.c.id.asc())
    ).all()
    out = [int(getattr(row, "id", None) or row[0]) for row in existing]
    next_index = len(out) + 1
    while len(out) < int(count):
        idx = next_index
        next_index += 1
        row = _filter_row_for_columns(
            {
                "name": f"{SAMPLE_PREFIX}-dev-{idx}",
                "hostname": f"{SAMPLE_PREFIX}-dev-{idx}",
                "ip_address": f"10.254.{((idx - 1) // 200) + 1}.{((idx - 1) % 200) + 1}",
                "snmp_community": "public",
                "snmp_version": "v2c",
                "snmp_port": 161,
                "ssh_username": "admin",
                "ssh_password": "",
                "ssh_port": 22,
                "enable_password": "",
                "polling_interval": 60,
                "status_interval": 60,
                "model": "CSR1000V",
                "os_version": "17.9",
                "serial_number": f"{SAMPLE_PREFIX.upper()}-{idx:04d}",
                "device_type": "cisco_ios",
                "gnmi_port": 57400,
                "telemetry_mode": "hybrid",
                "role": "access",
                "status": "online",
                "reachability_status": "reachable",
                "uptime": "5d 12h 0m",
                "variables": {},
                "latest_parsed_data": {},
            },
            device_cols,
        )
        inserted = db.execute(insert(device_table).values(**row))
        out.append(int(inserted.inserted_primary_key[0]))
    db.commit()
    return out[: int(count)]


def _seed_discovery_samples(db: Any, *, jobs_count: int, device_ids: list[int]) -> dict[str, int]:
    discovery_table = _reflect_table(db, "discovery_jobs")
    discovery_cols = _table_columns(db, "discovery_jobs")
    discovered_table = _reflect_table(db, "discovered_devices")
    discovered_cols = _table_columns(db, "discovered_devices")
    snapshot_table = _reflect_table(db, "topology_snapshots")
    snapshot_cols = _table_columns(db, "topology_snapshots")

    created = 0
    discovered_total = 0
    approved_total = 0
    existing_total = 0
    ignored_total = 0
    now = _utcnow()
    for idx in range(int(jobs_count)):
        created_at = now - timedelta(hours=(idx % 48), minutes=idx)
        completed_at = created_at + timedelta(seconds=45)
        job_row = _filter_row_for_columns(
            {
                "cidr": f"10.{200 + (idx % 20)}.{idx % 255}.0/24",
                "status": "completed",
                "snmp_community": "public",
                "snmp_version": "v2c",
                "snmp_port": 161,
                "total_ips": 20,
                "scanned_ips": 20,
                "created_at": created_at,
                "completed_at": completed_at,
                "logs": DISCOVERY_LOG_MARKER,
            },
            discovery_cols,
        )
        inserted = db.execute(insert(discovery_table).values(**job_row))
        job_id = int(inserted.inserted_primary_key[0])

        for host_idx in range(20):
            if host_idx < 17:
                status = "approved"
                matched_device_id = None
                approved_total += 1
            elif host_idx < 19:
                status = "existing"
                matched_device_id = int(device_ids[host_idx % len(device_ids)])
                existing_total += 1
            else:
                status = "ignored"
                matched_device_id = None
                ignored_total += 1
            row = _filter_row_for_columns(
                {
                    "job_id": job_id,
                    "ip_address": f"172.{20 + (idx % 10)}.{(idx % 200) + 1}.{host_idx + 1}",
                    "hostname": f"{SAMPLE_PREFIX}-disc-{idx + 1}-{host_idx + 1}",
                    "vendor": "Cisco",
                    "model": "CSR1000V",
                    "os_version": "17.9",
                    "snmp_status": "reachable",
                    "device_type": "cisco_ios",
                    "sys_object_id": "1.3.6.1.4.1.9.1.1208",
                    "sys_descr": "Ops KPI sample discovery device",
                    "vendor_confidence": 0.95,
                    "chassis_candidate": False,
                    "issues": [],
                    "evidence": {"sample": True},
                    "matched_device_id": matched_device_id,
                    "status": status,
                },
                discovered_cols,
            )
            db.execute(insert(discovered_table).values(**row))
            discovered_total += 1

        db.execute(
            insert(snapshot_table).values(
                **_filter_row_for_columns(
                    {
                        "site_id": None,
                        "job_id": job_id,
                        "label": f"{SAMPLE_PREFIX}-topology-{idx + 1}",
                        "node_count": 20,
                        "link_count": 19,
                        "nodes_json": "[]",
                        "links_json": "[]",
                        "metadata_json": json.dumps({"sample": True}, separators=(",", ":")),
                        "created_at": created_at + timedelta(seconds=20 + (idx % 5)),
                    },
                    snapshot_cols,
                )
            )
        )
        created += 1
    db.commit()
    return {
        "jobs": int(created),
        "discovered": int(discovered_total),
        "approved": int(approved_total),
        "existing": int(existing_total),
        "ignored": int(ignored_total),
    }


def _seed_change_samples(db: Any, *, event_count: int, device_ids: list[int]) -> dict[str, int]:
    if int(event_count) <= 0:
        return {"emitted": 0, "skipped": 0}
    rows: list[dict[str, Any]] = []
    failure_index = int(event_count) - 1 if int(event_count) >= 100 else -1
    for idx in range(int(event_count)):
        device_id = int(device_ids[idx % len(device_ids)])
        approval_id = 700000 + idx
        execution_id = f"{SAMPLE_PREFIX}-change-{idx + 1}"
        if idx == failure_index:
            rows.append(
                {
                    "device_id": device_id,
                    "status": "post_check_failed",
                    "approval_id": approval_id,
                    "execution_id": execution_id,
                    "wave": 1 + (idx // 10),
                    "post_check": {"ok": False},
                    "rollback_attempted": True,
                    "rollback_success": True,
                    "rollback_duration_ms": 1200,
                    "failure_cause": "post_check_failed",
                }
            )
        else:
            rows.append(
                {
                    "device_id": device_id,
                    "status": "success",
                    "approval_id": approval_id,
                    "execution_id": execution_id,
                    "wave": 1 + (idx // 10),
                }
            )
    result = ChangeExecutionService.emit_change_kpi_events(
        db,
        rows=rows,
        change_type="ops_kpi_sample",
        source=CHANGE_EVENT_SOURCE,
        commit=False,
    )
    db.commit()
    return {
        "emitted": int(result.get("emitted") or 0),
        "skipped": int(result.get("skipped") or 0),
    }


def _seed_northbound_samples(db: Any, *, delivery_count: int) -> dict[str, int]:
    if int(delivery_count) <= 0:
        return {"deliveries": 0, "success": 0, "failed": 0}
    event_table = _reflect_table(db, "event_logs")
    event_cols = _table_columns(db, "event_logs")
    now = _utcnow()
    failed = min(4, max(1, int(delivery_count) // 100))
    success = max(0, int(delivery_count) - int(failed))
    modes = ("jira", "servicenow", "splunk", "elastic")
    rows = []
    for idx in range(int(delivery_count)):
        is_failed = idx >= success
        rows.append(
            _filter_row_for_columns(
                {
                    "device_id": None,
                    "severity": "warning" if is_failed else "info",
                    "event_id": "NORTHBOUND_WEBHOOK_DELIVERY",
                    "message": json.dumps(
                        {
                            "status": "failed" if is_failed else "ok",
                            "mode": modes[idx % len(modes)],
                            "event_type": "sample",
                            "attempts": 2 if is_failed else 1,
                            "status_code": 503 if is_failed else 202,
                            "failure_cause": "timeout" if is_failed else None,
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    "source": NORTHBOUND_EVENT_SOURCE,
                    "timestamp": now - timedelta(minutes=min(idx, 600)),
                },
                event_cols,
            )
        )
    if rows:
        db.execute(insert(event_table), rows)
        db.commit()
    return {
        "deliveries": int(delivery_count),
        "success": int(success),
        "failed": int(failed),
    }


def _seed_issue_samples(db: Any, *, issue_count: int, device_ids: list[int]) -> dict[str, int]:
    if int(issue_count) <= 0:
        return {"issues_created": 0, "signals_created": 0}
    issue_table = _reflect_table(db, "issues")
    issue_cols = _table_columns(db, "issues")
    event_table = _reflect_table(db, "event_logs")
    now = _utcnow()

    issue_rows = []
    signal_rows = []
    for idx in range(int(issue_count)):
        device_id = int(device_ids[idx % len(device_ids)])
        created_at = now - timedelta(minutes=(idx * 3) + 2)
        issue_row: dict[str, Any] = {}
        if "device_id" in issue_cols:
            issue_row["device_id"] = device_id
        if "title" in issue_cols:
            issue_row["title"] = f"{ISSUE_TITLE_PREFIX} #{idx + 1}"
        if "description" in issue_cols:
            issue_row["description"] = "Ops KPI sample issue"
        if "severity" in issue_cols:
            issue_row["severity"] = "critical" if idx % 5 == 0 else "warning"
        if "status" in issue_cols:
            issue_row["status"] = "active"
        if "category" in issue_cols:
            issue_row["category"] = "performance"
        if "is_read" in issue_cols:
            issue_row["is_read"] = True
        if "created_at" in issue_cols:
            issue_row["created_at"] = created_at
        if "resolved_at" in issue_cols:
            issue_row["resolved_at"] = created_at + timedelta(minutes=5)
        issue_rows.append(issue_row)
        signal_rows.append(
            {
                "device_id": device_id,
                "severity": "critical" if idx % 5 == 0 else "warning",
                "event_id": "KPI_SAMPLE_SIGNAL",
                "message": "Ops KPI sample precursor signal",
                "source": SIGNAL_EVENT_SOURCE,
                "timestamp": created_at - timedelta(seconds=120),
            }
        )
    if issue_rows:
        db.execute(issue_table.insert(), issue_rows)
    if signal_rows:
        db.execute(event_table.insert(), signal_rows)
    db.commit()
    return {
        "issues_created": len(issue_rows),
        "signals_created": len(signal_rows),
    }


def _seed_autonomy_actions(db: Any, *, action_count: int, device_ids: list[int]) -> dict[str, int]:
    if int(action_count) <= 0:
        return {"events": 0, "approvals_opened": 0}
    approvals_opened = max(0, int(round(int(action_count) * 0.25)))
    for idx in range(int(action_count)):
        device_id = int(device_ids[idx % len(device_ids)])
        decisions = [{"approval_id": 900000 + idx}] if idx < approvals_opened else []
        ClosedLoopService.emit_evaluation_summary(
            db,
            result={
                "triggered": 1,
                "executed": 1,
                "blocked": 0,
                "rules_total": 1,
                "auto_execute_enabled": True,
                "decisions": decisions,
            },
            dry_run=False,
            source=AUTONOMY_SOURCE,
            device_id=device_id,
            commit=False,
        )
    db.commit()
    return {
        "events": int(action_count),
        "approvals_opened": int(approvals_opened),
    }


def run_ops_kpi_sample_collection(
    *,
    profile: str,
    cleanup: bool = True,
    discovery_jobs: int | None = None,
    change_events: int | None = None,
    northbound_deliveries: int | None = None,
    autonomy_issues: int | None = None,
    autonomy_actions: int | None = None,
    device_count: int | None = None,
) -> dict[str, Any]:
    _ensure_runtime()
    normalized_profile = str(profile or "local").strip().lower() or "local"
    if normalized_profile not in SAMPLE_PROFILES:
        raise ValueError(f"Unsupported sample profile: {normalized_profile}")
    spec = SAMPLE_PROFILES[normalized_profile]
    db = SessionLocal()
    try:
        cleanup_summary = _cleanup_existing_samples(db) if cleanup else {}
        devices = _get_or_create_sample_devices(db, int(device_count or spec["device_count"]))
        discovery_summary = _seed_discovery_samples(
            db,
            jobs_count=int(discovery_jobs or spec["discovery_jobs"]),
            device_ids=devices,
        )
        change_summary = _seed_change_samples(
            db,
            event_count=int(change_events or spec["change_events"]),
            device_ids=devices,
        )
        northbound_summary = _seed_northbound_samples(
            db,
            delivery_count=int(northbound_deliveries or spec["northbound_deliveries"]),
        )
        issue_summary = _seed_issue_samples(
            db,
            issue_count=int(autonomy_issues or spec["autonomy_issues"]),
            device_ids=devices,
        )
        autonomy_summary = _seed_autonomy_actions(
            db,
            action_count=int(autonomy_actions or spec["autonomy_actions"]),
            device_ids=devices,
        )
        return {
            "status": "ok",
            "profile": normalized_profile,
            "cleanup": cleanup_summary,
            "devices": {"count": len(devices)},
            "discovery": discovery_summary,
            "change": change_summary,
            "northbound": northbound_summary,
            "autonomy": {
                **issue_summary,
                **autonomy_summary,
            },
        }
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create self-contained local Ops KPI sample evidence for discovery/change/autonomy.",
    )
    parser.add_argument("--profile", default="local", choices=sorted(SAMPLE_PROFILES.keys()))
    parser.add_argument("--no-cleanup", action="store_true", help="Do not remove previous sample evidence before inserting.")
    parser.add_argument("--device-count", type=int, default=None)
    parser.add_argument("--discovery-jobs", type=int, default=None)
    parser.add_argument("--change-events", type=int, default=None)
    parser.add_argument("--northbound-deliveries", type=int, default=None)
    parser.add_argument("--autonomy-issues", type=int, default=None)
    parser.add_argument("--autonomy-actions", type=int, default=None)
    args = parser.parse_args()

    result = run_ops_kpi_sample_collection(
        profile=str(args.profile or "local"),
        cleanup=not bool(args.no_cleanup),
        discovery_jobs=args.discovery_jobs,
        change_events=args.change_events,
        northbound_deliveries=args.northbound_deliveries,
        autonomy_issues=args.autonomy_issues,
        autonomy_actions=args.autonomy_actions,
        device_count=args.device_count,
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
