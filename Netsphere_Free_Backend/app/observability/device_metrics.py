import time

from prometheus_client import REGISTRY
from prometheus_client.core import GaugeMetricFamily
from sqlalchemy import func

from app.db.session import SessionLocal
from app.models.device import Device, SystemMetric


class DeviceMetricsCollector:
    def __init__(self, cache_ttl_seconds: int = 10):
        self.cache_ttl_seconds = max(int(cache_ttl_seconds), 1)
        self._cache_expires_at = 0.0
        self._cached_families = None

    def collect(self):
        now = time.time()
        if self._cached_families is None or now >= self._cache_expires_at:
            try:
                self._cached_families = self._build_families()
                self._cache_expires_at = now + self.cache_ttl_seconds
            except Exception:
                if self._cached_families is None:
                    self._cached_families = []
                self._cache_expires_at = now + min(self.cache_ttl_seconds, 10)
        for fam in self._cached_families:
            yield fam

    def _build_families(self):
        db = SessionLocal()
        try:
            devices = db.query(Device).all()

            latest_ts = (
                db.query(SystemMetric.device_id, func.max(SystemMetric.timestamp).label("ts"))
                .group_by(SystemMetric.device_id)
                .subquery()
            )
            latest_metrics = (
                db.query(SystemMetric)
                .join(
                    latest_ts,
                    (SystemMetric.device_id == latest_ts.c.device_id)
                    & (SystemMetric.timestamp == latest_ts.c.ts),
                )
                .all()
            )
            metrics_by_device_id = {m.device_id: m for m in latest_metrics}

            total_devices = GaugeMetricFamily(
                "netsphere_devices_total",
                "Total number of devices registered in NetSphere.",
            )
            total_devices.add_metric([], float(len(devices)))

            online_devices = GaugeMetricFamily(
                "netsphere_devices_online_total",
                "Total number of devices currently online (based on last monitoring run).",
            )
            online_devices.add_metric([], float(sum(1 for d in devices if (d.status or "").lower() == "online")))

            labels = ["device_id", "name", "ip", "site_id", "device_type"]

            device_up = GaugeMetricFamily(
                "netsphere_device_up",
                "Device reachability (1=up, 0=down) as determined by monitoring.",
                labels=labels,
            )
            device_last_seen_ts = GaugeMetricFamily(
                "netsphere_device_last_seen_timestamp_seconds",
                "Device last_seen as a unix timestamp in seconds.",
                labels=labels,
            )
            device_cpu = GaugeMetricFamily(
                "netsphere_device_cpu_percent",
                "Latest observed device CPU utilization in percent.",
                labels=labels,
            )
            device_mem = GaugeMetricFamily(
                "netsphere_device_memory_percent",
                "Latest observed device memory utilization in percent.",
                labels=labels,
            )
            device_traffic_in = GaugeMetricFamily(
                "netsphere_device_traffic_in_bps",
                "Latest observed device inbound traffic in bits per second.",
                labels=labels,
            )
            device_traffic_out = GaugeMetricFamily(
                "netsphere_device_traffic_out_bps",
                "Latest observed device outbound traffic in bits per second.",
                labels=labels,
            )

            for d in devices:
                label_values = [
                    str(d.id),
                    str(d.name or ""),
                    str(d.ip_address or ""),
                    str(d.site_id or 0),
                    str(d.device_type or ""),
                ]
                is_up = 1.0 if (d.status or "").lower() == "online" else 0.0
                device_up.add_metric(label_values, is_up)

                if d.last_seen is not None:
                    device_last_seen_ts.add_metric(label_values, float(d.last_seen.timestamp()))

                m = metrics_by_device_id.get(d.id)
                if m is not None:
                    device_cpu.add_metric(label_values, float(m.cpu_usage or 0.0))
                    device_mem.add_metric(label_values, float(m.memory_usage or 0.0))
                    device_traffic_in.add_metric(label_values, float(m.traffic_in or 0.0))
                    device_traffic_out.add_metric(label_values, float(m.traffic_out or 0.0))

            return [
                total_devices,
                online_devices,
                device_up,
                device_last_seen_ts,
                device_cpu,
                device_mem,
                device_traffic_in,
                device_traffic_out,
            ]
        finally:
            db.close()


def register_device_metrics(cache_ttl_seconds: int = 10) -> None:
    collector = DeviceMetricsCollector(cache_ttl_seconds=cache_ttl_seconds)
    try:
        REGISTRY.register(collector)
    except ValueError:
        return
