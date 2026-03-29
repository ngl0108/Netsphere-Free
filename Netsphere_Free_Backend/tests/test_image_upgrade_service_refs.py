import hashlib
import os

from app.models.device import Device, FirmwareImage
from app.models.image_job import UpgradeJob, JobStatus
from app.services.image_upgrade_service import ImageUpgradeService


class _FakeDriver:
    DEVICE_TYPE = "cisco_ios"

    def __init__(self):
        self.last_error = ""
        self.calls = []

    def connect(self):
        self.calls.append(("connect",))
        return True

    def transfer_file(self, local_path, remote_path=None, file_system=None):
        self.calls.append(("transfer_file", os.path.basename(local_path), remote_path, file_system))
        return True

    def verify_image(self, file_path, expected_checksum):
        self.calls.append(("verify_image", file_path, expected_checksum))
        return True

    def set_boot_variable(self, file_path):
        self.calls.append(("set_boot_variable", file_path))
        return True

    def reload(self, save_config=True):
        self.calls.append(("reload", save_config))

    def disconnect(self):
        self.calls.append(("disconnect",))


def _write_firmware(filename: str, content: bytes) -> str:
    os.makedirs("firmware_storage", exist_ok=True)
    path = os.path.join("firmware_storage", filename)
    with open(path, "wb") as f:
        f.write(content)
    return path


def _md5(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(4096), b""):
            h.update(b)
    return h.hexdigest()


def test_upgrade_job_uses_flash_refs_for_ios(db, monkeypatch):
    fw_path = _write_firmware("ios.bin", b"abc")
    image = FirmwareImage(version="1", filename="ios.bin", device_family="cisco", md5_checksum=_md5(fw_path))
    device = Device(name="sw1", ip_address="10.0.0.1", device_type="cisco_ios", ssh_username="u", ssh_password="p", ssh_port=22)
    db.add_all([image, device])
    db.commit()

    job = UpgradeJob(device_id=device.id, image_id=image.id, status=JobStatus.PENDING.value, progress_percent=0, current_stage="queued")
    db.add(job)
    db.commit()
    db.refresh(job)

    driver = _FakeDriver()

    from app.services import image_upgrade_service as mod

    monkeypatch.setattr(mod.DriverManager, "get_driver", lambda *args, **kwargs: driver)

    ImageUpgradeService(db).process_job(job.id)
    db.refresh(job)

    assert job.status == JobStatus.COMPLETED.value
    assert ("transfer_file", "ios.bin", "ios.bin", "flash:") in driver.calls
    assert ("verify_image", "flash:ios.bin", image.md5_checksum) in driver.calls
    assert ("set_boot_variable", "flash:ios.bin") in driver.calls


def test_upgrade_job_uses_var_tmp_refs_for_junos(db, monkeypatch):
    fw_path = _write_firmware("junos.tgz", b"xyz")
    image = FirmwareImage(version="1", filename="junos.tgz", device_family="juniper", md5_checksum=_md5(fw_path))
    device = Device(name="mx1", ip_address="10.0.0.2", device_type="juniper_junos", ssh_username="u", ssh_password="p", ssh_port=22)
    db.add_all([image, device])
    db.commit()

    job = UpgradeJob(device_id=device.id, image_id=image.id, status=JobStatus.PENDING.value, progress_percent=0, current_stage="queued")
    db.add(job)
    db.commit()
    db.refresh(job)

    driver = _FakeDriver()
    driver.DEVICE_TYPE = "juniper_junos"

    from app.services import image_upgrade_service as mod

    monkeypatch.setattr(mod.DriverManager, "get_driver", lambda *args, **kwargs: driver)

    ImageUpgradeService(db).process_job(job.id)
    db.refresh(job)

    assert job.status == JobStatus.COMPLETED.value
    assert ("transfer_file", "junos.tgz", "junos.tgz", None) in driver.calls
    assert ("verify_image", "/var/tmp/junos.tgz", image.md5_checksum) in driver.calls
    assert ("set_boot_variable", "/var/tmp/junos.tgz") in driver.calls

