import re
from typing import Any, Dict, List, Optional


class InventoryParser:
    name = "base"
    priority = 100

    def can_handle(self, device_type: str) -> bool:
        return True

    def collect(self, conn: Any) -> List[Dict[str, Any]]:
        raise NotImplementedError()


class CiscoShowInventoryParser(InventoryParser):
    name = "cisco_show_inventory"
    priority = 10

    _DOMESTIC_CISCO_LIKE_DEVICE_TYPES = {
        "dasan_nos",
        "dasan",
        "ubiquoss_l2",
        "ubiquoss_l3",
        "ubiquoss",
        "handream_sg",
        "handream",
        "piolink_pas",
        "soltech_switch",
        "coreedge_switch",
        "nst_switch",
    }

    def can_handle(self, device_type: str) -> bool:
        dt = str(device_type or "").lower()
        return (
            dt in ("cisco_ios", "cisco_ios_xe", "cisco_xe", "cisco_nxos", "cisco_wlc")
            or dt.startswith("cisco_")
            or dt in self._DOMESTIC_CISCO_LIKE_DEVICE_TYPES
        )

    @staticmethod
    def _normalize_text(s: Any) -> str:
        return str(s or "").strip()

    @staticmethod
    def _parse_textfsm(parsed: Any) -> List[Dict[str, Any]]:
        if not isinstance(parsed, list):
            return []
        rows = []
        for r in parsed:
            if not isinstance(r, dict):
                continue
            name = CiscoShowInventoryParser._normalize_text(r.get("name") or r.get("NAME") or r.get("slot") or r.get("module"))
            descr = CiscoShowInventoryParser._normalize_text(r.get("descr") or r.get("description") or r.get("DESCR"))
            pid = CiscoShowInventoryParser._normalize_text(r.get("pid") or r.get("PID") or r.get("productid"))
            sn = CiscoShowInventoryParser._normalize_text(r.get("sn") or r.get("serial") or r.get("serial_number") or r.get("SN"))
            if not (name or pid or sn or descr):
                continue
            rows.append(
                {
                    "name": name,
                    "description": descr,
                    "model_name": pid,
                    "serial_number": sn,
                }
            )
        return rows

    @staticmethod
    def _parse_raw(output: str) -> List[Dict[str, Any]]:
        text = str(output or "")
        if not text.strip():
            return []
        blocks = re.split(r"\n\s*\n", text)
        rows = []
        for b in blocks:
            name_m = re.search(r'NAME\s*:\s*"([^"]+)"', b, re.IGNORECASE)
            descr_m = re.search(r'DESCR\s*:\s*"([^"]+)"', b, re.IGNORECASE)
            pid_m = re.search(r"\bPID\s*:\s*([^,\n]+)", b, re.IGNORECASE)
            sn_m = re.search(r"\bSN\s*:\s*([^\s,\n]+)", b, re.IGNORECASE)
            if not (name_m or pid_m or sn_m or descr_m):
                continue
            rows.append(
                {
                    "name": CiscoShowInventoryParser._normalize_text(name_m.group(1) if name_m else ""),
                    "description": CiscoShowInventoryParser._normalize_text(descr_m.group(1) if descr_m else ""),
                    "model_name": CiscoShowInventoryParser._normalize_text(pid_m.group(1) if pid_m else ""),
                    "serial_number": CiscoShowInventoryParser._normalize_text(sn_m.group(1) if sn_m else ""),
                }
            )
        return rows

    def collect(self, conn: Any) -> List[Dict[str, Any]]:
        parsed = None
        raw = None
        try:
            parsed = conn.send_command("show inventory", use_textfsm=True)
        except Exception:
            parsed = None
        rows = self._parse_textfsm(parsed)
        if rows:
            return rows
        try:
            raw = conn.send_command("show inventory")
        except Exception:
            raw = None
        return self._parse_raw(raw or "")


