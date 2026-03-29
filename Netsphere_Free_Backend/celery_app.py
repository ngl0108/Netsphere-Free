import logging
import os

from celery import Celery
from celery.schedules import crontab
from celery.signals import before_task_publish, task_postrun, task_prerun

from app.core.logging_config import configure_logging
from app.core.request_context import (
    clear_request_context,
    get_method,
    get_path,
    get_request_id,
    set_request_context,
)

configure_logging()
logger = logging.getLogger(__name__)

broker_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
backend_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "netmanager",
    broker=broker_url,
    backend=backend_url,
    include=[
        "app.tasks.monitoring",
        "app.tasks.config",
        "app.tasks.maintenance",
        "app.tasks.discovery",
        "app.tasks.neighbor_crawl",
        "app.tasks.topology_refresh",
        "app.tasks.device_sync",
        "app.tasks.syslog_ingest",
        "app.tasks.compliance",
        "app.tasks.smart_alerting",
        "app.tasks.closed_loop",
        "app.tasks.ops_kpi",
        "app.tasks.cloud_sync",
    ],
)

celery_app.set_default()

try:
    from kombu import Exchange, Queue
except ModuleNotFoundError:
    Exchange = None
    Queue = None

discovery_rate_limit = os.getenv("DISCOVERY_TASK_RATE_LIMIT", "30/m")
neighbor_rate_limit = os.getenv("NEIGHBOR_CRAWL_RATE_LIMIT", "30/m")
ssh_sync_rate_limit = os.getenv("SSH_SYNC_TASK_RATE_LIMIT", "120/m")
syslog_rate_limit = os.getenv("SYSLOG_TASK_RATE_LIMIT", "300/m")
monitor_all_devices_interval_sec = float(os.getenv("MONITOR_ALL_DEVICES_INTERVAL_SEC", "30"))
gnmi_collect_interval_sec = float(os.getenv("GNMI_COLLECT_INTERVAL_SEC", "5"))
cloud_auto_sync_beat_interval_sec = float(os.getenv("CLOUD_AUTO_SYNC_BEAT_INTERVAL_SEC", "30"))
closed_loop_interval_sec = float(os.getenv("CLOSED_LOOP_EVAL_INTERVAL_SEC", "30"))

celery_conf = dict(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Seoul",
    enable_utc=False,
    broker_connection_retry_on_startup=True,
    worker_max_tasks_per_child=int(os.getenv("CELERY_MAX_TASKS_PER_CHILD", "200")),
    worker_send_task_events=True,
    task_send_sent_event=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    broker_transport_options={
        "visibility_timeout": int(os.getenv("CELERY_VISIBILITY_TIMEOUT", "3600")),
    },
    task_default_queue="default",
    task_routes={
        "app.tasks.discovery.run_discovery_job": {"queue": "discovery", "routing_key": "discovery"},
        "app.tasks.neighbor_crawl.run_neighbor_crawl_job": {"queue": "discovery", "routing_key": "discovery"},
        "app.tasks.device_sync.ssh_sync_device": {"queue": "ssh", "routing_key": "ssh"},
        "app.tasks.device_sync.enqueue_ssh_sync_batch": {"queue": "ssh", "routing_key": "ssh"},
        "app.tasks.monitoring.monitor_all_devices": {"queue": "monitoring", "routing_key": "monitoring"},
        "app.tasks.monitoring.collect_gnmi_metrics": {"queue": "monitoring", "routing_key": "monitoring"},
        "app.tasks.smart_alerting.run_dynamic_thresholds": {"queue": "monitoring", "routing_key": "monitoring"},
        "app.tasks.smart_alerting.run_correlations": {"queue": "monitoring", "routing_key": "monitoring"},
        "app.tasks.closed_loop.run_closed_loop_cycle": {"queue": "monitoring", "routing_key": "monitoring"},
        "app.tasks.monitoring.full_ssh_sync_all": {"queue": "monitoring", "routing_key": "monitoring"},
        "app.tasks.maintenance.run_log_retention": {"queue": "maintenance", "routing_key": "maintenance"},
        "app.tasks.compliance.run_scheduled_compliance_scan": {"queue": "maintenance", "routing_key": "maintenance"},
        "app.tasks.compliance.run_scheduled_config_drift_checks": {"queue": "maintenance", "routing_key": "maintenance"},
        "app.tasks.syslog_ingest.ingest_syslog": {"queue": "syslog", "routing_key": "syslog"},
        "app.tasks.ops_kpi.run_daily_kpi_readiness_snapshot": {"queue": "maintenance", "routing_key": "maintenance"},
        "app.tasks.ops_kpi.run_scheduled_release_evidence_refresh": {"queue": "maintenance", "routing_key": "maintenance"},
        "app.tasks.cloud_sync.run_cloud_auto_sync": {"queue": "maintenance", "routing_key": "maintenance"},
    },
    task_annotations={
        "app.tasks.discovery.run_discovery_job": {"rate_limit": discovery_rate_limit},
        "app.tasks.neighbor_crawl.run_neighbor_crawl_job": {"rate_limit": neighbor_rate_limit},
        "app.tasks.device_sync.ssh_sync_device": {"rate_limit": ssh_sync_rate_limit},
        "app.tasks.syslog_ingest.ingest_syslog": {"rate_limit": syslog_rate_limit},
    },
    beat_schedule={
        "monitor-all-devices-interval": {
            "task": "app.tasks.monitoring.monitor_all_devices",
            "schedule": monitor_all_devices_interval_sec,
        },
        "collect-gnmi-metrics-interval": {
            "task": "app.tasks.monitoring.collect_gnmi_metrics",
            "schedule": gnmi_collect_interval_sec,
        },
        "smart-alert-dynamic-thresholds-every-30s": {
            "task": "app.tasks.smart_alerting.run_dynamic_thresholds",
            "schedule": float(os.getenv("SMART_ALERT_DYNAMIC_INTERVAL_SEC", "30")),
        },
        "smart-alert-correlations-every-30s": {
            "task": "app.tasks.smart_alerting.run_correlations",
            "schedule": float(os.getenv("SMART_ALERT_CORRELATION_INTERVAL_SEC", "30")),
        },
        "closed-loop-eval-cycle": {
            "task": "app.tasks.closed_loop.run_closed_loop_cycle",
            "schedule": closed_loop_interval_sec,
        },
        "full-ssh-sync-every-hour": {
            "task": "app.tasks.monitoring.full_ssh_sync_all",
            "schedule": 3600.0,
        },
        "run-log-retention-daily": {
            "task": "app.tasks.maintenance.run_log_retention",
            "schedule": crontab(hour=3, minute=0),
        },
        "run-config-drift-daily": {
            "task": "app.tasks.compliance.run_scheduled_config_drift_checks",
            "schedule": crontab(hour=3, minute=10),
        },
        "run-compliance-scan-daily": {
            "task": "app.tasks.compliance.run_scheduled_compliance_scan",
            "schedule": crontab(hour=3, minute=30),
        },
        "ops-kpi-readiness-snapshot-daily": {
            "task": "app.tasks.ops_kpi.run_daily_kpi_readiness_snapshot",
            "schedule": crontab(hour=4, minute=15),
        },
        "release-evidence-refresh-daily": {
            "task": "app.tasks.ops_kpi.run_scheduled_release_evidence_refresh",
            "schedule": crontab(hour=4, minute=30),
        },
        "cloud-auto-sync-interval": {
            "task": "app.tasks.cloud_sync.run_cloud_auto_sync",
            "schedule": cloud_auto_sync_beat_interval_sec,
        },
    },
)

