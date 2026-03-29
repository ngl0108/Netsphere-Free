from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session, joinedload

from app.models.device import ComplianceReport
from app.services.release_evidence_service import build_release_evidence_bundle
from app.services.report_export_service import build_compliance_pdf, build_compliance_xlsx
from app.services.support_bundle_service import SupportBundleService

BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_ROOT.parent

PRO_RUNBOOKS: tuple[tuple[Path, str], ...] = (
    (PROJECT_ROOT / "docs" / "PRO_BASELINE_RUNBOOK.md", "runbooks/PRO_BASELINE_RUNBOOK.md"),
    (PROJECT_ROOT / "docs" / "CLOUD_PRO_EXECUTION_RUNBOOK.md", "runbooks/CLOUD_PRO_EXECUTION_RUNBOOK.md"),
    (PROJECT_ROOT / "docs" / "CLOUD_PRO_AWS_PILOT_RUNBOOK.md", "runbooks/CLOUD_PRO_AWS_PILOT_RUNBOOK.md"),
    (PROJECT_ROOT / "docs" / "INSTALL_UPGRADE_RECOVERY_RUNBOOK.md", "runbooks/INSTALL_UPGRADE_RECOVERY_RUNBOOK.md"),
    (PROJECT_ROOT / "docs" / "RELEASE_GATE_RUNBOOK.md", "runbooks/RELEASE_GATE_RUNBOOK.md"),
    (PROJECT_ROOT / "docs" / "BRANCH_PROTECTION_CHECKLIST.md", "runbooks/BRANCH_PROTECTION_CHECKLIST.md"),
    (PROJECT_ROOT / "docs" / "ALERTING_OPERATIONS_POLICY.md", "runbooks/ALERTING_OPERATIONS_POLICY.md"),
    (PROJECT_ROOT / "docs" / "VENDOR_SUPPORT_POLICY.md", "runbooks/VENDOR_SUPPORT_POLICY.md"),
    (PROJECT_ROOT / "docs" / "LICENSE_SIGNING.md", "runbooks/LICENSE_SIGNING.md"),
    (
        PROJECT_ROOT / "docs" / "operational-validation" / "REAL_DEVICE_ACCEPTANCE_RUNBOOK.md",
        "runbooks/REAL_DEVICE_ACCEPTANCE_RUNBOOK.md",
    ),
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _build_compliance_payload(db: Session) -> list[dict[str, Any]]:
    reports = (
        db.query(ComplianceReport)
        .options(joinedload(ComplianceReport.device))
        .order_by(ComplianceReport.last_checked.desc().nullslast(), ComplianceReport.id.desc())
        .all()
    )
    payload: list[dict[str, Any]] = []
    for row in reports:
        payload.append(
            {
                "device_id": row.device_id,
                "device_name": row.device.name if row.device else None,
                "status": row.status,
                "score": row.match_percentage,
                "last_checked": row.last_checked.isoformat() if getattr(row, "last_checked", None) else None,
                "details": row.details if getattr(row, "details", None) else row.diff_content,
            }
        )
    return payload


def _build_readme(now: datetime, compliance_reports: int) -> str:
    generated_at = now.isoformat()
    return "\n".join(
        [
            "NetSphere Pro Operator Package",
            "==============================",
            "",
            f"Generated at: {generated_at}",
            "",
            "Included artifacts:",
            "- support/support_bundle.zip",
            "- release/release_evidence_bundle.zip",
            "- compliance/compliance_reports.xlsx",
            "- compliance/compliance_reports.pdf",
            "- runbooks/*",
            "",
            f"Compliance reports packaged: {compliance_reports}",
            "",
            "Use this package for:",
            "- operator handoff",
            "- upgrade preparation",
            "- rollback preparation",
            "- observability and release evidence review",
            "",
            "This package excludes live secrets and masks sensitive settings inside support bundle metadata.",
            "",
        ]
    )


def build_pro_operator_package(
    db: Session,
    *,
    support_days: int = 7,
    support_limit_per_table: int = 5000,
    include_app_log: bool = True,
    refresh_release_evidence: bool = False,
) -> bytes:
    now = _utc_now()
    compliance_payload = _build_compliance_payload(db)
    support_bundle = SupportBundleService.build_zip(
        db,
        days=int(support_days),
        limit_per_table=int(support_limit_per_table),
        include_app_log=bool(include_app_log),
    )
    release_bundle = build_release_evidence_bundle(refresh=bool(refresh_release_evidence))
    compliance_xlsx = build_compliance_xlsx(compliance_payload)
    compliance_pdf = build_compliance_pdf(compliance_payload)

    manifest: dict[str, Any] = {
        "package": "NetSphere Pro Operator Package",
        "generated_at": now.isoformat(),
        "artifacts": {
            "support_bundle": {
                "path": "support/support_bundle.zip",
                "days": int(support_days),
                "limit_per_table": int(support_limit_per_table),
                "include_app_log": bool(include_app_log),
            },
            "release_evidence_bundle": {
                "path": "release/release_evidence_bundle.zip",
                "refreshed": bool(refresh_release_evidence),
            },
            "compliance_exports": {
                "xlsx": "compliance/compliance_reports.xlsx",
                "pdf": "compliance/compliance_reports.pdf",
                "reports": len(compliance_payload),
            },
            "runbooks": [arcname for src, arcname in PRO_RUNBOOKS if src.exists()],
        },
    }

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        zf.writestr("README.txt", _build_readme(now, len(compliance_payload)))
        zf.writestr("support/support_bundle.zip", support_bundle)
        zf.writestr("release/release_evidence_bundle.zip", release_bundle)
        zf.writestr("compliance/compliance_reports.xlsx", compliance_xlsx)
        zf.writestr("compliance/compliance_reports.pdf", compliance_pdf)

        for src, arcname in PRO_RUNBOOKS:
            if not src.exists():
                continue
            try:
                zf.write(src, arcname=arcname)
            except Exception:
                continue

    return buf.getvalue()
