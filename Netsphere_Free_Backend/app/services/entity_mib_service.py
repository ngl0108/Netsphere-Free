from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.device import Device
from app.models.device_inventory import DeviceInventoryItem
from app.services.snmp_service import SnmpManager


class EntityMibService:
    _ENT_PHYSICAL_BASE = "1.3.6.1.2.1.47.1.1.1.1"

    _CLASS_MAP = {
        1: "other",
        2: "unknown",
        3: "chassis",
        4: "backplane",
        5: "container",
        6: "powerSupply",
        7: "fan",
        8: "sensor",
        9: "module",
        10: "port",
        11: "stack",
        12: "cpu",
    }

    @staticmethod
    def _int_or_none(v: Optional[str]) -> Optional[int]:
        if v is None:
            return None
        try:
            return int(str(v).strip())
        except Exception:
            return None

    @staticmethod
    def fetch_inventory(ip: str, community: str) -> List[Dict[str, Any]]:
        mgr = SnmpManager(ip, community)

        cols = {
            "description": f"{EntityMibService._ENT_PHYSICAL_BASE}.2",
            "contained_in": f"{EntityMibService._ENT_PHYSICAL_BASE}.4",
            "class_id": f"{EntityMibService._ENT_PHYSICAL_BASE}.5",
            "name": f"{EntityMibService._ENT_PHYSICAL_BASE}.7",
            "hardware_rev": f"{EntityMibService._ENT_PHYSICAL_BASE}.8",
            "firmware_rev": f"{EntityMibService._ENT_PHYSICAL_BASE}.9",
            "software_rev": f"{EntityMibService._ENT_PHYSICAL_BASE}.10",
            "serial_number": f"{EntityMibService._ENT_PHYSICAL_BASE}.11",
            "mfg_name": f"{EntityMibService._ENT_PHYSICAL_BASE}.12",
            "model_name": f"{EntityMibService._ENT_PHYSICAL_BASE}.13",
            "is_fru": f"{EntityMibService._ENT_PHYSICAL_BASE}.16",
        }

        data_by_col: Dict[str, Dict[int, str]] = {k: mgr.walk_table_column(oid) for k, oid in cols.items()}
        idxs = set()
        for m in data_by_col.values():
            idxs.update(m.keys())

        items: List[Dict[str, Any]] = []
        for idx in sorted(idxs):
            class_id = EntityMibService._int_or_none(data_by_col["class_id"].get(idx))
            is_fru_raw = data_by_col["is_fru"].get(idx)
            is_fru = None
            if is_fru_raw is not None:
                is_fru = str(is_fru_raw).strip().lower() in ("1", "true", "yes")

            contained_in = EntityMibService._int_or_none(data_by_col["contained_in"].get(idx))
            parent_index = contained_in if contained_in and contained_in > 0 else None
            items.append(
                {
                    "ent_physical_index": idx,
                    "parent_index": parent_index,
                    "contained_in": contained_in,
                    "class_id": class_id,
                    "class_name": EntityMibService._CLASS_MAP.get(class_id, "unknown") if class_id else None,
                    "name": data_by_col["name"].get(idx),
                    "description": data_by_col["description"].get(idx),
                    "model_name": data_by_col["model_name"].get(idx),
                    "serial_number": data_by_col["serial_number"].get(idx),
                    "mfg_name": data_by_col["mfg_name"].get(idx),
                    "hardware_rev": data_by_col["hardware_rev"].get(idx),
                    "firmware_rev": data_by_col["firmware_rev"].get(idx),
                    "software_rev": data_by_col["software_rev"].get(idx),
                    "is_fru": is_fru,
                }
            )

        return items

    @staticmethod
    def refresh_device_inventory(db: Session, device: Device) -> int:
        if not device or not device.ip_address or not device.snmp_community:
            return 0

        rows = EntityMibService.fetch_inventory(device.ip_address, device.snmp_community)
        if not rows:
            return 0

        now = datetime.now()
        count = 0
        chassis_candidate = None

        for r in rows:
            idx = r.get("ent_physical_index")
            if idx is None:
                continue
            item = (
                db.query(DeviceInventoryItem)
                .filter(DeviceInventoryItem.device_id == device.id, DeviceInventoryItem.ent_physical_index == int(idx))
                .first()
            )
            if not item:
                item = DeviceInventoryItem(device_id=device.id, ent_physical_index=int(idx))
                db.add(item)
                db.flush()

            item.parent_index = r.get("parent_index")
            item.contained_in = r.get("contained_in")
            item.class_id = r.get("class_id")
            item.class_name = r.get("class_name")
            item.name = r.get("name")
            item.description = r.get("description")
            item.model_name = r.get("model_name")
            item.serial_number = r.get("serial_number")
            item.mfg_name = r.get("mfg_name")
            item.hardware_rev = r.get("hardware_rev")
            item.firmware_rev = r.get("firmware_rev")
            item.software_rev = r.get("software_rev")
            item.is_fru = r.get("is_fru")
            item.last_seen = now
            count += 1

            if item.class_id == 3 and (not chassis_candidate or (item.ent_physical_index < chassis_candidate.ent_physical_index)):
                chassis_candidate = item

        if chassis_candidate:
            if chassis_candidate.model_name and (not device.model or device.model == "Unknown"):
                device.model = chassis_candidate.model_name
            if chassis_candidate.serial_number and not device.serial_number:
                device.serial_number = chassis_candidate.serial_number

        return count
