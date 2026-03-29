import logging
from sqlalchemy.orm import Session
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.db.session import SessionLocal
from app.models.device import Device, ConfigBackup
from app.services.ssh_service import DeviceConnection, DeviceInfo

logger = logging.getLogger("scheduler")


def backup_single_device(device_id: int):
    """
    [Worker] 개별 장비 1대를 백업하는 작업 함수
    (각 스레드에서 독립적으로 실행됨)
    """
    # 스레드마다 별도의 DB 세션을 생성해야 안전합니다.
    db: Session = SessionLocal()
    result = {"id": device_id, "status": "failed", "msg": ""}

    try:
        device = db.query(Device).filter(Device.id == device_id).first()
        if not device:
            result["msg"] = "Device not found"
            return result

        # 연결 정보 세팅
        info = DeviceInfo(
            host=device.ip_address,
            username=device.ssh_username,
            password=device.ssh_password,
            secret=device.enable_password,
            device_type=device.device_type,
            port=device.ssh_port
        )

        # 이름 미리 저장 (로깅용)
        result["name"] = device.name
        result["ip"] = device.ip_address

        # SSH 연결 시도
        conn = DeviceConnection(info)
        if conn.connect():
            # Config 가져오기
            config_txt = conn.get_running_config()

            # DB에 백업 저장
            backup = ConfigBackup(
                device_id=device.id,
                raw_config=config_txt,
                created_at=datetime.now()
            )
            db.add(backup)
            db.commit()

            conn.disconnect()
            result["status"] = "success"
        else:
            result["msg"] = f"Connection failed: {conn.last_error}"

    except Exception as e:
        result["msg"] = str(e)
    finally:
        db.close()  # 세션 정리

    return result


def run_auto_backup():
    """
    [Manager] 스레드 풀을 사용하여 병렬로 백업을 수행합니다.
    """
    logger.info("🚀 [Parallel Backup] Starting backup task...")

    # 메인 세션에서 장비 ID 목록만 가져옴 (가볍게)
    db = SessionLocal()
    device_ids = [d.id for d in db.query(Device).all()]
    db.close()

    if not device_ids:
        logger.info("⚠️ No devices to backup.")
        return

    # 최대 10개 장비를 동시에 처리 (서버 사양에 따라 조절 가능)
    MAX_WORKERS = 10

    success_cnt = 0
    fail_cnt = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # 작업을 스레드 풀에 등록
        future_to_id = {executor.submit(backup_single_device, d_id): d_id for d_id in device_ids}

        # 완료되는 순서대로 결과 처리
        for future in as_completed(future_to_id):
            res = future.result()
            if res["status"] == "success":
                logger.info(f"✅ Backup OK: {res.get('name')} ({res.get('ip')})")
                success_cnt += 1
            else:
                logger.warning(f"❌ Backup Fail: ID {res['id']} - {res['msg']}")
                fail_cnt += 1

    logger.info(f"🏁 [Parallel Backup] Completed. Success: {success_cnt}, Failed: {fail_cnt}")