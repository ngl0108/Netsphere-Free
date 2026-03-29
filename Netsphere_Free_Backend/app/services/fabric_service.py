from __future__ import annotations

from datetime import datetime
from difflib import unified_diff
from typing import Any, Dict, List, Tuple

from sqlalchemy.orm import Session

from app.models.device import ConfigBackup, Device
from app.services.change_execution_service import ChangeExecutionService
from app.services.post_check_service import resolve_pre_check_commands
from app.services.ssh_service import DeviceConnection, DeviceInfo


class FabricService:
    _DIFF_PREVIEW_LIMIT = 120

    def __init__(self, db: Session):
        self.db = db

    def _load_devices(self, ids: List[int]) -> List[Device]:
        if not ids:
            return []
        rows = self.db.query(Device).filter(Device.id.in_(ids)).all()
        by_id = {int(d.id): d for d in rows}
        ordered: List[Device] = []
        for dev_id in ids:
            d = by_id.get(int(dev_id))
            if d:
                ordered.append(d)
        return ordered

    def validate_inputs(self, spines: List[int], leafs: List[int]) -> Tuple[bool, str]:
        if not spines:
            return False, "At least one spine is required"
        if not leafs:
            return False, "At least one leaf is required"
        overlap = set(spines).intersection(set(leafs))
        if overlap:
            return False, f"Devices cannot be both spine and leaf: {sorted(list(overlap))}"
        return True, ""

    def generate_fabric_config(
        self,
        spines: List[int],
        leafs: List[int],
        asn_base: int = 65000,
        vni_base: int = 10000,
        underlay_ospf_area: int = 0,
    ) -> Dict[int, str]:
        ok, msg = self.validate_inputs(spines, leafs)
        if not ok:
            raise ValueError(msg)

        spine_devices = self._load_devices(spines)
        leaf_devices = self._load_devices(leafs)
        if len(spine_devices) != len(spines) or len(leaf_devices) != len(leafs):
            raise ValueError("One or more selected devices were not found")

        spine_rids: Dict[int, str] = {}
        leaf_rids: Dict[int, str] = {}
        for i, spine in enumerate(spine_devices):
            spine_rids[int(spine.id)] = f"10.0.0.{10 + i}"
        for i, leaf in enumerate(leaf_devices):
            leaf_rids[int(leaf.id)] = f"10.0.0.{20 + i}"

        configs: Dict[int, str] = {}
        for spine in spine_devices:
            rid = spine_rids[int(spine.id)]
            config = self._render_spine(spine, rid, asn_base)
            configs[int(spine.id)] = config

        for i, leaf in enumerate(leaf_devices):
            rid = leaf_rids[int(leaf.id)]
            config = self._render_leaf(
                leaf=leaf,
                rid=rid,
                asn=asn_base,
                spine_rids=[spine_rids[int(s.id)] for s in spine_devices],
                vni_base=vni_base + i * 100,
                ospf_area=underlay_ospf_area,
            )
            configs[int(leaf.id)] = config

        return configs

    def _render_spine(self, device: Device, rid: str, asn: int) -> str:
        return f"""! Generated Spine Config for {device.name}
hostname {device.hostname or device.name}
!
interface Loopback0
 ip address {rid} 255.255.255.255
 ip ospf 1 area 0
!
router ospf 1
 router-id {rid}
!
router bgp {asn}
 bgp router-id {rid}
 bgp log-neighbor-changes
 neighbor LEAFS peer-group
 neighbor LEAFS remote-as {asn}
 neighbor LEAFS update-source Loopback0
 !
 address-family l2vpn evpn
  neighbor LEAFS send-community both
  neighbor LEAFS route-reflector-client
 exit-address-family
!
"""

    def _render_leaf(
        self,
        *,
        leaf: Device,
        rid: str,
        asn: int,
        spine_rids: List[str],
        vni_base: int,
        ospf_area: int,
    ) -> str:
        loop1 = rid.replace("10.0.0.", "10.0.1.")
        lines: List[str] = []
        lines.append(f"! Generated Leaf Config for {leaf.name}")
        lines.append(f"hostname {leaf.hostname or leaf.name}")
        lines.append("!")
        lines.append("feature ospf")
        lines.append("feature bgp")
        lines.append("feature interface-vlan")
        lines.append("feature vn-segment-vlan-based")
        lines.append("feature nv overlay")
        lines.append("nv overlay evpn")
        lines.append("!")
        lines.append("interface Loopback0")
        lines.append(f"  ip address {rid}/32")
        lines.append(f"  ip router ospf 1 area {ospf_area}")
        lines.append("!")
        lines.append("interface Loopback1")
        lines.append("  description VTEP Source")
        lines.append(f"  ip address {loop1}/32")
        lines.append(f"  ip router ospf 1 area {ospf_area}")
        lines.append("!")
        lines.append("router ospf 1")
        lines.append(f"  router-id {rid}")
        lines.append("!")
        lines.append(f"router bgp {asn}")
        lines.append(f"  router-id {rid}")
        for spine_rid in spine_rids:
            lines.append(f"  neighbor {spine_rid}")
            lines.append(f"    remote-as {asn}")
            lines.append("    update-source Loopback0")
            lines.append("    address-family l2vpn evpn")
            lines.append("      send-community both")
        lines.append("!")
        lines.append("vlan 10")
        lines.append(f"  vn-segment {vni_base + 10}")
        lines.append("!")
        lines.append("interface nve1")
        lines.append("  no shutdown")
        lines.append("  source-interface Loopback1")
        lines.append("  host-reachability protocol bgp")
        return "\n".join(lines)

    @staticmethod
    def _split_commands(config_text: str) -> List[str]:
        return [ln.rstrip() for ln in str(config_text or "").splitlines() if str(ln).strip()]

    @staticmethod
    def _validate_rendered_config(config_text: str) -> List[str]:
        issues: List[str] = []
        text = str(config_text or "")
        commands = FabricService._split_commands(text)
        if not commands:
            issues.append("No commands rendered")
        if "{{" in text or "}}" in text:
            issues.append("Template variables are unresolved")
        if len(commands) < 10:
            issues.append("Rendered config is unexpectedly short")
        return issues

    @staticmethod
    def _looks_like_cli_error(output: str) -> bool:
        t = str(output or "").lower()
        return any(
            k in t
            for k in (
                "% invalid",
                "invalid input",
                "unknown command",
                "unrecognized command",
                "ambiguous command",
                "incomplete command",
                "syntax error",
                "error:",
            )
        )

    @staticmethod
    def _default_diff_payload() -> Dict[str, Any]:
        return {
            "has_changes": False,
            "before_lines": 0,
            "after_lines": 0,
            "added_lines": 0,
            "removed_lines": 0,
            "changed_lines_estimate": 0,
            "context_lines": 0,
            "total_diff_lines": 0,
            "preview": [],
            "preview_truncated": False,
        }

    @staticmethod
    def _summarize_diff(before_text: str, after_text: str, diff_lines: List[str]) -> Dict[str, Any]:
        summary = FabricService._default_diff_payload()
        added = 0
        removed = 0
        context = 0
        for line in list(diff_lines or []):
            if line.startswith(("---", "+++", "@@")):
                continue
            if line.startswith("+"):
                added += 1
            elif line.startswith("-"):
                removed += 1
            else:
                context += 1
        preview = list(diff_lines[: FabricService._DIFF_PREVIEW_LIMIT])
        summary.update(
            {
                "has_changes": bool(added or removed),
                "before_lines": len(str(before_text or "").splitlines()),
                "after_lines": len(str(after_text or "").splitlines()),
                "added_lines": int(added),
                "removed_lines": int(removed),
                "changed_lines_estimate": int(max(added, removed)),
                "context_lines": int(context),
                "total_diff_lines": len(list(diff_lines or [])),
                "preview": preview,
                "preview_truncated": len(list(diff_lines or [])) > len(preview),
            }
        )
        return summary

    def _build_dry_run_diff(self, device_id: int, rendered_config: str) -> Dict[str, Any]:
        try:
            latest = (
                self.db.query(ConfigBackup)
                .filter(ConfigBackup.device_id == int(device_id))
                .order_by(ConfigBackup.created_at.desc())
                .first()
            )
            current = str(latest.raw_config or "") if latest else ""
            diff_lines = list(
                unified_diff(
                    current.splitlines(),
                    str(rendered_config or "").splitlines(),
                    fromfile="current",
                    tofile="rendered",
                    lineterm="",
                )
            )
            return self._summarize_diff(current, str(rendered_config or ""), diff_lines)
        except Exception:
            return self._default_diff_payload()

    def execute_deploy(
        self,
        *,
        spines: List[int],
        leafs: List[int],
        asn_base: int,
        vni_base: int,
        dry_run: bool,
        verify_commands: List[str],
        rollback_on_error: bool,
        pre_check_commands: List[str] | None = None,
        wave_size: int = 0,
        canary_count: int = 0,
        stop_on_wave_failure: bool = True,
        inter_wave_delay_seconds: float = 0.0,
        idempotency_key: str | None = None,
        approval_id: int | None = None,
        execution_id: str | None = None,
    ) -> Dict[str, Any]:
        configs = self.generate_fabric_config(spines=spines, leafs=leafs, asn_base=asn_base, vni_base=vni_base)
        devices = self._load_devices([*spines, *leafs])
        dev_by_id = {int(d.id): d for d in devices}
        deploy_order = ChangeExecutionService._normalize_device_ids([*spines, *leafs])
        appr_id = int(approval_id) if approval_id is not None else None
        exec_id = str(execution_id or "").strip()
        if not exec_id:
            exec_id = ChangeExecutionService.make_fingerprint(
                "fabric_deploy_execution",
                {
                    "spine_ids": list(spines or []),
                    "leaf_ids": list(leafs or []),
                    "asn_base": int(asn_base),
                    "vni_base": int(vni_base),
                    "approval_id": appr_id,
                },
            )
        waves = ChangeExecutionService.build_waves(
            deploy_order,
            wave_size=int(wave_size or 0),
            canary_count=int(canary_count or 0),
        )

        idem = str(idempotency_key or "").strip()
        if idem:
            if not ChangeExecutionService.claim_idempotency("fabric_deploy", idem, ttl_seconds=120, db=self.db):
                skipped = []
                for wave_no, wave in enumerate(waves, start=1):
                    for did in wave:
                        skipped.append(
                            {
                                "id": int(did),
                                "device_id": int(did),
                                "status": "skipped_idempotent",
                                "error": "Duplicate deployment request blocked",
                                "wave": int(wave_no),
                                "rollback": {"attempted": False, "success": False, "message": None},
                                "verify": [],
                                "pre_check": {"ok": True, "rows": []},
                                "dry_run_diff": FabricService._default_diff_payload(),
                                "approval_id": appr_id,
                                "execution_id": exec_id,
                            }
                        )
                return {
                    "summary": {
                        "total": len(skipped),
                        "success": 0,
                        "failed": 0,
                        "skipped": len(skipped),
                        "dry_run": int(bool(dry_run)),
                        "waves_total": len(waves),
                        "waves_executed": 0,
                        "halted": False,
                        "halted_wave": None,
                        "idempotency_key": idem,
                        "approval_id": appr_id,
                        "execution_id": exec_id,
                    },
                    "results": skipped,
                    "execution": {
                        "waves_total": len(waves),
                        "waves_executed": 0,
                        "halted": False,
                        "halted_wave": None,
                        "idempotency_key": idem,
                        "approval_id": appr_id,
                        "execution_id": exec_id,
                    },
                    "approval_id": appr_id,
                    "execution_id": exec_id,
                }

        def _run_one(dev_id: int, wave_no: int) -> Dict[str, Any]:
            config_text = configs.get(int(dev_id))
            dev = dev_by_id.get(int(dev_id))
            if not dev or config_text is None:
                return {
                    "id": int(dev_id),
                    "device_id": int(dev_id),
                    "wave": int(wave_no),
                    "status": "error",
                    "error": "Device not found",
                    "validation_issues": [],
                    "verify": [],
                    "pre_check": {"ok": True, "rows": []},
                    "rollback": {"attempted": False, "success": False, "message": None},
                }

            validation_issues = self._validate_rendered_config(config_text)
            base_payload: Dict[str, Any] = {
                "id": int(dev.id),
                "device_id": int(dev.id),
                "device_name": dev.name,
                "wave": int(wave_no),
                "status": "dry_run",
                "validation_issues": validation_issues,
                "rendered_config": config_text,
                "verify": [],
                "post_check": {"ok": True, "rows": []},
                "pre_check": {"ok": True, "rows": []},
                "rollback": {"attempted": False, "success": False, "message": None},
                "dry_run_diff": FabricService._default_diff_payload(),
                "approval_id": appr_id,
                "execution_id": exec_id,
            }

            base_payload["dry_run_diff"] = self._build_dry_run_diff(int(dev.id), config_text)
            if dry_run:
                if validation_issues:
                    base_payload["status"] = "validation_failed"
                return base_payload

            if validation_issues:
                base_payload["status"] = "validation_failed"
                base_payload["error"] = "Validation failed before deploy"
                return base_payload

            if not dev.ssh_username or not dev.ssh_password:
                base_payload["status"] = "failed"
                base_payload["error"] = "SSH credentials are not configured"
                return base_payload

            info = DeviceInfo(
                host=dev.ip_address,
                username=dev.ssh_username,
                password=dev.ssh_password,
                secret=dev.enable_password,
                port=int(dev.ssh_port or 22),
                device_type=dev.device_type or "cisco_ios",
            )
            conn = DeviceConnection(info)
            snapshot_name = f"fabric_{dev.id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
            snapshot_prepared = False
            try:
                if not conn.connect():
                    raise RuntimeError(f"Connection failed: {conn.last_error}")

                effective_pre_check = list(pre_check_commands or []) if pre_check_commands is not None else []
                if pre_check_commands is None and not effective_pre_check:
                    try:
                        effective_pre_check = list(resolve_pre_check_commands(self.db, dev) or [])
                    except Exception:
                        effective_pre_check = []

                pre_rows: List[Dict[str, Any]] = []
                pre_ok = True
                for cmd in effective_pre_check:
                    c = str(cmd or "").strip()
                    if not c:
                        continue
                    try:
                        out = conn.send_command(c, read_timeout=20)
                        ok = bool(out) and not self._looks_like_cli_error(out)
                        pre_rows.append({"command": c, "ok": ok, "output": out})
                        if not ok:
                            pre_ok = False
                    except Exception as e:
                        pre_ok = False
                        pre_rows.append({"command": c, "ok": False, "error": f"{type(e).__name__}: {e}"})
                base_payload["pre_check"] = {"ok": pre_ok, "rows": pre_rows}
                if not pre_ok:
                    base_payload["status"] = "precheck_failed"
                    base_payload["error"] = "Pre-check failed before deploy"
                    return base_payload

                if rollback_on_error and getattr(conn, "driver", None) and hasattr(conn.driver, "prepare_rollback"):
                    try:
                        snapshot_prepared = bool(conn.driver.prepare_rollback(snapshot_name))
                    except Exception:
                        snapshot_prepared = False

                deploy_out = conn.send_config_set(self._split_commands(config_text))
                base_payload["deploy_output"] = deploy_out

                verify_rows: List[Dict[str, Any]] = []
                verify_ok = True
                for cmd in (verify_commands or []):
                    c = str(cmd or "").strip()
                    if not c:
                        continue
                    try:
                        out = conn.send_command(c, read_timeout=20)
                        ok = bool(out) and not self._looks_like_cli_error(out)
                        verify_rows.append({"command": c, "ok": ok, "output": out})
                        if not ok:
                            verify_ok = False
                    except Exception as e:
                        verify_rows.append({"command": c, "ok": False, "error": f"{type(e).__name__}: {e}"})
                        verify_ok = False
                base_payload["verify"] = verify_rows
                base_payload["post_check"] = {"ok": bool(verify_ok), "rows": verify_rows}
                if not verify_ok:
                    raise RuntimeError("Post-check failed after deploy")
                base_payload["status"] = "success"
                return base_payload
            except Exception as e:
                post_check_obj = base_payload.get("post_check") if isinstance(base_payload.get("post_check"), dict) else None
                if bool(post_check_obj) and not bool(post_check_obj.get("ok", True)):
                    base_payload["status"] = "postcheck_failed"
                else:
                    base_payload["status"] = "failed"
                base_payload["error"] = f"{type(e).__name__}: {e}"
                if rollback_on_error and snapshot_prepared:
                    base_payload["rollback"]["attempted"] = True
                    rb_started = datetime.utcnow()
                    try:
                        rb_ok = bool(conn.rollback())
                        base_payload["rollback"]["success"] = rb_ok
                        base_payload["rollback"]["message"] = "Rollback complete" if rb_ok else "Rollback failed"
                    except Exception as rb_e:
                        base_payload["rollback"]["success"] = False
                        base_payload["rollback"]["message"] = f"{type(rb_e).__name__}: {rb_e}"
                    finally:
                        base_payload["rollback"]["duration_ms"] = int((datetime.utcnow() - rb_started).total_seconds() * 1000)
                return base_payload
            finally:
                try:
                    conn.disconnect()
                except Exception:
                    pass

        def _run_wave(wave_device_ids: List[int], wave_no: int) -> List[Dict[str, Any]]:
            return [_run_one(int(did), int(wave_no)) for did in list(wave_device_ids or [])]

        wave_out = ChangeExecutionService.execute_wave_batches(
            waves,
            _run_wave,
            stop_on_wave_failure=bool(stop_on_wave_failure and not dry_run),
            inter_wave_delay_seconds=float(inter_wave_delay_seconds or 0.0),
        )
        results = list(wave_out.get("results") or [])
        for row in results:
            row.setdefault("approval_id", appr_id)
            row.setdefault("execution_id", exec_id)
        if not bool(dry_run):
            try:
                ChangeExecutionService.emit_change_kpi_events(
                    self.db,
                    rows=results,
                    change_type="fabric_deploy",
                    source="Fabric",
                    default_approval_id=appr_id,
                    default_execution_id=exec_id,
                    commit=True,
                )
            except Exception:
                pass
        exec_meta = dict(wave_out.get("execution") or {})
        exec_meta["approval_id"] = appr_id
        exec_meta["execution_id"] = exec_id

        failed_statuses = {"failed", "error", "validation_failed", "precheck_failed", "postcheck_failed"}
        success = 0
        failed = 0
        skipped = 0
        for r in results:
            st = str(r.get("status") or "").strip().lower()
            if st in {"success", "dry_run"}:
                success += 1
            elif st.startswith("skipped"):
                skipped += 1
            elif st in failed_statuses:
                failed += 1
            else:
                failed += 1

        summary = {
            "total": len(results),
            "success": int(success),
            "failed": int(failed),
            "skipped": int(skipped),
            "dry_run": int(bool(dry_run)),
            "waves_total": int(exec_meta.get("waves_total") or 0),
            "waves_executed": int(exec_meta.get("waves_executed") or 0),
            "halted": bool(exec_meta.get("halted", False)),
            "halted_wave": exec_meta.get("halted_wave"),
            "approval_id": appr_id,
            "execution_id": exec_id,
        }
        if idem:
            summary["idempotency_key"] = idem
            exec_meta["idempotency_key"] = idem

        return {
            "summary": summary,
            "results": results,
            "execution": exec_meta,
            "approval_id": appr_id,
            "execution_id": exec_id,
        }
