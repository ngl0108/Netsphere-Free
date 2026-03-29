"""
ZTP Service: Cisco PnP 프로토콜 처리 및 Day-0 Config 생성
"""
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Optional, Dict, Any
import logging
from sqlalchemy.orm import Session

from app.models.ztp_queue import ZtpQueue, ZtpStatus
from app.models.device import Device, Site, ConfigTemplate
from app.services.template_service import TemplateRenderer
from app.services.device_support_policy_service import DeviceSupportPolicyService
from app.services.license_policy_service import LicensePolicyService, LicensePolicyViolation

logger = logging.getLogger(__name__)


class ZtpService:
    """
    Zero Touch Provisioning Service
    - Cisco PnP XML 파싱
    - Day-0 Config 생성
    - 장비 자동 개통
    """

    def __init__(self, db: Session):
        self.db = db

    # ================================================================
    # 1. Cisco PnP XML 파싱
    # ================================================================
    def parse_pnp_request(self, xml_body: str) -> Dict[str, Any]:
        """
        Cisco PnP "WORK-REQUEST" XML을 파싱하여 장비 정보 추출.
        
        Expected XML:
        <pnp xmlns="urn:cisco:pnp:work-info">
          <info version="1.0" udi="PID:C9300-24P,VID:V01,SN:FCW12345678"/>
          <deviceInfo>
            <platformName>C9300-24P</platformName>
            <serialNumber>FCW12345678</serialNumber>
            <hwRevision>V01</hwRevision>
            <versionString>17.03.05</versionString>
            <hostname>Switch</hostname>
          </deviceInfo>
        </pnp>
        """
        try:
            # Namespace 제거 (간단한 파싱을 위해)
            xml_clean = re.sub(r'xmlns="[^"]+"', '', xml_body)
            root = ET.fromstring(xml_clean)
            
            device_info = root.find('.//deviceInfo')
            if device_info is None:
                # Fallback: info 태그에서 UDI 파싱
                info_tag = root.find('.//info')
                if info_tag is not None:
                    udi = info_tag.get('udi', '')
                    # UDI Format: PID:xxxx,VID:xxx,SN:xxxxxxx
                    sn_match = re.search(r'SN:([A-Z0-9]+)', udi)
                    pid_match = re.search(r'PID:([A-Z0-9\-]+)', udi)
                    return {
                        "serial_number": sn_match.group(1) if sn_match else None,
                        "platform": pid_match.group(1) if pid_match else None,
                        "software_version": None,
                        "hostname": None
                    }
                return {}

            return {
                "serial_number": self._get_text(device_info, 'serialNumber'),
                "platform": self._get_text(device_info, 'platformName'),
                "software_version": self._get_text(device_info, 'versionString'),
                "hostname": self._get_text(device_info, 'hostname')
            }
        except ET.ParseError as e:
            logger.warning("ZTP XML parse error error=%s", e)
            return {}

    def _get_text(self, parent, tag: str) -> Optional[str]:
        elem = parent.find(tag)
        return elem.text.strip() if elem is not None and elem.text else None

    # ================================================================
    # 2. ZTP Queue 관리
    # ================================================================
    def handle_discovery(self, device_info: Dict, source_ip: str) -> ZtpQueue:
        """
        PnP Discovery 요청 처리.
        - 기존 시리얼이 있으면 업데이트
        - 없으면 새로 생성. 
          [NEW] 만약 DB에 이미 등록된 시리얼(Device)이라면, 자동으로 매칭되어 'READY' 상태로 전환 (RMA/재설치 시나리오)
        """
        serial = device_info.get("serial_number")
        if not serial:
            raise ValueError("Serial Number is required")

        existing = self.db.query(ZtpQueue).filter(ZtpQueue.serial_number == serial).first()
        
        if existing:
            # 기존 항목 업데이트
            existing.ip_address = source_ip
            existing.platform = device_info.get("platform") or existing.platform
            existing.software_version = device_info.get("software_version") or existing.software_version
            existing.hostname = device_info.get("hostname") or existing.hostname
            existing.updated_at = datetime.now()
            self.db.commit()
            return existing
        
        # [NEW] Check for known device in inventory (Inventory Match)
        known_device = self.db.query(Device).filter(Device.serial_number == serial).first()
        
        status = ZtpStatus.NEW.value
        assigned_site_id = None
        target_hostname = None
        suggested_device_id = None
        last_message = None

        if known_device:
            status = ZtpStatus.READY.value
            assigned_site_id = known_device.site_id
            target_hostname = known_device.hostname
            suggested_device_id = known_device.id
            last_message = f"Auto-matched to existing device '{known_device.name}' (ID: {known_device.id})"

        # 신규 항목 생성
        new_entry = ZtpQueue(
            serial_number=serial,
            platform=device_info.get("platform"),
            software_version=device_info.get("software_version"),
            hostname=device_info.get("hostname"),
            ip_address=source_ip,
            status=status,
            assigned_site_id=assigned_site_id,
            target_hostname=target_hostname,
            suggested_device_id=suggested_device_id,
            last_message=last_message
        )
        self.db.add(new_entry)
        self.db.commit()
        self.db.refresh(new_entry)
        return new_entry

    # ================================================================
    # 3. Day-0 Config 생성
    # ================================================================
    def generate_day0_config(self, queue_item: ZtpQueue) -> Optional[str]:
        """
        ZtpQueue 항목을 기반으로 Day-0 Configuration 생성.
        Priority:
        1. [NEW] Backup Config (If matched to existing device)
        2. Template + Variables
        """
        support = DeviceSupportPolicyService.evaluate_metadata(
            self.db,
            site_id=getattr(queue_item, "assigned_site_id", None),
            device_type=str(getattr(queue_item, "device_type", "") or "unknown"),
            os_version=str(getattr(queue_item, "software_version", "") or ""),
            model=str(getattr(queue_item, "platform", "") or ""),
            hostname=str(getattr(queue_item, "target_hostname", "") or getattr(queue_item, "hostname", "") or ""),
        )
        if not bool((support.get("features") or {}).get("ztp", False)):
            queue_item.status = ZtpStatus.NEW.value
            queue_item.last_message = (
                f"ZTP blocked by vendor support policy (tier={support.get('tier')}, "
                f"fallback={support.get('fallback_mode')})."
            )
            self.db.commit()
            return None

        # [NEW] 1. Backup Config Check
        if queue_item.suggested_device_id:
            from app.models.device import ConfigBackup
            latest_backup = self.db.query(ConfigBackup)\
                .filter(ConfigBackup.device_id == queue_item.suggested_device_id)\
                .order_by(ConfigBackup.created_at.desc())\
                .first()
            
            if latest_backup and latest_backup.raw_config:
                return latest_backup.raw_config

        # 2. Template Logic
        if not queue_item.assigned_template_id:
            return None

        template = self.db.query(ConfigTemplate).filter(
            ConfigTemplate.id == queue_item.assigned_template_id
        ).first()
        
        if not template:
            return None

        # 변수 컨텍스트 구성
        site_vars = {}
        if queue_item.assigned_site_id:
            site = self.db.query(Site).filter(Site.id == queue_item.assigned_site_id).first()
            site_vars = site.variables or {} if site else {}

        device_vars = {
            "hostname": queue_item.target_hostname or f"Switch-{queue_item.serial_number[-4:]}",
            "serial_number": queue_item.serial_number,
            "platform": queue_item.platform or "Unknown"
        }

        context = TemplateRenderer.merge_variables({}, site_vars, device_vars)
        return TemplateRenderer.render(template.content, context)

    # ================================================================
    # 4. 자동 온보딩
    # ================================================================
    def complete_provisioning(self, queue_item: ZtpQueue) -> Device:
        """
        ZTP 완료 후 장비를 메인 Device 테이블로 이동.
        """
        try:
            LicensePolicyService.assert_can_add_devices(
                self.db,
                source="ztp_complete_provisioning",
            )
        except LicensePolicyViolation as exc:
            queue_item.status = ZtpStatus.ERROR.value
            queue_item.last_message = f"License policy blocked: {exc}"
            self.db.commit()
            raise

        # 벤더/장비 타입 결정 (없으면 Fallback)
        final_device_type = queue_item.device_type
        if not final_device_type:
            # Platform 문자열로 추론
            platform = (queue_item.platform or "").lower()
            if "juniper" in platform or "ex" in platform or "srx" in platform or "qfx" in platform:
                final_device_type = "juniper_junos"
            elif "arista" in platform or "dcs" in platform:
                final_device_type = "arista_eos"
            else:
                final_device_type = "cisco_ios"  # Default fallback

        support = DeviceSupportPolicyService.evaluate_metadata(
            self.db,
            site_id=getattr(queue_item, "assigned_site_id", None),
            device_type=str(final_device_type or "unknown"),
            os_version=str(getattr(queue_item, "software_version", "") or ""),
            model=str(getattr(queue_item, "platform", "") or ""),
            hostname=str(getattr(queue_item, "target_hostname", "") or getattr(queue_item, "hostname", "") or ""),
        )
        if not bool((support.get("features") or {}).get("ztp", False)):
            queue_item.status = ZtpStatus.ERROR.value
            queue_item.last_message = (
                f"ZTP blocked by vendor support policy (tier={support.get('tier')}, "
                f"fallback={support.get('fallback_mode')})."
            )
            self.db.commit()
            raise RuntimeError("ZTP blocked by vendor support policy")

        # Device 생성
        new_device = Device(
            name=queue_item.target_hostname or f"Device-{queue_item.serial_number[-4:]}",
            hostname=queue_item.target_hostname,
            ip_address=queue_item.ip_address or "0.0.0.0",
            serial_number=queue_item.serial_number,
            model=queue_item.platform,
            os_version=queue_item.software_version,
            device_type=final_device_type,  # [UPDATED] Use dynamic device type
            site_id=queue_item.assigned_site_id,
            status="online",
            variables={
                "support_policy": {
                    "tier": support.get("tier"),
                    "fallback_mode": support.get("fallback_mode"),
                    "features": support.get("features"),
                    "reasons": support.get("reasons"),
                }
            },
        )
        self.db.add(new_device)

        # Queue 상태 업데이트
        queue_item.status = ZtpStatus.COMPLETED.value
        queue_item.provisioned_at = datetime.now()
        queue_item.last_message = f"Successfully onboarded as {final_device_type}"

        self.db.commit()
        self.db.refresh(new_device)
        return new_device


    # ================================================================
    # 5. PnP Response 생성
    # ================================================================
    def generate_pnp_response(self, queue_item: ZtpQueue) -> str:
        """
        Cisco PnP Agent에게 보낼 XML Response 생성.
        - status == 'ready': Config Upgrade Work Item 전송
        - status == 'new': Backoff (재시도 대기)
        """
        if queue_item.status == ZtpStatus.READY.value:
            config = self.generate_day0_config(queue_item)
            if config:
                queue_item.status = ZtpStatus.PROVISIONING.value
                self.db.commit()
                return self._build_config_upgrade_response(config)
        
        # Backoff Response (30초 후 재시도)
        return self._build_backoff_response(30)

    def _build_config_upgrade_response(self, config: str) -> str:
        """CLI 설정 전송용 XML Response"""
        # CDATA로 Config 전달
        return f'''<?xml version="1.0" encoding="UTF-8"?>
<pnp xmlns="urn:cisco:pnp:work-response" version="1.0">
  <response correlator="CiscoPnP-1.0">
    <workInfo workItemId="1">
      <workType>CLI Configuration</workType>
      <data><![CDATA[
{config}
end
]]></data>
    </workInfo>
  </response>
</pnp>'''

    def _build_backoff_response(self, seconds: int) -> str:
        """재시도 요청 XML Response"""
        return f'''<?xml version="1.0" encoding="UTF-8"?>
<pnp xmlns="urn:cisco:pnp:work-response" version="1.0">
  <response correlator="CiscoPnP-1.0">
    <backoff seconds="{seconds}"/>
  </response>
</pnp>'''
