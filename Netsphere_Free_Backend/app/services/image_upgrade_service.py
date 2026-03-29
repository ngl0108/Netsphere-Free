import os
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.image_job import UpgradeJob, JobStatus
from app.models.device import Device, FirmwareImage
from app.drivers.manager import DriverManager

class ImageUpgradeService:
    def __init__(self, db: Session):
        self.db = db

    def create_jobs(self, image_id: int, device_ids: list[int]) -> list[UpgradeJob]:
        """Create upgrade jobs for multiple devices."""
        jobs = []
        for dev_id in device_ids:
            job = UpgradeJob(
                device_id=dev_id,
                image_id=image_id,
                status=JobStatus.PENDING.value,
                progress_percent=0,
                current_stage="queued"
            )
            self.db.add(job)
            jobs.append(job)
        self.db.commit()
        return jobs

    def process_job(self, job_id: int):
        """
        Execute the upgrade workflow for a single job.
        This is intended to be run in a background task.
        """
        # Re-query job to attach to current session if needed, 
        # but here self.db should be a fresh session provided by the caller/worker.
        job = self.db.query(UpgradeJob).filter(UpgradeJob.id == job_id).first()
        if not job:
            return

        device = job.device
        image = job.image
        
        # Paths
        # Assuming images are stored in "firmware_storage" as per images.py
        local_path = os.path.abspath(os.path.join("firmware_storage", image.filename))
        
        if not os.path.exists(local_path):
            self._fail_job(job, f"Image file not found on server: {local_path}")
            return

        driver = None
        try:
            # 1. Start
            self._update_status(job, JobStatus.RUNNING, 10, "connecting")
            driver = DriverManager.get_driver(
                device.device_type, device.ip_address, 
                device.ssh_username, device.ssh_password, 
                device.ssh_port, device.enable_password
            )
            
            if not driver.connect():
                self._fail_job(job, f"Could not connect to device {device.name}: {getattr(driver, 'last_error', '')}".strip())
                return

            dest_filename, verify_ref, file_system = self._compute_remote_refs(driver, local_path)

            # 2. Transfer
            self._update_status(job, JobStatus.RUNNING, 30, "transferring_file")
            success = driver.transfer_file(local_path, remote_path=dest_filename, file_system=file_system)
            if not success:
                self._fail_job(job, f"File transfer failed: {getattr(driver, 'last_error', '')}".strip())
                return

            # 3. Verify
            self._update_status(job, JobStatus.RUNNING, 60, "verifying_checksum")
            if image.md5_checksum:
                valid = driver.verify_image(verify_ref, image.md5_checksum)
                if not valid:
                    self._fail_job(job, f"Checksum verification failed on device: {getattr(driver, 'last_error', '')}".strip())
                    return

            # 4. Set Boot
            self._update_status(job, JobStatus.RUNNING, 80, "setting_boot_variable")
            if not driver.set_boot_variable(verify_ref):
                self._fail_job(job, f"Failed to set boot variable: {getattr(driver, 'last_error', '')}".strip())
                return

            # 5. Reload
            self._update_status(job, JobStatus.RUNNING, 90, "rebooting")
            driver.reload(save_config=True) # Connection will drop here
            
            # 6. Complete (technically we wait for it to come back, but for now we mark as 'rebooting' -> 'completed')
            # In a real system, we'd poll until it's back online. 
            # Here we just mark 'Waiting for Reboot' and complete.
            self._update_status(job, JobStatus.COMPLETED, 100, "reboot_initiated", "Device is rebooting with new image.")
            
        except Exception as e:
            self._fail_job(job, str(e))
        finally:
            if driver:
                try:
                    driver.disconnect()
                except Exception:
                    pass

    def _compute_remote_refs(self, driver, local_path: str) -> tuple[str, str, str | None]:
        filename = os.path.basename(local_path)
        dtype = (getattr(driver, "DEVICE_TYPE", None) or "").strip().lower()
        if dtype in {"juniper_junos", "juniper"}:
            return filename, f"/var/tmp/{filename}", None
        return filename, f"flash:{filename}", "flash:"

    def _update_status(self, job, status, progress, stage, msg=None):
        job.status = status.value
        job.progress_percent = progress
        job.current_stage = stage
        if msg:
            if job.logs: job.logs += f"\n{msg}"
            else: job.logs = msg
        job.started_at = datetime.now() if status == JobStatus.RUNNING and not job.started_at else job.started_at
        job.completed_at = datetime.now() if status in [JobStatus.COMPLETED, JobStatus.FAILED] else None
        self.db.commit()

    def _fail_job(self, job, error_msg):
        job.status = JobStatus.FAILED.value
        job.error_message = error_msg
        job.logs = (job.logs or "") + f"\nERROR: {error_msg}"
        job.completed_at = datetime.now()
        self.db.commit()
