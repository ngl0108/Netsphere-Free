from app.models.compliance import ComplianceRule, ComplianceStandard
from app.models.device import ComplianceReport, ConfigBackup, Device
from app.api.v1.endpoints import compliance as compliance_ep
from app.services.compliance_service import ComplianceEngine
from app.services.report_export_service import build_compliance_xlsx


def _unwrap_response_json(res):
    body = res.json()
    if isinstance(body, dict) and "data" in body:
        return body["data"]
    return body


def test_run_rule_scan_marks_golden_fixable_violation_as_auto_ready(db):
    device = Device(
        name="cmp-auto-ready-sw1",
        ip_address="10.240.0.1",
        device_type="cisco_ios",
        role="access",
        status="online",
    )
    standard = ComplianceStandard(name="Baseline", description="t", device_family="cisco_ios")
    db.add_all([device, standard])
    db.commit()
    db.refresh(device)
    db.refresh(standard)

    rule = ComplianceRule(
        standard_id=int(standard.id),
        name="Password encryption",
        description="Must enable password encryption",
        severity="warning",
        check_type="simple_match",
        pattern="service password-encryption",
        remediation="service password-encryption",
    )
    db.add(rule)
    db.add(ConfigBackup(device_id=int(device.id), raw_config="hostname sw1\nservice password-encryption\n", is_golden=True))
    db.add(ConfigBackup(device_id=int(device.id), raw_config="hostname sw1\n", is_golden=False))
    db.commit()

    result = ComplianceEngine(db).run_rule_scan(int(device.id))

    assert str(result.get("status") or "") == "violation"
    automation = dict(result.get("automation") or {})
    assert str(automation.get("status") or "") == "auto_ready"
    assert str((automation.get("primary_action") or {}).get("code") or "") == "drift_remediate"
    assert int((automation.get("fix_coverage") or {}).get("golden_fixable") or 0) == 1
    assert str((automation.get("drift") or {}).get("status") or "") == "drift"

    report = db.query(ComplianceReport).filter(ComplianceReport.device_id == int(device.id)).first()
    details = ComplianceEngine.normalize_report_details(report.details if report else None)
    assert str((details.get("automation") or {}).get("status") or "") == "auto_ready"
    assert int((details.get("summary") or {}).get("violations_total") or 0) == 1


def test_run_rule_scan_without_golden_surfaces_set_golden_next_step(db):
    device = Device(
        name="cmp-no-golden-sw1",
        ip_address="10.240.0.2",
        device_type="cisco_ios",
        role="access",
        status="online",
    )
    standard = ComplianceStandard(name="NoGoldenBaseline", description="t", device_family="cisco_ios")
    db.add_all([device, standard])
    db.commit()
    db.refresh(device)
    db.refresh(standard)

    rule = ComplianceRule(
        standard_id=int(standard.id),
        name="Enable SSH",
        description="Must keep SSH enabled",
        severity="critical",
        check_type="simple_match",
        pattern="ip ssh version 2",
        remediation="ip ssh version 2",
    )
    db.add(rule)
    db.add(ConfigBackup(device_id=int(device.id), raw_config="hostname sw2\n", is_golden=False))
    db.commit()

    result = ComplianceEngine(db).run_rule_scan(int(device.id))

    automation = dict(result.get("automation") or {})
    assert str(automation.get("status") or "") == "missing_golden"
    assert str((automation.get("primary_action") or {}).get("code") or "") == "set_golden"
    assert int((automation.get("fix_coverage") or {}).get("manual_guided") or 0) == 1
    assert any("golden config" in str(step).lower() for step in list(automation.get("next_steps") or []))


def test_compliance_reports_endpoint_exposes_nested_automation_in_details(db):
    device = Device(
        name="cmp-report-sw1",
        ip_address="10.240.0.3",
        device_type="cisco_ios",
        role="access",
        status="online",
    )
    standard = ComplianceStandard(name="ReportBaseline", description="t", device_family="cisco_ios")
    db.add_all([device, standard])
    db.commit()
    db.refresh(device)
    db.refresh(standard)

    rule = ComplianceRule(
        standard_id=int(standard.id),
        name="NTP required",
        description="Must configure NTP",
        severity="warning",
        check_type="simple_match",
        pattern="ntp server 10.0.0.10",
        remediation="ntp server 10.0.0.10",
    )
    db.add(rule)
    db.add(ConfigBackup(device_id=int(device.id), raw_config="hostname sw3\nntp server 10.0.0.10\n", is_golden=True))
    db.add(ConfigBackup(device_id=int(device.id), raw_config="hostname sw3\n", is_golden=False))
    db.commit()

    ComplianceEngine(db).run_rule_scan(int(device.id))

    items = compliance_ep.get_reports(device_id=None, db=db)
    assert isinstance(items, list) and items

    row = next(item for item in items if int(item.get("device_id") or 0) == int(device.id))
    details = ComplianceEngine.normalize_report_details(row.get("details"))
    assert str((details.get("automation") or {}).get("status") or "") == "auto_ready"
    assert str(((details.get("violations") or [])[0].get("rule") if details.get("violations") else "")) == "NTP required"


def test_compliance_xlsx_export_accepts_nested_details_payload():
    data = build_compliance_xlsx(
        [
            {
                "device_id": 1,
                "device_name": "edge-sw1",
                "status": "violation",
                "score": 75.0,
                "last_checked": "2026-03-08T00:00:00",
                "details": {
                    "summary": {"status": "violation", "violations_total": 1, "score": 75.0},
                    "standards": {
                        "Baseline": {
                            "total": 2,
                            "passed": 1,
                            "score": 50.0,
                            "violations": [
                                {
                                    "standard": "Baseline",
                                    "rule": "NTP required",
                                    "severity": "warning",
                                    "remediation": "ntp server 10.0.0.10",
                                }
                            ],
                        }
                    },
                    "violations": [
                        {
                            "standard": "Baseline",
                            "rule": "NTP required",
                            "severity": "warning",
                            "remediation": "ntp server 10.0.0.10",
                        }
                    ],
                    "automation": {"status": "auto_ready"},
                },
            }
        ]
    )

    assert isinstance(data, bytes)
    assert data[:2] == b"PK"
