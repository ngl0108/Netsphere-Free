from app.models.device import ConfigBackup, Device
from app.services.fabric_service import FabricService


def test_fabric_execute_deploy_supports_canary_and_waves_in_dry_run(db):
    spine = Device(name="f-spine", ip_address="10.92.0.1", device_type="cisco_ios", status="online")
    leaf1 = Device(name="f-leaf-1", ip_address="10.92.0.2", device_type="cisco_ios", status="online")
    leaf2 = Device(name="f-leaf-2", ip_address="10.92.0.3", device_type="cisco_ios", status="online")
    db.add_all([spine, leaf1, leaf2])
    db.commit()

    out = FabricService(db).execute_deploy(
        spines=[int(spine.id)],
        leafs=[int(leaf1.id), int(leaf2.id)],
        asn_base=65000,
        vni_base=10000,
        dry_run=True,
        pre_check_commands=[],
        verify_commands=[],
        rollback_on_error=True,
        canary_count=1,
        wave_size=1,
        stop_on_wave_failure=True,
        inter_wave_delay_seconds=0.0,
        idempotency_key=None,
        approval_id=77,
        execution_id="exec-fabric-77",
    )

    summary = out["summary"]
    rows = out["results"]
    assert summary["waves_total"] == 3
    assert summary["total"] == 3
    assert summary["failed"] == 0
    assert summary["approval_id"] == 77
    assert summary["execution_id"] == "exec-fabric-77"
    assert [r.get("wave") for r in rows] == [1, 2, 3]
    assert all(r.get("approval_id") == 77 for r in rows)
    assert all(r.get("execution_id") == "exec-fabric-77" for r in rows)


def test_fabric_execute_deploy_skips_duplicate_idempotency_key(db, monkeypatch):
    spine = Device(name="f2-spine", ip_address="10.93.0.1", device_type="cisco_ios", status="online")
    leaf1 = Device(name="f2-leaf-1", ip_address="10.93.0.2", device_type="cisco_ios", status="online")
    db.add_all([spine, leaf1])
    db.commit()

    monkeypatch.setattr(
        "app.services.fabric_service.ChangeExecutionService.claim_idempotency",
        lambda *_args, **_kwargs: False,
    )

    out = FabricService(db).execute_deploy(
        spines=[int(spine.id)],
        leafs=[int(leaf1.id)],
        asn_base=65000,
        vni_base=10000,
        dry_run=False,
        pre_check_commands=[],
        verify_commands=[],
        rollback_on_error=True,
        canary_count=0,
        wave_size=0,
        stop_on_wave_failure=True,
        inter_wave_delay_seconds=0.0,
        idempotency_key="dup-fabric-1",
        approval_id=101,
        execution_id="exec-fabric-101",
    )

    summary = out["summary"]
    assert summary["skipped"] == 2
    assert summary["idempotency_key"] == "dup-fabric-1"
    assert summary["approval_id"] == 101
    assert summary["execution_id"] == "exec-fabric-101"
    assert all(str(r.get("status")) == "skipped_idempotent" for r in out["results"])
    assert all(int(r.get("approval_id")) == 101 for r in out["results"])
    assert all(str(r.get("execution_id")) == "exec-fabric-101" for r in out["results"])


def test_fabric_dry_run_includes_diff_summary(db):
    spine = Device(name="f3-spine", ip_address="10.94.0.1", device_type="cisco_ios", status="online")
    leaf = Device(name="f3-leaf-1", ip_address="10.94.0.2", device_type="cisco_ios", status="online")
    db.add_all([spine, leaf])
    db.flush()
    db.add(ConfigBackup(device_id=int(spine.id), raw_config="hostname OLD-SPINE\n!\n", is_golden=False))
    db.add(ConfigBackup(device_id=int(leaf.id), raw_config="hostname OLD-LEAF\n!\n", is_golden=False))
    db.commit()

    out = FabricService(db).execute_deploy(
        spines=[int(spine.id)],
        leafs=[int(leaf.id)],
        asn_base=65000,
        vni_base=10000,
        dry_run=True,
        pre_check_commands=[],
        verify_commands=[],
        rollback_on_error=True,
        canary_count=0,
        wave_size=0,
        stop_on_wave_failure=True,
        inter_wave_delay_seconds=0.0,
        idempotency_key=None,
        approval_id=33,
        execution_id="exec-fabric-diff-33",
    )

    rows = list(out.get("results") or [])
    assert len(rows) == 2
    for row in rows:
        diff = row.get("dry_run_diff") or {}
        assert "has_changes" in diff
        assert "added_lines" in diff
        assert "removed_lines" in diff
        assert isinstance(diff.get("preview"), list)


