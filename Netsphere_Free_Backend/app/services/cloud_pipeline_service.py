from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Sequence

from sqlalchemy.orm import Session

from app.models.cloud import CloudAccount, CloudResource
from app.models.device import EventLog
from app.models.settings import SystemSetting
from app.schemas.cloud import (
    CloudPipelineAccountResult,
    CloudPipelineRunRequest,
    CloudPipelineRunResponse,
)
from app.services.cloud_normalization_service import CloudNormalizationService
from app.services.cloud_service import CloudScanner
from app.services.hybrid_topology_service import HybridTopologyService
from app.services.license_policy_service import LicensePolicyViolation


class CloudPipelineService:
    KPI_EVENT_ID = "CLOUD_PIPELINE_KPI"

    @staticmethod
    def _idempotency_claim(db: Session, *, key: str, ttl_seconds: int = 1200) -> bool:
        now = datetime.utcnow()
        idempotency_key = f"cloud_pipeline_idemp:{str(key).strip()}"
        row = db.query(SystemSetting).filter(SystemSetting.key == idempotency_key).first()
        if row and row.value:
            try:
                expiry = datetime.fromisoformat(str(row.value))
                if expiry > now:
                    return False
            except Exception:
                pass
        lock_until = now + timedelta(seconds=max(60, int(ttl_seconds)))
        if row is None:
            row = SystemSetting(key=idempotency_key, value=lock_until.isoformat(), description=idempotency_key, category="system")
        else:
            row.value = lock_until.isoformat()
        db.add(row)
        db.commit()
        return True

    @staticmethod
    def _first_failed_check_message(payload: Dict[str, object] | None) -> str | None:
        if not isinstance(payload, dict):
            return None
        checks = payload.get("checks")
        if not isinstance(checks, list):
            return None
        for item in checks:
            if isinstance(item, dict) and not bool(item.get("ok")):
                msg = str(item.get("message") or "").strip()
                if msg:
                    return msg
        return None

    @staticmethod
    def _normalize_provider_counts(
        db: Session,
        *,
        tenant_id: int | None,
        account_ids: Sequence[int],
    ) -> Dict[str, int]:
        if not account_ids:
            return {}
        q = db.query(CloudResource, CloudAccount).join(CloudAccount, CloudAccount.id == CloudResource.account_id)
        if tenant_id is not None:
            q = q.filter(CloudAccount.tenant_id == tenant_id)
        q = q.filter(CloudResource.account_id.in_(list(account_ids)))
        rows = q.all()
        counts: Dict[str, int] = {}
        for _res, acc in rows:
            group = CloudNormalizationService.provider_group(acc.provider)
            counts[group] = int(counts.get(group, 0)) + 1
        return dict(sorted(counts.items(), key=lambda kv: kv[0]))

    @staticmethod
    def _safe_int(value: object, default: int = 0) -> int:
        try:
            return int(value)  # type: ignore[arg-type]
        except Exception:
            return int(default)

    @classmethod
    def _link_count(cls, stats: Dict[str, int] | None) -> int:
        if not isinstance(stats, dict):
            return 0
        return cls._safe_int(stats.get("created_links")) + cls._safe_int(stats.get("updated_links"))

    @classmethod
    def _low_conf_count(cls, stats: Dict[str, int] | None) -> int:
        if not isinstance(stats, dict):
            return 0
        return cls._safe_int(stats.get("low_confidence_enqueued"))

    @classmethod
    def _emit_kpi_event(cls, db: Session, *, payload: Dict[str, object]) -> None:
        try:
            db.add(
                EventLog(
                    device_id=None,
                    severity="info" if str(payload.get("status") or "").lower() == "ok" else "warning",
                    event_id=cls.KPI_EVENT_ID,
                    message=json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str),
                    source="CloudPipeline",
                    timestamp=datetime.utcnow(),
                )
            )
            db.commit()
        except Exception:
            db.rollback()

    @classmethod
    def run(
        cls,
        db: Session,
        *,
        tenant_id: int | None,
        owner_id: int,
        req: CloudPipelineRunRequest,
    ) -> CloudPipelineRunResponse:
        started_at = datetime.utcnow()
        idempotency_key = str(req.idempotency_key or "").strip() or None
        if idempotency_key and (not bool(req.force)):
            if not cls._idempotency_claim(db, key=idempotency_key):
                return CloudPipelineRunResponse(
                    status="skipped_duplicate",
                    idempotency_key=idempotency_key,
                    message="Duplicate pipeline execution blocked by idempotency key.",
                )

        q = db.query(CloudAccount).filter(CloudAccount.is_active == True)  # noqa: E712
        if tenant_id is not None:
            q = q.filter(CloudAccount.tenant_id == tenant_id)

        target_ids: List[int] = []
        if isinstance(req.account_ids, list) and req.account_ids:
            for v in req.account_ids:
                try:
                    target_ids.append(int(v))
                except Exception:
                    continue
        if target_ids:
            q = q.filter(CloudAccount.id.in_(sorted(set(target_ids))))

        accounts = q.order_by(CloudAccount.id.asc()).all()
        if not accounts:
            return CloudPipelineRunResponse(
                status="no_accounts",
                idempotency_key=idempotency_key,
                message="No active cloud accounts found for pipeline run.",
            )

        results: List[CloudPipelineAccountResult] = []
        scanned_resources = 0
        failed_accounts = 0
        hard_stop = False

        for acc in accounts:
            row = CloudPipelineAccountResult(account_id=int(acc.id), provider=str(acc.provider or ""))
            scanner = CloudScanner(db, acc)
            preflight_ok = True

            if bool(req.preflight):
                try:
                    preflight_payload = asyncio.run(scanner.preflight())
                    status = str((preflight_payload or {}).get("status") or "unknown").strip().lower()
                    row.preflight_status = status
                    row.preflight_message = str(
                        (preflight_payload or {}).get("summary")
                        or cls._first_failed_check_message(preflight_payload)
                        or ""
                    ) or None
                    preflight_ok = status == "ok"
                except Exception as e:
                    preflight_ok = False
                    row.preflight_status = "failed"
                    row.preflight_message = f"{type(e).__name__}: {e}"

            if not preflight_ok:
                row.scan_status = "skipped"
                row.message = "preflight_failed"
                failed_accounts += 1
                results.append(row)
                if not bool(req.continue_on_error):
                    hard_stop = True
                    break
                continue

            try:
                scan_result = asyncio.run(scanner.scan())
                count = len(scan_result or [])
                row.scan_status = "ok"
                row.scan_count = int(count)
                scanned_resources += int(count)
            except Exception as e:
                row.scan_status = "failed"
                row.message = f"{type(e).__name__}: {e}"
                failed_accounts += 1
                if not bool(req.continue_on_error):
                    results.append(row)
                    hard_stop = True
                    break
            results.append(row)

        hybrid_build = None
        hybrid_infer = None
        message_parts: List[str] = []

        try:
            if bool(req.include_hybrid_build):
                hybrid_build = HybridTopologyService.build_cloud_peer_links(
                    db,
                    tenant_id=tenant_id,
                    owner_id=int(owner_id),
                )
            if bool(req.include_hybrid_infer):
                hybrid_infer = HybridTopologyService.build_inferred_cloud_links(
                    db,
                    tenant_id=tenant_id,
                    owner_id=int(owner_id),
                    enrich=bool(req.enrich_inferred),
                )
        except LicensePolicyViolation:
            raise
        except Exception as e:
            message_parts.append(f"hybrid_pipeline_error: {type(e).__name__}: {e}")
            if not bool(req.continue_on_error):
                hard_stop = True

        normalized_by_provider = cls._normalize_provider_counts(
            db,
            tenant_id=tenant_id,
            account_ids=[int(a.id) for a in accounts],
        )

        status = "ok"
        if hard_stop and failed_accounts > 0 and scanned_resources == 0:
            status = "failed"
        elif failed_accounts > 0:
            status = "partial"

        message = " ".join([m for m in message_parts if str(m).strip()]).strip() or None
        response = CloudPipelineRunResponse(
            status=status,
            idempotency_key=idempotency_key,
            total_accounts=len(accounts),
            scanned_resources=int(scanned_resources),
            failed_accounts=int(failed_accounts),
            accounts=results,
            normalized_by_provider=normalized_by_provider,
            hybrid_build=hybrid_build,
            hybrid_infer=hybrid_infer,
            message=message,
        )

        reflected_links = cls._link_count(hybrid_build) + cls._link_count(hybrid_infer)
        low_confidence_queued = cls._low_conf_count(hybrid_build) + cls._low_conf_count(hybrid_infer)
        duration_sec = max(0.0, float((datetime.utcnow() - started_at).total_seconds()))
        cls._emit_kpi_event(
            db,
            payload={
                "tenant_id": tenant_id,
                "owner_id": int(owner_id),
                "status": status,
                "idempotency_key": idempotency_key,
                "total_accounts": int(len(accounts)),
                "failed_accounts": int(failed_accounts),
                "scanned_resources": int(scanned_resources),
                "normalized_by_provider": dict(normalized_by_provider),
                "reflected_links": int(reflected_links),
                "low_confidence_queued": int(low_confidence_queued),
                "first_map_seconds": round(duration_sec, 3),
                "created_at": datetime.utcnow().isoformat(),
            },
        )
        return response
