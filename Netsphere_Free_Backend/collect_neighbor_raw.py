import argparse
import os
import re
import sys
from datetime import datetime

sys.path.append(os.getcwd())

from app.db.session import SessionLocal
from app.models.credentials import SnmpCredentialProfile
from app.models.device import Device, Site
from app.services.ssh_service import DeviceConnection, DeviceInfo


def _slug(s: str) -> str:
    s = str(s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")[:120] or "cmd"


def _default_commands(device_type: str) -> list[str]:
    dt = str(device_type or "").lower()
    if "juniper" in dt or "junos" in dt:
        return [
            "show lldp neighbors detail",
            "show lldp neighbors",
            "show lldp neighbors extensive",
        ]
    if "huawei" in dt or "vrp" in dt:
        return [
            "display lldp neighbor verbose",
            "display lldp neighbor",
        ]
    return [
        "show lldp neighbors detail",
        "show lldp neighbors",
        "show lldp neighbor",
        "show cdp neighbors detail",
        "show cdp neighbors",
    ]


def _redact(text: str) -> str:
    t = str(text or "")
    t = re.sub(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", "X.X.X.X", t)
    t = re.sub(r"\b[0-9a-f]{4}\.[0-9a-f]{4}\.[0-9a-f]{4}\b", "XXXX.XXXX.XXXX", t, flags=re.IGNORECASE)
    t = re.sub(r"\b[0-9a-f]{2}(?::[0-9a-f]{2}){5}\b", "XX:XX:XX:XX:XX:XX", t, flags=re.IGNORECASE)
    t = re.sub(r"\b([A-Z]{2,5}\d?/\d+(?:/\d+)*)\b", r"\1", t)
    return t


def _resolve_device_and_profile(device_id: int) -> tuple[Device | None, SnmpCredentialProfile | None]:
    db = SessionLocal()
    try:
        device = db.query(Device).filter(Device.id == int(device_id)).first()
        if not device:
            return None, None
        profile = None
        if getattr(device, "site_id", None):
            site = db.query(Site).filter(Site.id == int(device.site_id)).first()
            pid = getattr(site, "snmp_profile_id", None) if site else None
            if pid:
                profile = db.query(SnmpCredentialProfile).filter(SnmpCredentialProfile.id == int(pid)).first()
        return device, profile
    finally:
        db.close()


def _build_device_info(device: Device, profile: SnmpCredentialProfile | None) -> DeviceInfo | None:
    host = str(getattr(device, "ip_address", None) or "").strip()
    if not host:
        return None
    username = str(getattr(device, "ssh_username", None) or getattr(profile, "ssh_username", None) or "admin")
    password = getattr(device, "ssh_password", None) or getattr(profile, "ssh_password", None)
    if not password:
        return None
    secret = getattr(device, "enable_password", None) or getattr(profile, "enable_password", None)
    port = int(getattr(device, "ssh_port", None) or getattr(profile, "ssh_port", None) or 22)
    device_type = str(getattr(device, "device_type", None) or getattr(profile, "device_type", None) or "cisco_ios")
    return DeviceInfo(host=host, username=username, password=password, secret=secret, port=port, device_type=device_type)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device-id", type=int, required=True)
    ap.add_argument("--out-dir", type=str, default=os.path.join("tests", "fixtures", "neighbor_raw"))
    ap.add_argument("--redact", action="store_true")
    ap.add_argument("--cmd", action="append", default=[])
    args = ap.parse_args()

    device, profile = _resolve_device_and_profile(args.device_id)
    if not device:
        print("device not found")
        raise SystemExit(2)

    info = _build_device_info(device, profile)
    if not info:
        print("ssh credentials missing (device or site profile)")
        raise SystemExit(3)

    cmds = args.cmd or _default_commands(info.device_type)
    out_dir = os.path.abspath(args.out_dir)
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    conn = DeviceConnection(info)
    if not conn.connect():
        print(f"ssh connect failed: {conn.last_error}")
        raise SystemExit(4)

    saved = 0
    try:
        for cmd in cmds:
            cmd_s = str(cmd or "").strip()
            if not cmd_s:
                continue
            try:
                raw = conn.send_command(cmd_s, use_textfsm=False)
            except Exception as e:
                raw = f"[ERROR] {e}"
            if args.redact:
                raw = _redact(raw)
            path = os.path.join(out_dir, f"dev{device.id}_{_slug(info.device_type)}_{ts}_{_slug(cmd_s)}.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write(raw or "")
                if raw and not raw.endswith("\n"):
                    f.write("\n")
            print(f"saved: {path}")
            saved += 1
    finally:
        try:
            conn.disconnect()
        except Exception:
            pass

    print(f"done: {saved} file(s)")


if __name__ == "__main__":
    main()