class JuniperChassisHardwareParser(InventoryParser):
    name = "juniper_show_chassis_hardware"
    priority = 20

    def can_handle(self, device_type: str) -> bool:
        dt = str(device_type or "").lower()
        return dt in ("juniper_junos", "juniper") or dt.startswith("juniper")

    @staticmethod
    def _normalize_text(s: Any) -> str:
        return str(s or "").strip()

    @staticmethod
    def _parse_textfsm(parsed: Any) -> List[Dict[str, Any]]:
        if not isinstance(parsed, list):
            return []
        rows = []
        for r in parsed:
            if not isinstance(r, dict):
                continue
            item = JuniperChassisHardwareParser._normalize_text(r.get("item") or r.get("name") or r.get("ITEM"))
            descr = JuniperChassisHardwareParser._normalize_text(r.get("description") or r.get("descr") or r.get("DESCR"))
            part = JuniperChassisHardwareParser._normalize_text(r.get("part_number") or r.get("part") or r.get("pid") or r.get("PN"))
            sn = JuniperChassisHardwareParser._normalize_text(r.get("serial_number") or r.get("serial") or r.get("SN"))
            if not (item or part or sn or descr):
                continue
            rows.append({"name": item, "description": descr, "model_name": part, "serial_number": sn})
        return rows

    @staticmethod
    def _parse_raw(output: str) -> List[Dict[str, Any]]:
        text = str(output or "")
        if not text.strip():
            return []
        lines = [ln.rstrip("\n") for ln in text.splitlines() if ln.strip()]
        start = 0
        for i, ln in enumerate(lines):
            if ln.lower().startswith("item") and "serial" in ln.lower():
                start = i + 1
                break
        if start == 0:
            for i, ln in enumerate(lines):
                if "hardware inventory" in ln.lower():
                    start = i + 1
                    break
        rows = []
        for ln in lines[start:]:
            if ln.lower().startswith("item") and "serial" in ln.lower():
                continue
            parts = re.split(r"\s{2,}", ln.strip())
            if len(parts) < 2:
                continue
            item = parts[0].strip()
            descr = parts[-1].strip() if parts else ""
            serial = ""
            model = ""
            for tok in parts[1:-1]:
                if re.fullmatch(r"[A-Za-z0-9]{6,}", tok) and not serial:
                    serial = tok
                elif re.search(r"\d", tok) and not model:
                    model = tok
            rows.append({"name": item, "description": descr, "model_name": model, "serial_number": serial})
        return rows

    def collect(self, conn: Any) -> List[Dict[str, Any]]:
        parsed = None
        raw = None
        try:
            parsed = conn.send_command("show chassis hardware", use_textfsm=True)
        except Exception:
            parsed = None
        rows = self._parse_textfsm(parsed)
        if rows:
            return rows
        try:
            raw = conn.send_command("show chassis hardware")
        except Exception:
            raw = None
        return self._parse_raw(raw or "")


class AristaEosInventoryParser(InventoryParser):
    name = "arista_eos_inventory"
    priority = 15

    def can_handle(self, device_type: str) -> bool:
        dt = str(device_type or "").lower()
        return dt in ("arista_eos", "arista") or dt.startswith("arista")

    @staticmethod
    def _normalize_text(s: Any) -> str:
        return str(s or "").strip()

    @staticmethod
    def _parse_textfsm(parsed: Any) -> List[Dict[str, Any]]:
        if not isinstance(parsed, list):
            return []
        rows = []
        for r in parsed:
            if not isinstance(r, dict):
                continue
            name = AristaEosInventoryParser._normalize_text(r.get("name") or r.get("slot") or r.get("item") or r.get("component"))
            descr = AristaEosInventoryParser._normalize_text(r.get("description") or r.get("descr"))
            pid = AristaEosInventoryParser._normalize_text(r.get("pid") or r.get("part_number") or r.get("model") or r.get("pn"))
            sn = AristaEosInventoryParser._normalize_text(r.get("sn") or r.get("serial") or r.get("serial_number"))
            if not (name or pid or sn or descr):
                continue
            rows.append({"name": name, "description": descr, "model_name": pid, "serial_number": sn})
        return rows

    @staticmethod
    def _parse_show_version(raw: str) -> List[Dict[str, Any]]:
        text = str(raw or "")
        if not text.strip():
            return []
        model = ""
        serial = ""
        m = re.search(r"^\s*Model name\s*:\s*(.+)$", text, re.IGNORECASE | re.MULTILINE)
        if m:
            model = m.group(1).strip()
        m = re.search(r"^\s*Serial number\s*:\s*(.+)$", text, re.IGNORECASE | re.MULTILINE)
        if m:
            serial = m.group(1).strip()
        if not model and not serial:
            return []
        return [{"name": "Chassis", "description": "Arista EOS", "model_name": model, "serial_number": serial}]

    def collect(self, conn: Any) -> List[Dict[str, Any]]:
        for cmd in ("show inventory all", "show inventory"):
            try:
                parsed = conn.send_command(cmd, use_textfsm=True)
            except Exception:
                parsed = None
            rows = self._parse_textfsm(parsed)
            if rows:
                return rows

        for cmd in ("show version detail", "show version"):
            try:
                raw = conn.send_command(cmd)
            except Exception:
                raw = None
            rows = self._parse_show_version(raw or "")
            if rows:
                return rows
        return []


