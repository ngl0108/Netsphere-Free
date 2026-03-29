import io
import json
import zipfile

from app.models.settings import SystemSetting


def _make_bundle_bytes(settings: dict) -> bytes:
    buf = io.BytesIO()
    payload = {
        "generated_at": "2026-02-25T00:00:00Z",
        "settings": dict(settings or {}),
    }
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("meta.json", json.dumps(payload, ensure_ascii=False))
    return buf.getvalue()


def test_support_restore_requires_admin_role(client, normal_user_token):
    bundle = _make_bundle_bytes({"hostname": "restored-controller"})
    res = client.post(
        "/api/v1/support/restore",
        data={"apply": "true", "restore_settings": "true"},
        files={"bundle": ("support_bundle.zip", bundle, "application/zip")},
        headers=normal_user_token,
    )
    assert res.status_code == 403


def test_support_restore_preview_does_not_apply(client, admin_user_token, db):
    row = SystemSetting(key="hostname", value="before-preview")
    db.add(row)
    db.commit()

    bundle = _make_bundle_bytes({"hostname": "preview-controller"})
    res = client.post(
        "/api/v1/support/restore",
        data={"apply": "false", "restore_settings": "true"},
        files={"bundle": ("support_bundle.zip", bundle, "application/zip")},
        headers=admin_user_token,
    )
    assert res.status_code == 200
    body = res.json()
    if isinstance(body, dict) and "data" in body:
        body = body["data"]
    assert str(body.get("status")) == "preview"

    db.refresh(row)
    assert str(row.value) == "before-preview"


def test_support_restore_apply_updates_settings(client, admin_user_token, db):
    row = SystemSetting(key="hostname", value="before-apply")
    db.add(row)
    db.commit()

    bundle = _make_bundle_bytes(
        {
            "hostname": "after-apply",
            "smtp_password": "masked-should-be-skipped",
        }
    )
    res = client.post(
        "/api/v1/support/restore",
        data={"apply": "true", "restore_settings": "true"},
        files={"bundle": ("support_bundle.zip", bundle, "application/zip")},
        headers=admin_user_token,
    )
    assert res.status_code == 200
    body = res.json()
    if isinstance(body, dict) and "data" in body:
        body = body["data"]
    assert str(body.get("status")) == "applied"
    assert int(((body.get("restored") or {}).get("settings") or 0)) >= 1

    db.refresh(row)
    assert str(row.value) == "after-apply"
