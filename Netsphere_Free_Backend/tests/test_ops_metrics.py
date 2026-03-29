import sys
import types

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.approval import ApprovalRequest
from app.models.automation import AutomationRule
from app.models.device import ComplianceReport, Device, Issue, Link
from app.models.discovery import DiscoveredDevice, DiscoveryJob
from app.models.settings import SystemSetting
from app.models.topology_candidate import TopologyNeighborCandidate
from app.models.user import User

try:
    import prometheus_client  # noqa: F401
except Exception:
    class _Sample:
        def __init__(self, labels, value):
            self.labels = labels
            self.value = value

    class _GaugeMetricFamily:
        def __init__(self, name, documentation, labels=None):
            self.name = name
            self.documentation = documentation
            self.label_names = labels or []
            self.samples = []

        def add_metric(self, label_values, value):
            labels = {key: label_values[idx] for idx, key in enumerate(self.label_names)}
            self.samples.append(_Sample(labels, value))

    fake_prom = types.ModuleType("prometheus_client")
    fake_prom.REGISTRY = types.SimpleNamespace(register=lambda collector: None)
    fake_core = types.ModuleType("prometheus_client.core")
    fake_core.GaugeMetricFamily = _GaugeMetricFamily
    sys.modules["prometheus_client"] = fake_prom
    sys.modules["prometheus_client.core"] = fake_core

from app.observability import ops_metrics as metrics_module


def _metric_value(metric_family, labels=None):
    labels = labels or {}
    for sample in getattr(metric_family, "samples", []):
        if sample.labels == labels:
            return sample.value
    return None


def test_ops_metrics_collector_exposes_operational_counts(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        user = User(username="operator", hashed_password="hash", role="admin", is_active=True)
        db.add(user)
        db.flush()

        device = Device(
            name="edge-a",
            ip_address="10.0.0.1",
            device_type="cisco_ios",
            status="online",
            owner_id=user.id,
        )
        db.add(device)
        db.flush()

        discovery_job = DiscoveryJob(cidr="10.0.0.0/24", status="completed")
        db.add(discovery_job)
        db.flush()

        db.add_all(
            [
                DiscoveredDevice(job_id=discovery_job.id, ip_address="10.0.0.2", status="approved", device_type="switch"),
                TopologyNeighborCandidate(source_device_id=device.id, neighbor_name="dist-1", status="unmatched"),
                ApprovalRequest(requester_id=user.id, title="Push config", status="pending"),
                AutomationRule(
                    name="cpu-warn",
                    trigger_type="cpu",
                    trigger_value="80",
                    action_type="workflow",
                    enabled=True,
                ),
                ComplianceReport(device_id=device.id, status="violation", match_percentage=72.0),
                Issue(device_id=device.id, title="CPU high", severity="warning", status="active"),
                Link(source_device_id=device.id, target_device_id=device.id),
                SystemSetting(key="closed_loop_engine_enabled", value="true", description="x", category="ops"),
                SystemSetting(key="webhook_enabled", value="true", description="x", category="ops"),
                SystemSetting(key="webhook_retry_attempts", value="3", description="x", category="ops"),
            ]
        )
        db.commit()

        monkeypatch.setattr(metrics_module, "SessionLocal", SessionLocal)
        collector = metrics_module.OpsMetricsCollector(cache_ttl_seconds=1)
        families = collector._build_families()
        family_by_name = {family.name: family for family in families}

        assert _metric_value(family_by_name["netsphere_discovery_jobs_total"], {"status": "completed"}) == 1.0
        assert _metric_value(family_by_name["netsphere_discovered_devices_total"], {"status": "approved"}) == 1.0
        assert _metric_value(family_by_name["netsphere_topology_candidates_total"], {"status": "unmatched"}) == 1.0
        assert _metric_value(family_by_name["netsphere_approval_requests_total"], {"status": "pending"}) == 1.0
        assert _metric_value(family_by_name["netsphere_automation_rules_total"], {"enabled": "true"}) == 1.0
        assert _metric_value(family_by_name["netsphere_compliance_reports_total"], {"status": "violation"}) == 1.0
        assert _metric_value(
            family_by_name["netsphere_controller_component_enabled"],
            {"component": "closed_loop_engine"},
        ) == 1.0
        assert _metric_value(
            family_by_name["netsphere_controller_setting_value"],
            {"setting": "webhook_retry_attempts"},
        ) == 3.0
    finally:
        db.close()