class HpeArubaInventoryParser(InventoryParser):
    name = "hpe_aruba_inventory"
    priority = 25

    def can_handle(self, device_type: str) -> bool:
        dt = str(device_type or "").lower()
        return dt in ("aruba_os", "hp_procurve", "hpe_comware", "hp_comware") or "aruba" in dt or dt.startswith("hp_") or dt.startswith("hpe_")

    @staticmethod
    def _parse_system_info(raw: str) -> List[Dict[str, Any]]:
        text = str(raw or "")
        if not text.strip():
            return []
        model = ""
        serial = ""
        descr = ""
        m = re.search(r"^\s*(Product\s+Number|Product\s+Name|Model)\s*:\s*(.+)$", text, re.IGNORECASE | re.MULTILINE)
        if m:
            model = m.group(2).strip()
        m = re.search(r"^\s*(Serial\s+Number|Chassis\s+Serial)\s*:\s*(.+)$", text, re.IGNORECASE | re.MULTILINE)
        if m:
            serial = m.group(2).strip()
        m = re.search(r"^\s*(System\s+Description|Description)\s*:\s*(.+)$", text, re.IGNORECASE | re.MULTILINE)
        if m:
            descr = m.group(2).strip()
        if not model and not serial:
            return []
        return [{"name": "Chassis", "description": descr or "HPE/Aruba", "model_name": model, "serial_number": serial}]

    @staticmethod
    def _parse_aos_cx_inventory(raw: str) -> List[Dict[str, Any]]:
        text = str(raw or "")
        if not text.strip():
            return []

        rows: List[Dict[str, Any]] = []
        current_name = ""
        current_values: Dict[str, str] = {}

        def _flush() -> None:
            nonlocal current_name, current_values
            if not current_name:
                current_values = {}
                return
            name = "Chassis" if current_name.lower() == "system" else current_name
            description = str(current_values.get("Product Name") or current_values.get("Vendor") or "").strip()
            model_name = str(current_values.get("Product Name") or current_values.get("Part Number") or "").strip()
            serial_number = str(current_values.get("Chassis Serial Nbr") or current_values.get("Serial Nbr") or "").strip()
            if name and (description or model_name or serial_number):
                rows.append(
                    {
                        "name": name,
                        "description": description,
                        "model_name": model_name,
                        "serial_number": serial_number,
                    }
                )
            current_name = ""
            current_values = {}

        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or set(stripped) == {"-"}:
                continue
            heading = re.match(r"^(.+?)\s*:\s*$", stripped)
            if heading and ":" not in heading.group(1):
                _flush()
                current_name = heading.group(1).strip()
                continue
            if ":" in stripped and current_name:
                key, value = stripped.split(":", 1)
                current_values[key.strip()] = value.strip()
        _flush()
        return rows

    @staticmethod
    def _parse_aos_switch_modules(raw: str) -> List[Dict[str, Any]]:
        text = str(raw or "")
        if not text.strip():
            return []

        rows: List[Dict[str, Any]] = []
        chassis_match = re.search(r"^\s*Chassis:\s*(.+)$", text, re.IGNORECASE | re.MULTILINE)
        chassis_name = str(chassis_match.group(1) if chassis_match else "").strip()
        first_serial = ""

        for line in text.splitlines():
            stripped = line.rstrip()
            if not stripped.strip() or re.match(r"^\s*(Status and Counters|-{3,}|Slot\s+Module Description)", stripped, re.IGNORECASE):
                continue
            match = re.match(r"^\s*(\d+)\s{2,}(.+?)\s{2,}([A-Z0-9]{6,})\s{2,}(\S+)\s*$", stripped)
            if not match:
                continue
            slot, description, serial, status = match.groups()
            if not first_serial:
                first_serial = serial.strip()
            rows.append(
                {
                    "name": f"Slot {slot.strip()}",
                    "description": description.strip(),
                    "model_name": description.strip(),
                    "serial_number": serial.strip(),
                    "status": status.strip(),
                }
            )

        if chassis_name:
            rows.insert(
                0,
                {
                    "name": "Chassis",
                    "description": chassis_name,
                    "model_name": chassis_name,
                    "serial_number": first_serial,
                },
            )
        return rows

    def collect(self, conn: Any) -> List[Dict[str, Any]]:
        for cmd in ("show inventory", "show modules", "show chassis", "show system information", "show system"):
            try:
                raw = conn.send_command(cmd)
            except Exception:
                raw = None
            if cmd == "show inventory":
                rows = self._parse_aos_cx_inventory(raw or "")
                if rows:
                    return rows
            if cmd == "show modules":
                rows = self._parse_aos_switch_modules(raw or "")
                if rows:
                    return rows
            rows = self._parse_system_info(raw or "")
            if rows:
                return rows
        return []


