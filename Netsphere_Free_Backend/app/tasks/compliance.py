try:
    from celery import shared_task
except ModuleNotFoundError:
    def shared_task(*args, **kwargs):
        def decorator(fn):
            return fn
        if args and callable(args[0]) and not kwargs:
            return args[0]
        return decorator

from app.db.session import SessionLocal
from app.services.compliance_service import ComplianceEngine
from app.services.change_execution_service import ChangeExecutionService


@shared_task(bind=True, name="app.tasks.compliance.run_compliance_scan_task")
def run_compliance_scan_task(self, device_ids: list[int], standard_id: int | None = None):
    db = SessionLocal()
    try:
        engine = ComplianceEngine(db)
        results = []
        total = len(device_ids or [])
        for idx, dev_id in enumerate(device_ids or []):
            try:
                res = engine.run_rule_scan(dev_id, standard_id)
                results.append(res)
            except Exception as e:
                results.append({"device_id": dev_id, "error": str(e)})
            try:
                if hasattr(self, "update_state"):
                    self.update_state(state="PROGRESS", meta={"done": idx + 1, "total": total})
            except Exception:
                pass
        return {"results": results}
    finally:
        db.close()


@shared_task(name="app.tasks.compliance.run_scheduled_compliance_scan")
def run_scheduled_compliance_scan():
    db = SessionLocal()
    try:
        from app.services.ha_service import HaService
        if HaService.enabled(db) and not HaService.is_active(db):
            return {"status": "skipped", "reason": "ha_standby"}
        from app.models.device import Device
        from app.models.settings import SystemSetting

        enabled = db.query(SystemSetting).filter(SystemSetting.key == "compliance_scan_enabled").first()
        if enabled and str(enabled.value or "").strip().lower() in {"0", "false", "no"}:
            return {"status": "skipped", "reason": "disabled"}

        std_setting = db.query(SystemSetting).filter(SystemSetting.key == "compliance_scan_standard_id").first()
        standard_id = None
        if std_setting and str(std_setting.value or "").strip():
            try:
                standard_id = int(str(std_setting.value).strip())
            except Exception:
                standard_id = None

        device_ids = [d_id for (d_id,) in db.query(Device.id).all()]
        engine = ComplianceEngine(db)
        results = []
        for dev_id in device_ids:
            try:
                results.append(engine.run_rule_scan(dev_id, standard_id))
            except Exception as e:
                results.append({"device_id": dev_id, "error": str(e)})
        return {"status": "ok", "standard_id": standard_id, "count": len(results), "results": results}
    finally:
        db.close()


