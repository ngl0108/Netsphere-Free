import zlib
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.device import Device
from app.models.device_inventory import DeviceInventoryItem
from app.services.inventory_parsers import get_inventory_parsers


class InventorySshService:
    @staticmethod
    def _stable_index(device_id: int, name: str, pid: str, serial: str) -> int:
        key = f"{device_id}|{name}|{pid}|{serial}".encode("utf-8", errors="ignore")
        v = zlib.crc32(key) & 0xFFFFFFFF
        return 1000000000 + (v % 900000000)

    @staticmethod
    def refresh_device_inventory_from_ssh(db: Session, device: Device, conn: Any) -> int:
        if not device or not conn:
            return 0

        rows: List[Dict[str, Any]] = []
        device_type = getattr(device, "device_type", None)
        for p in get_inventory_parsers():
            if not p.can_handle(device_type):
                continue
            try:
                rows = p.collect(conn) or []
            except Exception:
                rows = []
            if rows:
                break
        if not rows:
            return 0

        now = datetime.now()
        chassis_idx = None
        for r in rows:
            cls = str(r.get("class_name") or InventorySshService._infer_class_name(str(r.get("name") or ""), str(r.get("description") or ""))).lower()
            if cls == "chassis" and not chassis_idx:
                chassis_idx = InventorySshService._stable_index(
                    device.id,
                    str(r.get("name") or ""),
                    str(r.get("model_name") or ""),
                    str(r.get("serial_number") or ""),
                )

        count = 0
        for r in rows:
            name = str(r.get("name") or "")
            model = str(r.get("model_name") or "")
            serial = str(r.get("serial_number") or "")
            descr = str(r.get("description") or "")
            idx = InventorySshService._stable_index(device.id, name, model, serial)
            item = (
                db.query(DeviceInventoryItem)
                .filter(DeviceInventoryItem.device_id == device.id, DeviceInventoryItem.ent_physical_index == idx)
                .first()
            )
            if not item:
                item = DeviceInventoryItem(device_id=device.id, ent_physical_index=idx)
                db.add(item)
                db.flush()

            cls_name = str(r.get("class_name") or InventorySshService._infer_class_name(name, descr))
            item.class_name = cls_name
            item.class_id = 3 if cls_name == "chassis" else 9
            item.name = name or None
            item.description = descr or None
            item.model_name = model or None
            item.serial_number = serial or None
            item.mfg_name = None
            item.parent_index = None if (chassis_idx is None or idx == chassis_idx) else chassis_idx
            item.last_seen = now
            count += 1

            if item.class_id == 3:
                if item.model_name and (not device.model or device.model == "Unknown"):
                    device.model = item.model_name
                if item.serial_number and not device.serial_number:
                    device.serial_number = item.serial_number

        return count

    @staticmethod
    def _infer_class_name(name: str, descr: str) -> str:
        t = f"{name} {descr}".lower()
        if "chassis" in t:
            return "chassis"
        if "power" in t or "psu" in t or "powersupply" in t:
            return "powerSupply"
        if "fan" in t:
            return "fan"
        if "transceiver" in t or "sfp" in t or "qsfp" in t:
            return "port"
        return "module"
