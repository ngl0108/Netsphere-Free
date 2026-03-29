try:
    from celery import shared_task
except ModuleNotFoundError:
    def shared_task(*args, **kwargs):
        def decorator(fn):
            return fn
        if args and callable(args[0]) and not kwargs:
            return args[0]
        return decorator
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
# [핵심 수정] 예전 경로(app.models.config_template) 대신 통합된 모델(app.models.device) 사용
from app.models.device import Device, ConfigTemplate, ConfigBackup
import logging

logger = logging.getLogger(__name__)


@shared_task
def pull_and_parse_config(device_id: int):
    """
    비동기 작업: 장비 설정을 가져와서 DB에 저장 (시뮬레이션)
    """
    db = SessionLocal()
    try:
        device = db.query(Device).filter(Device.id == device_id).first()
        if not device:
            return f"Device {device_id} not found"

        # [임시] SSH 연동 전이므로 더미 데이터 생성
        logger.info("Connecting via SSH (simulated)", extra={"device_id": device.id})
        logger.info("Pulling running-config (simulated)", extra={"device_id": device.id})

        dummy_config = f"""!
version 17.06
hostname {device.name}
!
interface GigabitEthernet1/0/1
 description Management Interface
 ip address dhcp
!
line vty 0 4
 transport input ssh
!
end
"""
        backup = ConfigBackup(
            device_id=device.id,
            raw_config=dummy_config
        )
        db.add(backup)
        db.commit()
        return f"Config pulled successfully for {device.name}"
    finally:
        db.close()


@shared_task
def deploy_config_task(device_id: int, template_id: int):
    """
    비동기 작업: 템플릿을 장비에 배포 (시뮬레이션)
    """
    db = SessionLocal()
    try:
        device = db.query(Device).filter(Device.id == device_id).first()
        template = db.query(ConfigTemplate).filter(ConfigTemplate.id == template_id).first()

        if not device or not template:
            return "Device or Template not found"

        # [임시] 배포 로직 시뮬레이션
        logger.info("Deploying template (simulated)", extra={"device_id": device.id})
        # 실제로는 여기서 Netmiko/Napalm 등을 사용해 설정 밀어넣기 수행

        return f"Deployed template '{template.name}' to {device.name}"
    finally:
        db.close()


@shared_task(name="app.tasks.config.deploy_vlan_bulk_task")
def deploy_vlan_bulk_task(device_ids: list[int], vlan_id: int, vlan_name: str):
    from app.services.ssh_service import DeviceConnection, DeviceInfo

    vlan_template = "vlan {{ vlan_id }}\n name {{ vlan_name }}\nexit"
    db = SessionLocal()
    try:
        devices = db.query(Device).filter(Device.id.in_(device_ids)).all()
        device_by_id = {d.id: d for d in devices}
        summary = []
        for d_id in device_ids:
            dev = device_by_id.get(d_id)
            if not dev:
                summary.append({"id": d_id, "name": None, "status": "not_found"})
                continue
            try:
                conn = DeviceConnection(
                    DeviceInfo(
                        host=dev.ip_address,
                        username=dev.ssh_username,
                        password=dev.ssh_password,
                        secret=dev.enable_password,
                        port=getattr(dev, "ssh_port", 22) or 22,
                        device_type=dev.device_type or "cisco_ios",
                    )
                )
                if conn.connect():
                    res = conn.deploy_config_template(vlan_template, {"vlan_id": vlan_id, "vlan_name": vlan_name})
                    summary.append(
                        {"id": d_id, "name": dev.name, "status": "success" if res.get("success") else "failed"}
                    )
                    conn.disconnect()
                else:
                    summary.append({"id": d_id, "name": dev.name, "status": "failed"})
            except Exception:
                logger.exception("VLAN deploy failed", extra={"device_id": getattr(dev, "id", None)})
                summary.append({"id": d_id, "name": getattr(dev, "name", None), "status": "failed"})
        return {"summary": summary}
    finally:
        db.close()