@shared_task(name="app.tasks.compliance.run_scheduled_config_drift_checks")
def run_scheduled_config_drift_checks():
    db = SessionLocal()
    try:
        from app.services.ha_service import HaService
        if HaService.enabled(db) and not HaService.is_active(db):
            return {"status": "skipped", "reason": "ha_standby"}
        from datetime import datetime

        from app.models.device import Device, Issue, EventLog, ConfigBackup
        from app.models.settings import SystemSetting
        from app.models.approval import ApprovalRequest
        from app.models.user import User
        from app.core import security
        import secrets

        enabled = db.query(SystemSetting).filter(SystemSetting.key == "config_drift_enabled").first()
        if enabled and str(enabled.value or "").strip().lower() in {"0", "false", "no"}:
            return {"status": "skipped", "reason": "disabled"}

        engine = ComplianceEngine(db)
        device_ids = [d_id for (d_id,) in db.query(ConfigBackup.device_id).filter(ConfigBackup.is_golden == True).distinct().all()]
        summary = {"checked": 0, "drift": 0, "compliant": 0, "no_golden": 0, "errors": 0}

        approval_enabled = db.query(SystemSetting).filter(SystemSetting.key == "config_drift_approval_enabled").first()
        approval_is_on = bool(approval_enabled) and str(approval_enabled.value or "").strip().lower() in {"1", "true", "yes", "on"}
        system_user = None
        if approval_is_on:
            system_user = db.query(User).filter(User.username == "system").first()
            if not system_user:
                hashed_pw = security.get_password_hash(secrets.token_urlsafe(32))
                system_user = User(username="system", hashed_password=hashed_pw, full_name="System Automation", role="admin", is_active=True)
                db.add(system_user)
                db.commit()
                db.refresh(system_user)

        for dev_id in device_ids:
            summary["checked"] += 1
            device = db.query(Device).filter(Device.id == dev_id).first()
            if not device:
                continue

            try:
                res = engine.check_config_drift(dev_id)
            except Exception as e:
                summary["errors"] += 1
                db.add(
                    EventLog(
                        device_id=dev_id,
                        severity="warning",
                        event_id="CONFIG_DRIFT_CHECK_ERROR",
                        message=str(e),
                        source="Automation",
                        timestamp=datetime.now(),
                    )
                )
                db.commit()
                continue

            status = str(res.get("status") or "")
            if status == "no_golden":
                summary["no_golden"] += 1
                continue

            issue_title = "Config Drift Detected"
            existing = (
                db.query(Issue)
                .filter(Issue.device_id == dev_id, Issue.status == "active", Issue.category == "config", Issue.title == issue_title)
                .first()
            )

            if status == "drift":
                summary["drift"] += 1
                msg = f"Golden#{res.get('golden_id')} vs Running#{res.get('latest_id')} drift detected"
                db.add(
                    EventLog(
                        device_id=dev_id,
                        severity="warning",
                        event_id="CONFIG_DRIFT",
                        message=msg,
                        source="Automation",
                        timestamp=datetime.now(),
                    )
                )
                if not existing:
                    db.add(
                        Issue(
                            device_id=dev_id,
                            title=issue_title,
                            description=msg,
                            severity="warning",
                            status="active",
                            category="config",
                            created_at=datetime.now(),
                        )
                    )
                else:
                    existing.description = msg

                if approval_is_on and system_user:
                    already = False
                    existing_pending = (
                        db.query(ApprovalRequest)
                        .filter(ApprovalRequest.request_type == "config_drift_remediate", ApprovalRequest.status == "pending")
                        .order_by(ApprovalRequest.created_at.desc())
                        .limit(200)
                        .all()
                    )
                    for r in existing_pending:
                        try:
                            if int((r.payload or {}).get("device_id") or 0) == int(dev_id):
                                already = True
                                break
                        except Exception:
                            continue
                    if not already:
                        db.add(
                            ApprovalRequest(
                                requester_id=system_user.id,
                                title=f"[Drift] Force Sync Proposal - {device.name}",
                                description=msg,
                                request_type="config_drift_remediate",
                                payload={
                                    "device_id": dev_id,
                                    "golden_id": res.get("golden_id"),
                                    "latest_id": res.get("latest_id"),
                                    "save_pre_backup": True,
                                    "prepare_device_snapshot": True,
                                    "rollback_on_failure": True,
                                    "post_check_enabled": True,
                                    "post_check_commands": [],
                                    "execution_status": "proposed",
                                },
                                status="pending",
                            )
                        )
                db.commit()
            else:
                summary["compliant"] += 1
                if existing:
                    existing.status = "resolved"
                    existing.resolved_at = datetime.now()
                    db.commit()

        return {"status": "ok", **summary}
    finally:
        db.close()