def test_fabric_post_check_failure_triggers_rollback_and_failure_status(db, monkeypatch):
    spine = Device(
        name="f4-spine",
        ip_address="10.95.0.1",
        device_type="cisco_ios",
        status="online",
        ssh_username="admin",
        ssh_password="pass",
    )
    leaf = Device(
        name="f4-leaf-1",
        ip_address="10.95.0.2",
        device_type="cisco_ios",
        status="online",
        ssh_username="admin",
        ssh_password="pass",
    )
    db.add_all([spine, leaf])
    db.commit()

    class _FakeDriver:
        def __init__(self):
            self.rollback_called = False

        def prepare_rollback(self, _name):
            return True

    class _FakeConnection:
        def __init__(self, info):
            self.info = info
            self.driver = _FakeDriver()

        def connect(self):
            return True

        def send_config_set(self, _commands):
            return "ok"

        def send_command(self, _cmd, read_timeout=20):
            return "% Invalid input detected"

        def rollback(self):
            self.driver.rollback_called = True
            return True

        def disconnect(self):
            return True

    monkeypatch.setattr("app.services.fabric_service.DeviceConnection", _FakeConnection)

    out = FabricService(db).execute_deploy(
        spines=[int(spine.id)],
        leafs=[int(leaf.id)],
        asn_base=65000,
        vni_base=10000,
        dry_run=False,
        pre_check_commands=[],
        verify_commands=["show bgp summary"],
        rollback_on_error=True,
        canary_count=0,
        wave_size=0,
        stop_on_wave_failure=True,
        inter_wave_delay_seconds=0.0,
        idempotency_key=None,
        approval_id=88,
        execution_id="exec-fabric-postcheck-88",
    )

    rows = list(out.get("results") or [])
    assert len(rows) == 2
    assert all(str(r.get("status") or "") == "postcheck_failed" for r in rows)
    assert all(bool((r.get("post_check") or {}).get("ok")) is False for r in rows)
    assert all(bool((r.get("rollback") or {}).get("attempted")) is True for r in rows)
    assert all(bool((r.get("rollback") or {}).get("success")) is True for r in rows)
    summary = out.get("summary") or {}
    assert int(summary.get("failed") or 0) == 2
    assert int(summary.get("success") or 0) == 0


def test_fabric_post_check_failure_halts_following_waves(db, monkeypatch):
    spine = Device(
        name="f5-spine",
        ip_address="10.96.0.1",
        device_type="cisco_ios",
        status="online",
        ssh_username="admin",
        ssh_password="pass",
    )
    leaf1 = Device(
        name="f5-leaf-1",
        ip_address="10.96.0.2",
        device_type="cisco_ios",
        status="online",
        ssh_username="admin",
        ssh_password="pass",
    )
    leaf2 = Device(
        name="f5-leaf-2",
        ip_address="10.96.0.3",
        device_type="cisco_ios",
        status="online",
        ssh_username="admin",
        ssh_password="pass",
    )
    db.add_all([spine, leaf1, leaf2])
    db.commit()

    class _FakeDriver:
        def prepare_rollback(self, _name):
            return True

    class _FakeConnection:
        def __init__(self, info):
            self.info = info
            self.driver = _FakeDriver()

        def connect(self):
            return True

        def send_config_set(self, _commands):
            return "ok"

        def send_command(self, _cmd, read_timeout=20):
            if str(self.info.host) == "10.96.0.1":
                return "% Invalid input detected"
            return "ok"

        def rollback(self):
            return True

        def disconnect(self):
            return True

    monkeypatch.setattr("app.services.fabric_service.DeviceConnection", _FakeConnection)

    out = FabricService(db).execute_deploy(
        spines=[int(spine.id)],
        leafs=[int(leaf1.id), int(leaf2.id)],
        asn_base=65000,
        vni_base=10000,
        dry_run=False,
        pre_check_commands=[],
        verify_commands=["show bgp summary"],
        rollback_on_error=True,
        canary_count=0,
        wave_size=1,
        stop_on_wave_failure=True,
        inter_wave_delay_seconds=0.0,
        idempotency_key=None,
        approval_id=99,
        execution_id="exec-fabric-wavehalt-99",
    )

    rows = list(out.get("results") or [])
    by_id = {int(r.get("device_id") or r.get("id")): r for r in rows}
    assert by_id[int(spine.id)]["status"] == "postcheck_failed"
    assert by_id[int(leaf1.id)]["status"] == "skipped_wave_halt"
    assert by_id[int(leaf2.id)]["status"] == "skipped_wave_halt"
    execution = out.get("execution") or {}
    assert execution.get("halted") is True
    assert execution.get("halted_wave") == 1