class HuaweiInventoryParser(InventoryParser):
    name = "huawei_inventory"
    priority = 30

    def can_handle(self, device_type: str) -> bool:
        dt = str(device_type or "").lower()
        return dt in ("huawei", "huawei_vrp", "hp_comware", "hpe_comware") or dt.startswith("huawei")

    @staticmethod
    def _parse_display_version(raw: str) -> Dict[str, str]:
        text = str(raw or "")
        model = ""
        m = re.search(r"^\s*Huawei\s+(\S+)\s+.*Version", text, re.IGNORECASE | re.MULTILINE)
        if m:
            model = m.group(1).strip()
        if not model:
            m = re.search(r"^\s*Device\s+Model\s*:\s*(.+)$", text, re.IGNORECASE | re.MULTILINE)
            if m:
                model = m.group(1).strip()
        if not model:
            m = re.search(r"^\s*BOARD TYPE\s*:\s*(.+)$", text, re.IGNORECASE | re.MULTILINE)
            if m:
                model = m.group(1).strip()
        if not model:
            m = re.search(r"^\s*H3C\s+(\S+)\s+uptime is", text, re.IGNORECASE | re.MULTILINE)
            if m:
                model = m.group(1).strip()
        return {"model": model}

    @staticmethod
    def _parse_display_esn(raw: str) -> str:
        text = str(raw or "")
        m = re.search(r"\bESN\b\s*:\s*([A-Za-z0-9]+)", text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
        m = re.search(r"^\s*([A-Za-z0-9]{8,})\s*$", text, re.MULTILINE)
        if m:
            return m.group(1).strip()
        return ""

    @staticmethod
    def _parse_display_device(raw: str) -> List[Dict[str, Any]]:
        text = str(raw or "")
        if not text.strip():
            return []
        rows: List[Dict[str, Any]] = []
        current: Optional[Dict[str, Any]] = None
        table_mode = False
        for ln in text.splitlines():
            line = ln.strip()
            if not line:
                continue
            if line.lower().startswith("slot ") and "type" in line.lower() and "description" in line.lower():
                table_mode = True
                continue
            if table_mode:
                if set(line) == {"-"}:
                    continue
                parts = re.split(r"\s{2,}", line)
                if len(parts) >= 6 and parts[0].isdigit():
                    slot, board_type = parts[0], parts[1]
                    description = parts[-1]
                    rows.append(
                        {
                            "name": f"Slot {slot}",
                            "description": description,
                            "model_name": board_type,
                            "serial_number": "",
                            "class_name": "module",
                        }
                    )
                    continue
            m = re.match(r"^slot\s+(\d+)\s*[:\-]", line, re.IGNORECASE)
            if m:
                if current:
                    rows.append(current)
                slot = m.group(1)
                current = {"name": f"Slot {slot}", "description": "", "model_name": "", "serial_number": "", "class_name": "module"}
                continue
            if current is None:
                continue
            m = re.match(r"^(board\s*type|type|boardname)\s*:\s*(.+)$", line, re.IGNORECASE)
            if m and not current.get("model_name"):
                current["model_name"] = m.group(2).strip()
                continue
            m = re.match(r"^(barcode|sn|serial\s*number|s/n)\s*:\s*(.+)$", line, re.IGNORECASE)
            if m and not current.get("serial_number"):
                current["serial_number"] = m.group(2).strip()
                continue
            m = re.match(r"^(description)\s*:\s*(.+)$", line, re.IGNORECASE)
            if m and not current.get("description"):
                current["description"] = m.group(2).strip()
                continue
        if current:
            rows.append(current)
        return [r for r in rows if r.get("name") and (r.get("model_name") or r.get("serial_number") or r.get("description"))]

    def collect(self, conn: Any) -> List[Dict[str, Any]]:
        modules: List[Dict[str, Any]] = []
        serial = ""
        model = ""
        try:
            modules = self._parse_display_device(conn.send_command("display device"))
        except Exception:
            modules = []
        try:
            serial = self._parse_display_esn(conn.send_command("display esn"))
        except Exception:
            serial = ""
        try:
            model = self._parse_display_version(conn.send_command("display version")).get("model") or ""
        except Exception:
            model = ""
        if not serial and not model and not modules:
            return []
        rows = [{"name": "Chassis", "description": "Huawei", "model_name": model, "serial_number": serial, "class_name": "chassis"}]
        rows.extend(modules)
        return rows


class AlcatelAosInventoryParser(InventoryParser):
    name = "alcatel_aos_inventory"
    priority = 35

    def can_handle(self, device_type: str) -> bool:
        dt = str(device_type or "").lower()
        return dt == "alcatel_aos" or dt.startswith("alcatel")

    @staticmethod
    def _parse_show_chassis(raw: str) -> List[Dict[str, Any]]:
        text = str(raw or "")
        if not text.strip():
            return []

        rows: List[Dict[str, Any]] = []
        current: Optional[Dict[str, Any]] = None

        def _flush() -> None:
            nonlocal current
            if current and (current.get("model_name") or current.get("serial_number") or current.get("description")):
                rows.append(current)
            current = None

        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            match = re.match(r"^Chassis\s+(\d+)$", stripped, re.IGNORECASE)
            if match:
                _flush()
                current = {
                    "name": f"Chassis {match.group(1)}",
                    "description": "",
                    "model_name": "",
                    "serial_number": "",
                }
                continue
            if current is None or ":" not in stripped:
                continue
            key, value = stripped.split(":", 1)
            key_lower = key.strip().lower()
            normalized = value.strip().rstrip(",")
            if key_lower == "model name":
                current["model_name"] = normalized
            elif key_lower == "description":
                current["description"] = normalized
            elif key_lower == "serial number":
                current["serial_number"] = normalized
        _flush()
        return rows

    def collect(self, conn: Any) -> List[Dict[str, Any]]:
        try:
            raw = conn.send_command("show chassis")
        except Exception:
            raw = None
        return self._parse_show_chassis(raw or "")


class F5BigIpInventoryParser(InventoryParser):
    name = "f5_bigip_inventory"
    priority = 36

    def can_handle(self, device_type: str) -> bool:
        dt = str(device_type or "").lower()
        return dt == "f5_ltm" or dt.startswith("f5")

    @staticmethod
    def _parse_show_sys_hardware(raw: str) -> List[Dict[str, Any]]:
        text = str(raw or "")
        if not text.strip():
            return []

        rows: List[Dict[str, Any]] = []
        model = ""
        serial = ""

        match = re.search(r"^\s*Hardware Version\s+Name:\s*(.+)$", text, re.IGNORECASE | re.MULTILINE)
        if match:
            model = match.group(1).strip()
        match = re.search(r"^\s*Chassis Serial\s+([A-Za-z0-9]+)\s*$", text, re.IGNORECASE | re.MULTILINE)
        if match:
            serial = match.group(1).strip()
        if model or serial:
            rows.append(
                {
                    "name": "Chassis",
                    "description": "F5 BIG-IP",
                    "model_name": model,
                    "serial_number": serial,
                }
            )

        feature_section = False
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.lower().startswith("hardware features"):
                feature_section = True
                continue
            if not feature_section or stripped.lower().startswith("type") or set(stripped) == {"-"}:
                continue
            match = re.match(r"^(?P<kind>\S+)\s+(?P<name>\S+)\s+(?P<revision>\S+)\s+(?P<status>\S+)$", stripped)
            if not match:
                continue
            rows.append(
                {
                    "name": match.group("name"),
                    "description": match.group("kind"),
                    "model_name": match.group("kind"),
                    "serial_number": "",
                    "status": match.group("status"),
                    "revision": match.group("revision"),
                }
            )
        return rows

    def collect(self, conn: Any) -> List[Dict[str, Any]]:
        try:
            raw = conn.send_command("show sys hardware")
        except Exception:
            raw = None
        return self._parse_show_sys_hardware(raw or "")


class GenericHeuristicInventoryParser(InventoryParser):
    name = "generic_heuristic_inventory"
    priority = 90

    @staticmethod
    def _normalize_text(s: Any) -> str:
        return str(s or "").strip()

    @staticmethod
    def _parse_cisco_like_blocks(output: str) -> List[Dict[str, Any]]:
        text = str(output or "")
        if not text.strip():
            return []
        blocks = re.split(r"\n\s*\n", text)
        rows: List[Dict[str, Any]] = []
        for b in blocks:
            name_m = re.search(r'NAME\s*:\s*"([^"]+)"', b, re.IGNORECASE)
            descr_m = re.search(r'DESCR\s*:\s*"([^"]+)"', b, re.IGNORECASE)
            pid_m = re.search(r"\bPID\s*:\s*([^,\n]+)", b, re.IGNORECASE)
            sn_m = re.search(r"\bSN\s*:\s*([^\s,\n]+)", b, re.IGNORECASE)
            if not (name_m or pid_m or sn_m or descr_m):
                continue
            rows.append(
                {
                    "name": GenericHeuristicInventoryParser._normalize_text(name_m.group(1) if name_m else "Chassis"),
                    "description": GenericHeuristicInventoryParser._normalize_text(descr_m.group(1) if descr_m else ""),
                    "model_name": GenericHeuristicInventoryParser._normalize_text(pid_m.group(1) if pid_m else ""),
                    "serial_number": GenericHeuristicInventoryParser._normalize_text(sn_m.group(1) if sn_m else ""),
                }
            )
        return rows

    @staticmethod
    def _find_first(text: str, patterns: List[str]) -> str:
        for pattern in patterns:
            m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if m:
                return str(m.group(1)).strip()
        return ""

    @staticmethod
    def _parse_key_value_style(output: str) -> List[Dict[str, Any]]:
        text = str(output or "")
        if not text.strip():
            return []

        model = GenericHeuristicInventoryParser._find_first(
            text,
            [
                r"^\s*(?:Model(?:\s+Name)?|System\s+Type|System\s+Model(?:\s+ID)?|Product\s+Name|Product\s+Model|Platform|Chassis\s+Type|Appliance\s+Model)\s*:\s*(.+)$",
                r"^\s*Model\s+ID\s*:\s*(.+)$",
            ],
        )
        serial = GenericHeuristicInventoryParser._find_first(
            text,
            [
                r"^\s*(?:Serial(?:\s+Number)?|Service\s+Tag|System\s+Serial(?:\s+Number)?|Serial-Number|Chassis\s+Serial)\s*:\s*(.+)$",
            ],
        )
        descr = GenericHeuristicInventoryParser._find_first(
            text,
            [
                r"^\s*(?:System\s+Description|Description|Version)\s*:\s*(.+)$",
            ],
        )

        if not model and not serial:
            return []
        return [
            {
                "name": "Chassis",
                "description": descr or "Heuristic Inventory",
                "model_name": model,
                "serial_number": serial,
            }
        ]

    def can_handle(self, device_type: str) -> bool:
        return True

    def collect(self, conn: Any) -> List[Dict[str, Any]]:
        commands = (
            "show inventory",
            "show system information",
            "show system info",
            "show system",
            "show version",
            "display version",
            "get system status",
        )
        for cmd in commands:
            try:
                raw = conn.send_command(cmd)
            except Exception:
                raw = None
            rows = self._parse_cisco_like_blocks(raw or "")
            if rows:
                return rows
            rows = self._parse_key_value_style(raw or "")
            if rows:
                return rows
        return []


def get_inventory_parsers() -> List[InventoryParser]:
    parsers: List[InventoryParser] = [
        CiscoShowInventoryParser(),
        AristaEosInventoryParser(),
        JuniperChassisHardwareParser(),
        HpeArubaInventoryParser(),
        HuaweiInventoryParser(),
        AlcatelAosInventoryParser(),
        F5BigIpInventoryParser(),
        GenericHeuristicInventoryParser(),
    ]
    parsers.sort(key=lambda p: int(getattr(p, "priority", 100)))
    return parsers


def inventory_parser_support_matrix() -> List[Dict[str, Any]]:
    sample_device_types = [
        "cisco_ios",
        "cisco_nxos",
        "arista_eos",
        "juniper_junos",
        "hpe_aruba",
        "huawei_vrp",
        "dasan_nos",
        "ubiquoss_l2",
        "handream_sg",
        "piolink_pas",
        "soltech_switch",
        "coreedge_switch",
        "nst_switch",
    ]
    rows: List[Dict[str, Any]] = []
    for parser in get_inventory_parsers():
        supported = []
        for dt in sample_device_types:
            try:
                if parser.can_handle(dt):
                    supported.append(dt)
            except Exception:
                continue
        rows.append(
            {
                "parser": getattr(parser, "name", parser.__class__.__name__),
                "priority": int(getattr(parser, "priority", 100)),
                "sample_supported_device_types": supported,
            }
        )
    return rows