@shared_task(name="app.tasks.compliance.run_config_drift_remediation_for_approval")
def run_config_drift_remediation_for_approval(approval_request_id: int, execution_id: str | None = None):
    db = SessionLocal()
    try:
        from datetime import datetime
        from app.models.approval import ApprovalRequest
        from app.models.device import EventLog

        req = db.query(ApprovalRequest).filter(ApprovalRequest.id == approval_request_id).first()
        if not req:
            return {"status": "error", "message": "Approval request not found"}

        if req.request_type != "config_drift_remediate":
            return {"status": "skipped", "message": "Unsupported request_type"}

        if req.status != "approved":
            return {"status": "skipped", "message": f"Request status is {req.status}"}

        payload = dict(req.payload or {})
        raw_ids = payload.get("device_ids")
        device_ids: list[int] = []
        if isinstance(raw_ids, list):
            for v in raw_ids:
                try:
                    device_ids.append(int(v))
                except Exception:
                    continue
        if not device_ids:
            one = payload.get("device_id")
            if one is not None:
                try:
                    device_ids = [int(one)]
                except Exception:
                    device_ids = []
        if not device_ids:
            return {"status": "error", "message": "device_id or device_ids missing in payload"}
        device_ids = ChangeExecutionService._normalize_device_ids(device_ids)

        exec_id = str(execution_id or payload.get("execution_id") or "").strip()
        if not exec_id:
            exec_id = ChangeExecutionService.make_fingerprint(
                "approval_drift_remediation",
                {"approval_id": int(approval_request_id), "device_ids": device_ids},
            )
        payload["approval_id"] = int(approval_request_id)
        payload["execution_id"] = exec_id
        trace = payload.get("execution_trace")
        if not isinstance(trace, dict):
            trace = {}
        trace["approval_id"] = int(approval_request_id)
        trace["execution_id"] = exec_id
        payload["execution_trace"] = trace
        req.payload = payload
        db.commit()
        db.refresh(req)

        engine = ComplianceEngine(db)
        result = engine.remediate_config_drift_batch(
            list(device_ids or []),
            save_pre_backup=bool(payload.get("save_pre_backup", True)),
            prepare_device_snapshot=bool(payload.get("prepare_device_snapshot", True)),
            rollback_on_failure=bool(payload.get("rollback_on_failure", True)),
            post_check_enabled=bool(payload.get("post_check_enabled", True)),
            post_check_commands=list(payload.get("post_check_commands") or []),
            canary_count=int(payload.get("canary_count") or 0),
            wave_size=int(payload.get("wave_size") or 0),
            stop_on_wave_failure=bool(payload.get("stop_on_wave_failure", True)),
            inter_wave_delay_seconds=float(payload.get("inter_wave_delay_seconds") or 0.0),
            require_drift_gate=bool(payload.get("require_drift_gate", True)),
            idempotency_key=(payload.get("idempotency_key") or None),
            approval_id=int(approval_request_id),
            execution_id=exec_id,
        )

        rows = list(result.get("summary") or [])
        failed = 0
        success = 0
        skipped = 0
        for row in rows:
            st = str((row or {}).get("status") or "").strip().lower()
            if st == "success":
                success += 1
            elif st.startswith("skipped_"):
                skipped += 1
            else:
                failed += 1

        if failed > 0:
            exec_status = "failed"
        elif success > 0:
            exec_status = "success"
        else:
            exec_status = "skipped"

        payload["execution_status"] = exec_status
        payload["execution_result"] = result
        payload["executed_at"] = datetime.now().isoformat()
        payload["approval_id"] = int(approval_request_id)
        payload["execution_id"] = exec_id
        payload["device_ids"] = list(device_ids or [])
        req.payload = payload

        primary_device_id = int(device_ids[0]) if device_ids else None
        db.add(
            EventLog(
                device_id=primary_device_id,
                severity="info" if exec_status == "success" else "warning",
                event_id="CONFIG_DRIFT_REMEDIATION_APPROVAL_EXECUTED",
                message=(
                    f"Approval#{approval_request_id} execution_id={exec_id} "
                    f"status={exec_status} success={success} failed={failed} skipped={skipped}"
                ),
                source="Approval",
                timestamp=datetime.now(),
            )
        )
        db.commit()
        return {
            "status": "ok",
            "approval_request_id": approval_request_id,
            "execution_id": exec_id,
            "execution_status": exec_status,
            "result": result,
        }
    finally:
        db.close()
