import re
import json
import time
from datetime import datetime
from sqlalchemy.orm import Session
from typing import Any, Dict, List, Optional
from app.models.device import Device, ComplianceReport, ConfigBackup, Issue, EventLog
from app.models.compliance import ComplianceStandard, ComplianceRule
from app.services.template_service import TemplateRenderer
from app.services.ssh_service import DeviceConnection, DeviceInfo
from app.services.post_check_service import resolve_post_check_commands, resolve_pre_check_commands
from app.services.config_replace_profile_service import resolve_config_replace_profile
from app.services.change_execution_service import ChangeExecutionService
from app.services.change_policy_service import ChangePolicyService
from app.services.device_support_policy_service import DeviceSupportPolicyService
import uuid

class ComplianceEngine:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _parse_report_details(details_raw: Any) -> Dict[str, Any]:
        if isinstance(details_raw, dict):
            return dict(details_raw)
        if isinstance(details_raw, str) and details_raw.strip():
            try:
                parsed = json.loads(details_raw)
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                return {}
        return {}

    @staticmethod
    def _collect_violations_from_standards(standards: Dict[str, Any]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for std_name, raw in dict(standards or {}).items():
            if not isinstance(raw, dict):
                continue
            for item in list(raw.get("violations") or []):
                if not isinstance(item, dict):
                    continue
                row = dict(item)
                row.setdefault("standard", std_name)
                out.append(row)
        return out

    @staticmethod
    def _derive_report_summary(standards: Dict[str, Any], violations: List[Dict[str, Any]]) -> Dict[str, Any]:
        total_rules = 0
        passed_rules = 0
        for raw in dict(standards or {}).values():
            if not isinstance(raw, dict):
                continue
            try:
                total_rules += int(raw.get("total") or 0)
            except Exception:
                pass
            try:
                passed_rules += int(raw.get("passed") or 0)
            except Exception:
                pass
        score = 100.0
        if total_rules > 0:
            score = round((passed_rules / total_rules) * 100.0, 2)
        elif list(violations or []):
            score = 0.0
        return {
            "status": "compliant" if not list(violations or []) else "violation",
            "total_rules": int(total_rules),
            "passed_rules": int(passed_rules),
            "violations_total": len(list(violations or [])),
            "score": float(score),
        }

    @staticmethod
    def normalize_report_details(details_raw: Any) -> Dict[str, Any]:
        parsed = ComplianceEngine._parse_report_details(details_raw)
        if not parsed:
            return {"summary": {}, "standards": {}, "violations": [], "automation": {}}

        if any(key in parsed for key in ("summary", "standards", "violations", "automation")):
            standards = parsed.get("standards")
            if not isinstance(standards, dict):
                standards = {}
            violations = parsed.get("violations")
            if not isinstance(violations, list):
                violations = ComplianceEngine._collect_violations_from_standards(standards)
            summary = parsed.get("summary")
            if not isinstance(summary, dict):
                summary = ComplianceEngine._derive_report_summary(standards, violations)
            automation = parsed.get("automation")
            if not isinstance(automation, dict):
                automation = {}
            return {
                **parsed,
                "summary": summary,
                "standards": standards,
                "violations": list(violations or []),
                "automation": automation,
            }

        standards = {str(k): v for k, v in parsed.items() if isinstance(v, dict)}
        violations = ComplianceEngine._collect_violations_from_standards(standards)
        return {
            "summary": ComplianceEngine._derive_report_summary(standards, violations),
            "standards": standards,
            "violations": violations,
            "automation": {},
        }

    def _build_violation_record(self, standard: ComplianceStandard, rule: ComplianceRule) -> Dict[str, Any]:
        return {
            "standard_id": int(standard.id),
            "standard": standard.name,
            "rule_id": int(rule.id),
            "rule": rule.name,
            "severity": rule.severity,
            "description": rule.description,
            "remediation": rule.remediation,
            "check_type": rule.check_type,
            "pattern": rule.pattern,
        }

    def _build_report_automation(self, device: Device, violation_refs: List[Dict[str, Any]]) -> Dict[str, Any]:
        violations_total = len(list(violation_refs or []))
        if violations_total == 0:
            return {
                "status": "healthy",
                "actionable": False,
                "requires_approval": False,
                "primary_action": {"code": "none", "label": "No action required"},
                "support": {},
                "drift": {"status": "not_needed", "has_golden": False},
                "fix_coverage": {
                    "total": 0,
                    "golden_fixable": 0,
                    "manual_guided": 0,
                    "manual_review": 0,
                    "coverage_pct": 100.0,
                },
                "pre_check_commands": [],
                "actions": [],
                "next_steps": [],
            }

        support_policy = DeviceSupportPolicyService.evaluate_device(self.db, device)
        features = dict(support_policy.get("features") or {})
        config_supported = bool(features.get("config", False))
        rollback_supported = bool(features.get("rollback", False))

        golden = (
            self.db.query(ConfigBackup)
            .filter(ConfigBackup.device_id == int(device.id), ConfigBackup.is_golden == True)
            .first()
        )
        drift = self.check_config_drift(int(device.id))
        drift_status = str((drift or {}).get("status") or "").strip().lower()
        has_golden = bool(golden and getattr(golden, "raw_config", None))
        golden_config = str(getattr(golden, "raw_config", "") or "")

        golden_fixable_rules: List[Dict[str, Any]] = []
        if has_golden:
            for ref in list(violation_refs or []):
                rule = ref.get("rule")
                record = dict(ref.get("record") or {})
                if isinstance(rule, ComplianceRule) and self._check_rule(golden_config, rule):
                    golden_fixable_rules.append(
                        {
                            "standard": record.get("standard"),
                            "rule": record.get("rule"),
                            "rule_id": record.get("rule_id"),
                        }
                    )

        golden_fixable_count = len(golden_fixable_rules)
        rule_remediation_count = sum(
            1 for ref in list(violation_refs or []) if str((ref.get("record") or {}).get("remediation") or "").strip()
        )
        manual_review_count = max(0, violations_total - rule_remediation_count)

        try:
            pre_check_commands = list(resolve_pre_check_commands(self.db, device) or [])
        except Exception:
            pre_check_commands = []

        requires_approval = False
        auto_actionable = bool(
            config_supported and drift_status == "drift" and golden_fixable_count > 0 and has_golden
        )
        if auto_actionable:
            try:
                requires_approval = bool(
                    ChangePolicyService.requires_compliance_remediate_approval(
                        self.db,
                        target_count=1,
                        approval_id=None,
                    )
                )
            except Exception:
                requires_approval = False

        coverage_pct = round((golden_fixable_count / violations_total) * 100.0, 2) if violations_total > 0 else 100.0
        status = "review_required"
        primary_action = {"code": "review_violations", "label": "Review violations"}
        next_steps: List[str] = []

        if not config_supported:
            status = "blocked"
            if rule_remediation_count > 0:
                primary_action = {"code": "manual_rule_fix", "label": "Use remediation guidance"}
            next_steps.append("Config automation is blocked by the current device support policy.")
        elif not has_golden:
            status = "missing_golden"
            primary_action = {"code": "set_golden", "label": "Set golden config"}
            next_steps.append("Set a golden config to enable force-sync remediation.")
        elif auto_actionable:
            if golden_fixable_count == violations_total:
                status = "approval_required" if requires_approval else "auto_ready"
            else:
                status = "partial_auto_approval" if requires_approval else "partial_auto"
            primary_action = {
                "code": "request_approval" if requires_approval else "drift_remediate",
                "label": "Request drift approval" if requires_approval else "Force sync to golden",
            }
            next_steps.append(
                "Open Drift and request approval before force sync."
                if requires_approval
                else "Open Drift and run force sync to golden."
            )
        elif drift_status == "compliant" and golden_fixable_count > 0:
            status = "baseline_review"
            primary_action = {"code": "review_golden", "label": "Review golden baseline"}
            next_steps.append("Golden config already matches the device, so rule violations must be fixed in the baseline.")
        elif rule_remediation_count > 0:
            status = "manual_guided"
            primary_action = {"code": "manual_rule_fix", "label": "Use remediation guidance"}

        if rule_remediation_count > 0:
            next_steps.append(f"{rule_remediation_count} violation(s) include remediation guidance.")
        if manual_review_count > 0:
            next_steps.append(f"{manual_review_count} violation(s) still require manual review.")
        if has_golden and golden_fixable_count == 0:
            next_steps.append("Current golden config does not resolve any of the active rule violations.")

        actions = [
            {
                "code": "open_drift",
                "label": "Open drift analysis",
                "available": bool(has_golden),
                "target": "drift",
            },
            {
                "code": "drift_remediate",
                "label": "Force sync to golden",
                "available": bool(auto_actionable and not requires_approval),
                "coverage": "full" if golden_fixable_count == violations_total else ("partial" if golden_fixable_count > 0 else "none"),
            },
            {
                "code": "request_approval",
                "label": "Request drift approval",
                "available": bool(auto_actionable and requires_approval),
                "coverage": "full" if golden_fixable_count == violations_total else ("partial" if golden_fixable_count > 0 else "none"),
            },
            {
                "code": "manual_rule_fix",
                "label": "Use remediation guidance",
                "available": bool(rule_remediation_count > 0),
                "count": int(rule_remediation_count),
            },
        ]

        return {
            "status": status,
            "actionable": bool(auto_actionable),
            "requires_approval": bool(requires_approval),
            "primary_action": primary_action,
            "support": {
                "tier": support_policy.get("tier"),
                "readiness": support_policy.get("readiness"),
                "config_supported": bool(config_supported),
                "rollback_supported": bool(rollback_supported),
                "fallback_mode": support_policy.get("fallback_mode"),
                "reasons": list(support_policy.get("reasons") or []),
            },
            "drift": {
                "status": drift_status or "unknown",
                "has_golden": bool(has_golden),
                "golden_id": drift.get("golden_id") if isinstance(drift, dict) else None,
                "latest_id": drift.get("latest_id") if isinstance(drift, dict) else None,
                "message": drift.get("message") if isinstance(drift, dict) else None,
            },
            "fix_coverage": {
                "total": int(violations_total),
                "golden_fixable": int(golden_fixable_count),
                "manual_guided": int(rule_remediation_count),
                "manual_review": int(manual_review_count),
                "coverage_pct": float(coverage_pct),
            },
            "golden_fixable_rules": golden_fixable_rules,
            "pre_check_commands": pre_check_commands,
            "actions": actions,
            "next_steps": next_steps,
        }

    def run_rule_scan(self, device_id: int, standard_id: int = None):
        """
        Rule-based Compliance Scan (New Feature)
        """
        device = self.db.query(Device).filter(Device.id == device_id).first()
        if not device:
            return {"error": "Device not found"}

        # 최신 설정 백업 가져오기
        latest_backup = self.db.query(ConfigBackup)\
            .filter(ConfigBackup.device_id == device_id)\
            .order_by(ConfigBackup.created_at.desc(), ConfigBackup.id.desc())\
            .first()
        
        if not latest_backup or not latest_backup.raw_config:
            return {"error": "No config backup found for this device"}
        
        config_text = latest_backup.raw_config
        
        # 적용할 표준 조회
        query = self.db.query(ComplianceStandard)
        if standard_id:
            query = query.filter(ComplianceStandard.id == standard_id)
        
        standards = query.all()
        if not standards:
            return {"error": "No compliance standards found"}

        violations = []
        violation_refs = []
        total_rules = 0
        passed_rules = 0
        
        report_details = {} # Standard 별 결과

        for standard in standards:
            # 장비 OS Family가 맞는지 확인 (간단한 체크)
            # if standard.device_family and standard.device_family not in device.device_type: continue
            
            std_violations = []
            std_passed = 0
            std_total = 0

            for rule in standard.rules:
                total_rules += 1
                std_total += 1
                
                is_compliant = self._check_rule(config_text, rule)
                
                if is_compliant:
                    passed_rules += 1
                    std_passed += 1
                else:
                    v_data = self._build_violation_record(standard, rule)
                    violations.append(v_data)
                    std_violations.append(v_data)
                    violation_refs.append({"standard": standard, "rule": rule, "record": v_data})

            report_details[standard.name] = {
                "standard_id": int(standard.id),
                "total": std_total,
                "passed": std_passed,
                "score": (std_passed / std_total * 100) if std_total > 0 else 100,
                "violations": std_violations
            }

        # 결과 저장
        report = self.db.query(ComplianceReport).filter(ComplianceReport.device_id == device_id).first()
        if not report:
            report = ComplianceReport(device_id=device_id)
            self.db.add(report)
        
        status = "compliant" if not violations else "violation"
        score = (passed_rules / total_rules * 100) if total_rules > 0 else 100.0
        
        report.status = status
        report.match_percentage = score
        report.last_checked = datetime.now()
        automation = self._build_report_automation(device, violation_refs)
        details_payload = {
            "summary": {
                "status": status,
                "total_rules": int(total_rules),
                "passed_rules": int(passed_rules),
                "violations_total": len(violations),
                "score": float(round(score, 2)),
            },
            "standards": report_details,
            "violations": violations,
            "automation": automation,
        }
        
        # 상세 결과 저장 (JSON 직렬화해서 diff_content에 임시 저장하거나 details 컬럼 사용)
        # details 컬럼은 SQL로 추가할 예정이므로, 여기서는 속성이 런타임에 존재한다고 가정하고 에러 처리
        try:
            report.details = details_payload
        except Exception:
            pass
        report.diff_content = json.dumps(details_payload, ensure_ascii=False)

        # 이슈 생성 로직
        if status == "violation":
            self._create_compliance_issue(device, violations)
        else:
             # Resolve existing compliance issues
             self._resolve_compliance_issues(device)

        self.db.commit()
        
        return {
            "device": device.name,
            "status": status,
            "score": score,
            "violations": violations,
            "details": details_payload,
            "automation": automation,
        }

    def _check_rule(self, config: str, rule: ComplianceRule) -> bool:
        """
        규칙 검사 로직
        """
        pattern = rule.pattern
        if not pattern: return True
        
        if rule.check_type == "simple_match":
            return pattern in config
            
        elif rule.check_type == "absent_match":
            return pattern not in config
            
        elif rule.check_type == "regex_match":
            try:
                return re.search(pattern, config, re.MULTILINE) is not None
            except re.error:
                return False 
                
        return True

    def _create_compliance_issue(self, device, violations):
        # Check for existing open issue
        existing_issue = self.db.query(Issue).filter(
            Issue.device_id == device.id,
            Issue.status == 'active',
            Issue.category == 'security',
            Issue.title.like('Security Compliance Violation%')
        ).first()
        
        if not existing_issue:
            cnt = len(violations)
            new_issue = Issue(
                device_id=device.id,
                title=f"Security Compliance Violation ({cnt} items)",
                description=f"Device failed {cnt} security compliance rules. Check audit report for details.",
                severity="warning",
                status="active",
                category="security",
                created_at=datetime.now()
            )
            self.db.add(new_issue)

    def _resolve_compliance_issues(self, device):
        issues = self.db.query(Issue).filter(
            Issue.device_id == device.id,
            Issue.status == 'active',
            Issue.category == 'security',
            Issue.title.like('Security Compliance Violation%')
        ).all()
        for issue in issues:
            issue.status = 'resolved'
            issue.resolved_at = datetime.now()


    # ---------------------------------------------------------
    # Legacy: Golden Config Template Match (Keep for compatibility)
    # ---------------------------------------------------------
    def check_golden_config(self, device_id: int, template_content: str, policy=None):
        # 1. 장비 정보 조회
        device = self.db.query(Device).filter(Device.id == device_id).first()
        if not device:
            return {"status": "error", "message": "Device not found"}

        # 2. Running Config (최근 백업) 확인
        latest_backup = None
        if device.config_backups:
            backups = sorted(device.config_backups, key=lambda x: x.created_at, reverse=True)
            latest_backup = backups[0].raw_config

        if not latest_backup:
            return {"status": "error", "message": "No running config found. Please Sync first."}

        # 3. 변수 병합 및 렌더링
        global_vars = {"company": "NetSphere"}
        site_vars = device.site_obj.variables if device.site_obj else {}
        device_vars = device.variables or {}
        device_vars.update({
            "hostname": device.name,
            "management_ip": device.ip_address,
            "model": device.model
        })

        context = TemplateRenderer.merge_variables(global_vars, site_vars, device_vars)
        golden_config = TemplateRenderer.render(template_content, context)

        # 4. Compare
        def is_code(line):
            l = line.strip()
            return l and not l.startswith('!') and not l.startswith('#')

        running_lines = set(line.strip() for line in latest_backup.strip().splitlines() if is_code(line))
        golden_lines = set(line.strip() for line in golden_config.strip().splitlines() if is_code(line))

        missing_lines = golden_lines - running_lines
        
        status = "compliant" if not missing_lines else "violation"
        score = 100.0
        if len(golden_lines) > 0:
            score = ((len(golden_lines) - len(missing_lines)) / len(golden_lines)) * 100

        # ... (Legacy report saving logic simplified) ...
        # This function is kept but we prioritize run_rule_scan for the new page

        return {
            "status": status,
            "match_percentage": round(score, 2),
            "violations": {
                "missing_lines": sorted(list(missing_lines))
            }
        }

    # ---------------------------------------------------------
    # Config Drift Detection (Gluware-like Feature)
    # ---------------------------------------------------------
    def set_golden_config(self, backup_id: int):
        # 1. 대상 백업 조회
        target_backup = self.db.query(ConfigBackup).filter(ConfigBackup.id == backup_id).first()
        if not target_backup:
            return {"error": "Backup not found"}
        
        # 2. 해당 장비의 기존 Golden 해제 (장비당 1개만 Golden 유지)
        self.db.query(ConfigBackup).filter(
            ConfigBackup.device_id == target_backup.device_id,
            ConfigBackup.is_golden == True
        ).update({"is_golden": False})
        
        # 3. 새로운 Golden 지정
        target_backup.is_golden = True
        self.db.commit()
        return {"message": f"Backup #{backup_id} is now the Golden Config"}

    def check_config_drift(self, device_id: int):
        import difflib

        # 1. Golden Config 조회
        golden = self.db.query(ConfigBackup).filter(
            ConfigBackup.device_id == device_id,
            ConfigBackup.is_golden == True
        ).first()

        if not golden:
            return {"status": "no_golden", "message": "No Golden Config defined for this device"}

        # 2. 최신 Running Config (백업) 조회
        latest = self.db.query(ConfigBackup).filter(
            ConfigBackup.device_id == device_id
        ).order_by(ConfigBackup.created_at.desc(), ConfigBackup.id.desc()).first()

        if not latest:
            return {"status": "error", "message": "No config backup available"}

        # 3. 비교 (Diff)
        golden_lines = (golden.raw_config or "").splitlines()
        latest_lines = (latest.raw_config or "").splitlines()
        
        diff = list(difflib.unified_diff(
            golden_lines, latest_lines, 
            fromfile=f'Golden (ID:{golden.id})', 
            tofile=f'Running (ID:{latest.id})',
            lineterm=''
        ))

        # 4. 결과 분석
        drift_detected = len(diff) > 0
        
        return {
            "device_id": device_id,
            "status": "drift" if drift_detected else "compliant",
            "golden_id": golden.id,
            "latest_id": latest.id,
            "diff_lines": diff,
            "message": "Configuration drift detected" if drift_detected else "Configuration matches Golden Config"
        }

    def _looks_like_cli_error(self, output: str) -> bool:
        t = (output or "").lower()
        return any(
            s in t
            for s in (
                "% invalid",
                "invalid input",
                "unknown command",
                "unrecognized command",
                "ambiguous command",
                "incomplete command",
                "error:",
                "syntax error",
            )
        )

    def _default_post_check_commands(self, device_type: str) -> List[str]:
        dt = str(device_type or "").lower()
        if "juniper" in dt or "junos" in dt:
            return ["show system uptime", "show system alarms", "show chassis alarms"]
        if "huawei" in dt:
            return ["display clock", "display version"]
        return ["show clock", "show version"]

    def _run_post_check(self, conn: DeviceConnection, device: Device, commands: List[str]) -> Dict[str, Any]:
        tried = []
        for cmd in commands:
            try:
                out = conn.send_command(cmd, read_timeout=20)
            except Exception as e:
                tried.append({"command": cmd, "ok": False, "error": f"{type(e).__name__}: {e}"})
                continue
            ok = bool(out) and not self._looks_like_cli_error(out)
            if ok:
                return {"ok": True, "command": cmd, "output": out, "tried": tried}
            tried.append({"command": cmd, "ok": False, "output": out})
        return {"ok": False, "command": None, "output": None, "tried": tried}

    def _run_pre_check(self, conn: DeviceConnection, commands: List[str]) -> Dict[str, Any]:
        rows: List[Dict[str, Any]] = []
        all_ok = True
        for cmd in list(commands or []):
            c = str(cmd or "").strip()
            if not c:
                continue
            try:
                out = conn.send_command(c, read_timeout=20)
                ok = bool(out) and not self._looks_like_cli_error(out)
                rows.append({"command": c, "ok": ok, "output": out})
                if not ok:
                    all_ok = False
            except Exception as e:
                all_ok = False
                rows.append({"command": c, "ok": False, "error": f"{type(e).__name__}: {e}"})
        return {"ok": bool(all_ok), "rows": rows}

    def _config_to_commands(self, raw_config: str) -> List[str]:
        lines = []
        for line in (raw_config or "").splitlines():
            s = str(line or "").strip()
            if not s:
                continue
            if s.startswith("!") or s.startswith("#"):
                continue
            if s.lower().startswith("building configuration"):
                continue
            if s.lower().startswith("current configuration"):
                continue
            lines.append(s)
        return lines

    def _classify_remediation_failure(
        self,
        *,
        status: str,
        error: Optional[str],
        post_check: Optional[Dict[str, Any]],
        rollback_attempted: bool,
        rollback_success: bool,
    ) -> str:
        st = str(status or "").strip().lower()
        msg = str(error or "").strip().lower()
        if st == "precheck_failed":
            return "precheck_failed"
        if st == "no_golden":
            return "no_golden"
        if "ssh password not set" in msg:
            return "credential_missing"
        if "connection failed" in msg:
            return "connection_failed"
        if "golden config is empty" in msg:
            return "golden_empty"
        if bool(post_check) and post_check.get("ok") is False:
            return "post_check_failed_rollback_failed" if rollback_attempted and not rollback_success else "post_check_failed"
        if rollback_attempted and not rollback_success:
            return "rollback_failed"
        if st in {"error", "failed"}:
            return "execution_failed"
        return "unknown"

    def _emit_remediation_kpi_event(self, device_id: int, payload: Dict[str, Any]) -> None:
        try:
            self.db.add(
                EventLog(
                    device_id=int(device_id),
                    severity="info",
                    event_id="CONFIG_DRIFT_REMEDIATION_KPI",
                    message=json.dumps(payload or {}, ensure_ascii=False, default=str),
                    source="Compliance",
                    timestamp=datetime.now(),
                )
            )
        except Exception:
            pass

    def remediate_config_drift(
        self,
        device_id: int,
        *,
        save_pre_backup: bool = True,
        pre_check_commands: Optional[List[str]] = None,
        prepare_device_snapshot: bool = True,
        rollback_on_failure: bool = True,
        post_check_enabled: bool = True,
        post_check_commands: Optional[List[str]] = None,
        approval_id: Optional[int] = None,
        execution_id: Optional[str] = None,
        wave: Optional[int] = None,
    ) -> Dict[str, Any]:
        device = self.db.query(Device).filter(Device.id == device_id).first()
        if not device:
            return {"status": "error", "message": "Device not found"}

        golden = self.db.query(ConfigBackup).filter(ConfigBackup.device_id == device_id, ConfigBackup.is_golden == True).first()
        if not golden or not golden.raw_config:
            return {"status": "no_golden", "message": "No Golden Config defined for this device"}

        if not device.ssh_password:
            return {"status": "error", "message": "SSH password not set for device"}

        info = DeviceInfo(
            host=device.ip_address,
            username=device.ssh_username or "admin",
            password=device.ssh_password,
            secret=device.enable_password,
            port=int(device.ssh_port or 22),
            device_type=device.device_type or "cisco_ios",
        )

        conn = DeviceConnection(info)
        if not conn.connect():
            return {"status": "failed", "message": f"Connection failed: {conn.last_error}"}

        pre_backup_id = None
        pre_backup_error = None
        rollback_prepared = False
        rollback_ref = None
        post_check = None
        pre_check = {"ok": True, "rows": []}

        try:
            pre_commands = [str(c or "").strip() for c in list(pre_check_commands or []) if str(c or "").strip()]
            if not pre_commands:
                try:
                    pre_commands = list(resolve_pre_check_commands(self.db, device) or [])
                except Exception:
                    pre_commands = []
            if pre_commands:
                pre_check = self._run_pre_check(conn, pre_commands)
                if not bool(pre_check.get("ok")):
                    failure_cause = self._classify_remediation_failure(
                        status="precheck_failed",
                        error="Pre-check failed before remediation",
                        post_check=None,
                        rollback_attempted=False,
                        rollback_success=False,
                    )
                    self._emit_remediation_kpi_event(
                        int(device_id),
                        {
                            "status": "precheck_failed",
                            "device_id": int(device_id),
                            "approval_id": int(approval_id) if approval_id is not None else None,
                            "execution_id": str(execution_id) if execution_id is not None else None,
                            "wave": int(wave) if wave is not None else None,
                            "error": "Pre-check failed before remediation",
                            "pre_check": pre_check,
                            "post_check_failed": False,
                            "rollback_attempted": False,
                            "rollback_success": False,
                            "rollback_duration_ms": None,
                            "rollback_error": None,
                            "failure_cause": failure_cause,
                            "timestamp": datetime.now().isoformat(),
                        },
                    )
                    self.db.commit()
                    return {
                        "status": "precheck_failed",
                        "device_id": int(device_id),
                        "error": "Pre-check failed before remediation",
                        "pre_check": pre_check,
                        "post_check": None,
                        "failure_cause": failure_cause,
                        "rollback_attempted": False,
                        "rollback_success": False,
                        "rollback_error": None,
                        "rollback_duration_ms": None,
                        "approval_id": int(approval_id) if approval_id is not None else None,
                        "execution_id": str(execution_id) if execution_id is not None else None,
                        "wave": int(wave) if wave is not None else None,
                    }

            if save_pre_backup:
                try:
                    running_before = conn.get_running_config()
                    b = ConfigBackup(device_id=device_id, raw_config=running_before, is_golden=False)
                    self.db.add(b)
                    self.db.commit()
                    self.db.refresh(b)
                    pre_backup_id = int(b.id)
                except Exception as e:
                    self.db.rollback()
                    pre_backup_error = f"{type(e).__name__}: {e}"

            if prepare_device_snapshot:
                snap_name = f"rollback_{device_id}_{uuid.uuid4().hex[:10]}"
                try:
                    rollback_prepared = bool(conn.driver.prepare_rollback(snap_name)) if conn.driver else False
                    rollback_ref = getattr(conn.driver, "_rollback_ref", None) or snap_name
                except Exception:
                    rollback_prepared = False
                    rollback_ref = None

            push_output: Any
            replace_result = None
            if getattr(conn, "driver", None) and hasattr(conn.driver, "apply_config_replace"):
                try:
                    profile = resolve_config_replace_profile(self.db, device)
                    if profile and isinstance(profile, dict):
                        try:
                            setattr(conn.driver, "_config_replace_profile", profile)
                        except Exception:
                            pass
                    replace_result = conn.driver.apply_config_replace(golden.raw_config or "")
                except Exception as e:
                    replace_result = {"success": False, "error": f"{type(e).__name__}: {e}"}

            if isinstance(replace_result, dict) and replace_result.get("success") is True:
                push_output = replace_result.get("output")
                if push_output is None or push_output == "":
                    parts: List[str] = []
                    ref = replace_result.get("ref")
                    if ref:
                        parts.append(f"ref: {ref}")
                    replace_command = replace_result.get("replace_command")
                    if replace_command:
                        parts.append(f"replace_command: {replace_command}")
                    copy_output = replace_result.get("copy_output")
                    if copy_output:
                        parts.append("copy_output:\n" + str(copy_output))
                    replace_output = replace_result.get("replace_output")
                    if replace_output:
                        parts.append("replace_output:\n" + str(replace_output))
                    if parts:
                        push_output = "\n\n".join(parts)
                    else:
                        push_output = json.dumps(replace_result, ensure_ascii=False, default=str)
            else:
                cmds = self._config_to_commands(golden.raw_config)
                if not cmds:
                    return {"status": "error", "message": "Golden config is empty after normalization"}
                push_output = conn.send_config_set(cmds)

            if post_check_enabled:
                commands = list(post_check_commands or [])
                if not commands:
                    commands = resolve_post_check_commands(self.db, device) or []
                if not commands:
                    commands = self._default_post_check_commands(info.device_type)
                post_check = self._run_post_check(conn, device, commands)
                if not post_check.get("ok"):
                    raise Exception("Post-check failed")

            try:
                running_after = conn.get_running_config()
                b2 = ConfigBackup(device_id=device_id, raw_config=running_after, is_golden=False)
                self.db.add(b2)
                self.db.commit()
            except Exception:
                self.db.rollback()

            drift = self.check_config_drift(device_id)

            issue_title = "Config Drift Detected"
            existing = self.db.query(Issue).filter(Issue.device_id == device_id, Issue.status == "active", Issue.category == "config", Issue.title == issue_title).first()
            if drift.get("status") == "compliant" and existing:
                existing.status = "resolved"
                existing.resolved_at = datetime.now()
                self.db.commit()

            self.db.add(
                EventLog(
                    device_id=device_id,
                    severity="info",
                    event_id="CONFIG_DRIFT_REMEDIATION",
                    message=f"Remediation executed (golden_id={golden.id})",
                    source="Compliance",
                    timestamp=datetime.now(),
                )
            )
            self._emit_remediation_kpi_event(
                int(device_id),
                {
                    "status": "ok",
                    "device_id": int(device_id),
                    "approval_id": int(approval_id) if approval_id is not None else None,
                    "execution_id": str(execution_id) if execution_id is not None else None,
                    "wave": int(wave) if wave is not None else None,
                    "pre_check": pre_check,
                    "post_check_failed": bool(post_check_enabled and bool(post_check) and not bool(post_check.get("ok"))),
                    "rollback_attempted": False,
                    "rollback_success": False,
                    "rollback_duration_ms": None,
                    "failure_cause": None,
                    "timestamp": datetime.now().isoformat(),
                },
            )
            self.db.commit()

            return {
                "status": "ok",
                "device_id": device_id,
                "golden_id": golden.id,
                "pre_backup_id": pre_backup_id,
                "pre_backup_error": pre_backup_error,
                "rollback_prepared": rollback_prepared,
                "rollback_ref": rollback_ref,
                "push_output": push_output,
                "replace_result": replace_result,
                "pre_check": pre_check,
                "post_check": post_check,
                "drift_after": drift,
                "approval_id": int(approval_id) if approval_id is not None else None,
                "execution_id": str(execution_id) if execution_id is not None else None,
                "wave": int(wave) if wave is not None else None,
            }
        except Exception as e:
            rollback_attempted = False
            rollback_success = False
            rollback_error = None
            rollback_duration_ms = None
            if rollback_on_failure:
                rollback_attempted = True
                rb_started = time.perf_counter()
                try:
                    rollback_success = bool(conn.driver.rollback()) if conn.driver else False
                except Exception as re:
                    rollback_error = f"{type(re).__name__}: {re}"
                    rollback_success = False
                finally:
                    rollback_duration_ms = int((time.perf_counter() - rb_started) * 1000)

            failure_cause = self._classify_remediation_failure(
                status="postcheck_failed" if bool(bool(post_check) and not bool(post_check.get("ok"))) else "failed",
                error=str(e),
                post_check=post_check,
                rollback_attempted=rollback_attempted,
                rollback_success=rollback_success,
            )
            failure_status = (
                "postcheck_failed"
                if str(failure_cause) in {"post_check_failed", "post_check_failed_rollback_failed"}
                else ("precheck_failed" if str(failure_cause) == "precheck_failed" else "failed")
            )

            self.db.add(
                EventLog(
                    device_id=device_id,
                    severity="warning",
                    event_id="CONFIG_DRIFT_REMEDIATION_FAILED",
                    message=str(e),
                    source="Compliance",
                    timestamp=datetime.now(),
                )
            )
            self._emit_remediation_kpi_event(
                int(device_id),
                {
                    "status": failure_status,
                    "device_id": int(device_id),
                    "approval_id": int(approval_id) if approval_id is not None else None,
                    "execution_id": str(execution_id) if execution_id is not None else None,
                    "wave": int(wave) if wave is not None else None,
                    "error": str(e),
                    "pre_check": pre_check,
                    "post_check_failed": bool(bool(post_check) and not bool(post_check.get("ok"))),
                    "rollback_attempted": bool(rollback_attempted),
                    "rollback_success": bool(rollback_success),
                    "rollback_duration_ms": int(rollback_duration_ms) if rollback_duration_ms is not None else None,
                    "rollback_error": rollback_error,
                    "failure_cause": failure_cause,
                    "timestamp": datetime.now().isoformat(),
                },
            )
            self.db.commit()

            return {
                "status": failure_status,
                "device_id": device_id,
                "error": str(e),
                "pre_backup_id": pre_backup_id,
                "pre_backup_error": pre_backup_error,
                "rollback_attempted": rollback_attempted,
                "rollback_success": rollback_success,
                "rollback_error": rollback_error,
                "rollback_duration_ms": rollback_duration_ms,
                "rollback_prepared": rollback_prepared,
                "rollback_ref": rollback_ref,
                "pre_check": pre_check,
                "post_check": post_check,
                "failure_cause": failure_cause,
                "approval_id": int(approval_id) if approval_id is not None else None,
                "execution_id": str(execution_id) if execution_id is not None else None,
                "wave": int(wave) if wave is not None else None,
            }
        finally:
            try:
                conn.disconnect()
            except Exception:
                pass

    def remediate_config_drift_batch(
        self,
        device_ids: List[int],
        *,
        save_pre_backup: bool = True,
        pre_check_commands: Optional[List[str]] = None,
        prepare_device_snapshot: bool = True,
        rollback_on_failure: bool = True,
        post_check_enabled: bool = True,
        post_check_commands: Optional[List[str]] = None,
        canary_count: int = 0,
        wave_size: int = 0,
        stop_on_wave_failure: bool = True,
        inter_wave_delay_seconds: float = 0.0,
        require_drift_gate: bool = True,
        idempotency_key: Optional[str] = None,
        approval_id: Optional[int] = None,
        execution_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        target_ids = ChangeExecutionService._normalize_device_ids(list(device_ids or []))
        exec_id = str(execution_id or "").strip()
        if not exec_id:
            exec_id = ChangeExecutionService.make_fingerprint(
                "compliance_drift_remediate",
                {
                    "device_ids": target_ids,
                    "save_pre_backup": bool(save_pre_backup),
                    "pre_check_commands": list(pre_check_commands or []),
                    "prepare_device_snapshot": bool(prepare_device_snapshot),
                    "rollback_on_failure": bool(rollback_on_failure),
                    "post_check_enabled": bool(post_check_enabled),
                    "post_check_commands": list(post_check_commands or []),
                    "canary_count": int(canary_count or 0),
                    "wave_size": int(wave_size or 0),
                    "stop_on_wave_failure": bool(stop_on_wave_failure),
                    "inter_wave_delay_seconds": float(inter_wave_delay_seconds or 0.0),
                    "require_drift_gate": bool(require_drift_gate),
                    "approval_id": int(approval_id) if approval_id is not None else None,
                },
            )

        if not target_ids:
            execution_meta = {
                "waves_total": 0,
                "waves_executed": 0,
                "halted": False,
                "halted_wave": None,
                "approval_id": int(approval_id) if approval_id is not None else None,
                "execution_id": exec_id,
                "idempotency_key": None,
            }
            return {
                "summary": [],
                "execution": execution_meta,
                "counts": {"total": 0, "success": 0, "failed": 0, "skipped": 0, "gate_failed": 0},
                "approval_id": int(approval_id) if approval_id is not None else None,
                "execution_id": exec_id,
                "idempotency_key": None,
            }

        idem_key = str(idempotency_key or "").strip()
        if not idem_key:
            idem_key = ChangeExecutionService.make_fingerprint(
                "compliance_drift_remediate_idem",
                {
                    "device_ids": target_ids,
                    "execution_id": exec_id,
                    "approval_id": int(approval_id) if approval_id is not None else None,
                },
            )
        if not ChangeExecutionService.claim_idempotency("compliance_drift_remediate", idem_key, ttl_seconds=120, db=self.db):
            skipped_rows: List[Dict[str, Any]] = []
            for did in target_ids:
                skipped_rows.append(
                    {
                        "id": int(did),
                        "device_id": int(did),
                        "status": "skipped_idempotent",
                        "error": "Duplicate compliance remediation request",
                        "approval_id": int(approval_id) if approval_id is not None else None,
                        "execution_id": exec_id,
                    }
                )
            execution_meta = {
                "waves_total": 0,
                "waves_executed": 0,
                "halted": False,
                "halted_wave": None,
                "approval_id": int(approval_id) if approval_id is not None else None,
                "execution_id": exec_id,
                "idempotency_key": idem_key,
            }
            return {
                "summary": skipped_rows,
                "execution": execution_meta,
                "counts": {"total": len(skipped_rows), "success": 0, "failed": 0, "skipped": len(skipped_rows), "gate_failed": 0},
                "approval_id": int(approval_id) if approval_id is not None else None,
                "execution_id": exec_id,
                "idempotency_key": idem_key,
            }

        waves = ChangeExecutionService.build_waves(
            target_ids,
            wave_size=int(wave_size or 0),
            canary_count=int(canary_count or 0),
        )

        def _is_failure(row: Dict[str, Any]) -> bool:
            status = str((row or {}).get("status") or "").strip().lower()
            if status in {"success", "dry_run", "skipped_gate_compliant", "skipped_gate_not_drift"}:
                return False
            if status.startswith("skipped_"):
                return False
            return True

        def _run_one(dev_id: int, wave_no: int) -> Dict[str, Any]:
            if bool(require_drift_gate):
                drift = self.check_config_drift(int(dev_id))
                drift_status = str((drift or {}).get("status") or "").strip().lower()
                if drift_status == "compliant":
                    return {
                        "id": int(dev_id),
                        "device_id": int(dev_id),
                        "status": "skipped_gate_compliant",
                        "wave": int(wave_no),
                        "gate": drift,
                        "approval_id": int(approval_id) if approval_id is not None else None,
                        "execution_id": exec_id,
                    }
                if drift_status != "drift":
                    return {
                        "id": int(dev_id),
                        "device_id": int(dev_id),
                        "status": f"gate_failed_{drift_status or 'unknown'}",
                        "error": str((drift or {}).get("message") or drift_status or "Gate check failed"),
                        "wave": int(wave_no),
                        "gate": drift,
                        "approval_id": int(approval_id) if approval_id is not None else None,
                        "execution_id": exec_id,
                    }

            one = self.remediate_config_drift(
                int(dev_id),
                save_pre_backup=bool(save_pre_backup),
                pre_check_commands=list(pre_check_commands or []),
                prepare_device_snapshot=bool(prepare_device_snapshot),
                rollback_on_failure=bool(rollback_on_failure),
                post_check_enabled=bool(post_check_enabled),
                post_check_commands=list(post_check_commands or []),
                approval_id=approval_id,
                execution_id=exec_id,
                wave=int(wave_no),
            )
            one_status = str((one or {}).get("status") or "").strip().lower()
            if one_status in {"ok", "success"}:
                normalized_status = "success"
            elif one_status in {"precheck_failed", "pre_check_failed"}:
                normalized_status = "precheck_failed"
            elif one_status in {"postcheck_failed", "post_check_failed"}:
                normalized_status = "postcheck_failed"
            elif one_status in {"validation_failed"}:
                normalized_status = "validation_failed"
            else:
                normalized_status = "failed"
            return {
                "id": int(dev_id),
                "device_id": int(dev_id),
                "status": normalized_status,
                "error": one.get("error") if isinstance(one, dict) else None,
                "wave": int(wave_no),
                "result": one,
                "failure_cause": one.get("failure_cause") if isinstance(one, dict) else None,
                "pre_check": one.get("pre_check") if isinstance(one, dict) else None,
                "post_check": one.get("post_check") if isinstance(one, dict) else None,
                "post_check_failed": bool(one.get("post_check_failed")) if isinstance(one, dict) else False,
                "rollback_attempted": bool(one.get("rollback_attempted")) if isinstance(one, dict) else False,
                "rollback_success": bool(one.get("rollback_success")) if isinstance(one, dict) else False,
                "rollback_duration_ms": one.get("rollback_duration_ms") if isinstance(one, dict) else None,
                "rollback_error": one.get("rollback_error") if isinstance(one, dict) else None,
                "approval_id": int(approval_id) if approval_id is not None else None,
                "execution_id": exec_id,
            }

        def _run_wave(wave_device_ids: List[int], wave_no: int) -> List[Dict[str, Any]]:
            rows: List[Dict[str, Any]] = []
            for did in list(wave_device_ids or []):
                rows.append(_run_one(int(did), int(wave_no)))
            return rows

        wave_out = ChangeExecutionService.execute_wave_batches(
            waves,
            _run_wave,
            stop_on_wave_failure=bool(stop_on_wave_failure),
            inter_wave_delay_seconds=float(inter_wave_delay_seconds or 0.0),
            is_failure=_is_failure,
        )
        rows = list(wave_out.get("results") or [])
        for row in rows:
            row.setdefault("approval_id", int(approval_id) if approval_id is not None else None)
            row.setdefault("execution_id", exec_id)

        execution_meta = dict(wave_out.get("execution") or {})
        execution_meta["approval_id"] = int(approval_id) if approval_id is not None else None
        execution_meta["execution_id"] = exec_id
        execution_meta["idempotency_key"] = idem_key

        success_cnt = 0
        failed_cnt = 0
        skipped_cnt = 0
        gate_failed_cnt = 0
        for row in rows:
            st = str((row or {}).get("status") or "").strip().lower()
            if st == "success":
                success_cnt += 1
            elif st.startswith("skipped_"):
                skipped_cnt += 1
            elif st.startswith("gate_failed_"):
                gate_failed_cnt += 1
                failed_cnt += 1
            elif _is_failure(row):
                failed_cnt += 1

        return {
            "summary": rows,
            "execution": execution_meta,
            "counts": {
                "total": len(rows),
                "success": int(success_cnt),
                "failed": int(failed_cnt),
                "skipped": int(skipped_cnt),
                "gate_failed": int(gate_failed_cnt),
            },
            "approval_id": int(approval_id) if approval_id is not None else None,
            "execution_id": exec_id,
            "idempotency_key": idem_key,
        }
