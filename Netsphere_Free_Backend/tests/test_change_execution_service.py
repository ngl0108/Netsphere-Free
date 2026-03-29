from app.services.change_execution_service import ChangeExecutionService


def test_build_waves_supports_canary_and_wave_size():
    waves = ChangeExecutionService.build_waves([1, 2, 3, 4, 5], canary_count=1, wave_size=2)
    assert waves == [[1], [2, 3], [4, 5]]


def test_execute_wave_batches_halts_and_marks_remaining_skipped():
    waves = [[10], [20], [30]]

    def run_wave(ids, wave_no):
        did = int(ids[0])
        if did == 20:
            return [{"id": did, "status": "failed", "error": "boom", "wave": wave_no}]
        return [{"id": did, "status": "success", "wave": wave_no}]

    out = ChangeExecutionService.execute_wave_batches(
        waves,
        run_wave,
        stop_on_wave_failure=True,
        inter_wave_delay_seconds=0.0,
    )

    rows = out["results"]
    assert len(rows) == 3
    assert rows[0]["status"] == "success"
    assert rows[1]["status"] == "failed"
    assert rows[2]["status"] == "skipped_wave_halt"
    assert out["execution"]["halted"] is True
    assert out["execution"]["halted_wave"] == 2


def test_change_kpi_payload_infers_post_check_failure_from_status():
    payload = ChangeExecutionService._build_change_kpi_payload(
        {
            "device_id": 10,
            "status": "postcheck_failed",
            "error": "Post-check failed after deploy",
        },
        change_type="template_deploy",
    )
    assert payload is not None
    assert payload["status"] == "failed"
    assert payload["post_check_failed"] is True
    assert payload["failure_cause"] == "post_check_failed"


def test_change_kpi_payload_marks_post_check_rollback_failed_when_rollback_fails():
    payload = ChangeExecutionService._build_change_kpi_payload(
        {
            "device_id": 11,
            "status": "postcheck_failed",
            "rollback_attempted": True,
            "rollback_success": False,
            "error": "Post-check failed and rollback failed",
        },
        change_type="fabric_deploy",
    )
    assert payload is not None
    assert payload["post_check_failed"] is True
    assert payload["rollback_attempted"] is True
    assert payload["rollback_success"] is False
    assert payload["failure_cause"] == "post_check_failed_rollback_failed"
