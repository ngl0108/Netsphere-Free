import io
import zipfile
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models import device as _device
from app.models.user import User
from app.services import pro_operator_package_service as svc


def test_build_pro_operator_package_includes_expected_artifacts(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        user = User(username="operator", hashed_password="hash", role="admin", is_active=True)
        db.add(user)
        db.flush()
        device = _device.Device(
            name="edge-a",
            ip_address="10.0.0.1",
            device_type="arista_eos",
            status="online",
            owner_id=user.id,
        )
        db.add(device)
        db.flush()
        report = _device.ComplianceReport(
            device_id=device.id,
            status="violation",
            match_percentage=78.5,
            last_checked=datetime.now(timezone.utc),
            diff_content='{"standards":{"CIS":{"total":10,"passed":7,"score":70,"violations":[{"rule":"NTP","severity":"high","remediation":"Enable NTP"}]}}}',
        )
        db.add(report)
        db.commit()

        monkeypatch.setattr(svc.SupportBundleService, "build_zip", lambda *args, **kwargs: b"support-zip")
        monkeypatch.setattr(svc, "build_release_evidence_bundle", lambda refresh=False: b"release-zip")
        monkeypatch.setattr(svc, "build_compliance_xlsx", lambda reports: b"xlsx-bytes")
        monkeypatch.setattr(svc, "build_compliance_pdf", lambda reports: b"pdf-bytes")

        bundle = svc.build_pro_operator_package(db, include_app_log=False)
        with zipfile.ZipFile(io.BytesIO(bundle), mode="r") as zf:
            names = set(zf.namelist())
            assert "manifest.json" in names
            assert "README.txt" in names
            assert "support/support_bundle.zip" in names
            assert "release/release_evidence_bundle.zip" in names
            assert "compliance/compliance_reports.xlsx" in names
            assert "compliance/compliance_reports.pdf" in names
            assert "runbooks/PRO_BASELINE_RUNBOOK.md" in names
            assert "runbooks/ALERTING_OPERATIONS_POLICY.md" in names
    finally:
        db.close()