if Exchange and Queue:
    exchange = Exchange("netmanager", type="direct")
    celery_conf.update(
        task_default_exchange="netmanager",
        task_default_exchange_type="direct",
        task_default_routing_key="default",
        task_queues=(
            Queue("default", exchange, routing_key="default"),
            Queue("discovery", exchange, routing_key="discovery"),
            Queue("ssh", exchange, routing_key="ssh"),
            Queue("monitoring", exchange, routing_key="monitoring"),
            Queue("maintenance", exchange, routing_key="maintenance"),
            Queue("syslog", exchange, routing_key="syslog"),
        ),
    )

celery_app.conf.update(**celery_conf)
REQUEST_ID_HEADER = "x-request-id"
REQUEST_PATH_HEADER = "x-request-path"
REQUEST_METHOD_HEADER = "x-request-method"


@before_task_publish.connect
def _inject_correlation_headers(headers=None, **kwargs):
    try:
        if not isinstance(headers, dict):
            return
        request_id = str(get_request_id() or "").strip()
        if not request_id:
            return
        headers.setdefault(REQUEST_ID_HEADER, request_id)

        path = str(get_path() or "").strip()
        method = str(get_method() or "").strip()
        if path:
            headers.setdefault(REQUEST_PATH_HEADER, path)
        if method:
            headers.setdefault(REQUEST_METHOD_HEADER, method)
    except Exception:
        logger.exception("failed to inject celery correlation headers")


@task_prerun.connect
def _set_worker_request_context(task_id=None, task=None, **kwargs):
    try:
        request = getattr(task, "request", None)
        headers = getattr(request, "headers", None) if request is not None else None
        if not isinstance(headers, dict):
            headers = {}

        task_name = str(getattr(task, "name", "") or "")
        fallback_path = f"celery:{task_name or 'task'}"
        rid = (
            str(headers.get(REQUEST_ID_HEADER) or "").strip()
            or str(getattr(request, "correlation_id", "") or "").strip()
            or str(task_id or "").strip()
            or "celery-task"
        )
        path = str(headers.get(REQUEST_PATH_HEADER) or "").strip() or fallback_path
        method = str(headers.get(REQUEST_METHOD_HEADER) or "").strip() or "TASK"
        set_request_context(rid, path, method)
    except Exception:
        logger.exception("failed to set worker request context")


@task_postrun.connect
def _clear_worker_request_context(**kwargs):
    try:
        clear_request_context()
    except Exception:
        logger.exception("failed to clear worker request context")


if __name__ == "__main__":
    celery_app.start()
