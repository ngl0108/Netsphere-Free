import csv
import json

from tools import export_real_device_acceptance_plan as tool


def test_build_real_device_acceptance_plan_assigns_profiles_and_waves():
    payload = {
        "generated_at": "2026-03-09T00:00:00+00:00",
        "summary": {"readiness": {"full": 1, "extended": 1, "basic": 1}},
        "rows": [
            {"device_type": "cisco_nxos", "readiness": "full", "readiness_score": 100, "covered": True},
            {"device_type": "fortinet", "readiness": "basic", "readiness_score": 30, "covered": True},
            {"device_type": "ubiquoss_l3", "readiness": "extended", "readiness_score": 60, "covered": True},
        ],
    }

    out = tool.build_real_device_acceptance_plan(payload)

    assert out["summary"]["total_device_types"] == 3
    assert out["summary"]["wave_counts"]["wave_1"] == 3
    assert out["summary"]["wave_counts"]["wave_2"] == 0
    by_type = {row["device_type"]: row for row in out["rows"]}
    assert by_type["cisco_nxos"]["command_profile"] == "cisco_nxos"
    assert "vxlan_overlay_visibility" in by_type["cisco_nxos"]["mandatory_scenarios"]
    assert by_type["fortinet"]["feature_class"] == "security"
    assert "northbound_event_delivery" in by_type["fortinet"]["mandatory_scenarios"]
    assert by_type["fortinet"]["suggested_wave"] == 1
    assert by_type["ubiquoss_l3"]["command_profile"] == "domestic_switch"
    assert by_type["ubiquoss_l3"]["suggested_wave"] == 1


def test_export_real_device_acceptance_plan_writes_json_md_and_csv(tmp_path):
    matrix_path = tmp_path / "vendor.json"
    json_out = tmp_path / "acceptance.json"
    md_out = tmp_path / "acceptance.md"
    csv_out = tmp_path / "acceptance.csv"
    matrix_path.write_text(
        json.dumps(
            {
                "generated_at": "2026-03-09T00:00:00+00:00",
                "summary": {"readiness": {"full": 1}},
                "rows": [
                    {
                        "device_type": "cisco_ios_xe",
                        "readiness": "full",
                        "readiness_score": 100,
                        "covered": True,
                        "driver_modes": ["generic"],
                        "fixture_groups": ["global_switch"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    payload = tool.build_real_device_acceptance_plan(json.loads(matrix_path.read_text(encoding="utf-8")))
    tool._write_json(json_out, payload)
    tool._write_markdown(md_out, payload)
    tool._write_csv(csv_out, payload)

    data = json.loads(json_out.read_text(encoding="utf-8"))
    assert data["rows"][0]["device_type"] == "cisco_ios_xe"
    assert "Cisco IOS / IOS XE" in md_out.read_text(encoding="utf-8")
    with csv_out.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert rows[0]["device_type"] == "cisco_ios_xe"
    assert "show version" in rows[0]["required_commands"]
