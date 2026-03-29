import time

from prometheus_client import REGISTRY
from prometheus_client.core import GaugeMetricFamily
from sqlalchemy import func

from app.db.session import SessionLocal
from app.models.approval import ApprovalRequest
from app.models.automation import AutomationRule
from app.models.device import ComplianceReport, Device, Issue, Link
from app.models.discovery import DiscoveredDevice, DiscoveryJob
from app.models.settings import SystemSetting
from app.models.topology_candidate import TopologyNeighborCandidate


def _as_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return bool(default)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return bool(default)


def _setting_lookup(db):
    rows = db.query(SystemSetting.key, SystemSetting.value).all()
    return {str(key): value for key, value in rows}


class OpsMetricsCollector:
    def __init__(self, cache_ttl_seconds: int = 15):
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
            settings = _setting_lookup(db)

            discovery_jobs = GaugeMetricFamily(
                "netsphere_discovery_jobs_total",
                "NetSphere discovery jobs grouped by status.",
                labels=["status"],
            )
            for status, count in (
                db.query(DiscoveryJob.status, func.count(DiscoveryJob.id))
                .group_by(DiscoveryJob.status)
                .all()
            ):
                discovery_jobs.add_metric([str(status or "unknown").lower()], float(count or 0))

            discovered_devices = GaugeMetricFamily(
                "netsphere_discovered_devices_total",
                "NetSphere discovered devices grouped by reconciliation status.",
                labels=["status"],
            )
            for status, count in (
                db.query(DiscoveredDevice.status, func.count(DiscoveredDevice.id))
                .group_by(DiscoveredDevice.status)
                .all()
            ):
                discovered_devices.add_metric([str(status or "unknown").lower()], float(count or 0))

            topology_candidates = GaugeMetricFamily(
                "netsphere_topology_candidates_total",
                "Topology neighbor candidates grouped by status.",
                labels=["status"],
            )
            for status, count in (
                db.query(TopologyNeighborCandidate.status, func.count(TopologyNeighborCandidate.id))
                .group_by(TopologyNeighborCandidate.status)
                .all()
            ):
                topology_candidates.add_metric([str(status or "unknown").lower()], float(count or 0))

            topology_links = GaugeMetricFamily(
                "netsphere_topology_links_total",
                "Total active topology links known to NetSphere.",
            )
            topology_links.add_metric(
                [],
                float(db.query(func.count(Link.id)).scalar() or 0),
            )

            approvals = GaugeMetricFamily(
                "netsphere_approval_requests_total",
                "Approval requests grouped by lifecycle status.",
                labels=["status"],
            )
            for status, count in (
                db.query(ApprovalRequest.status, func.count(ApprovalRequest.id))
                .group_by(ApprovalRequest.status)
                .all()
            ):
                approvals.add_metric([str(status or "unknown").lower()], float(count or 0))

            automation_rules = GaugeMetricFamily(
                "netsphere_automation_rules_total",
                "Automation rules grouped by enabled state.",
                labels=["enabled"],
            )
            for enabled, count in (
                db.query(AutomationRule.enabled, func.count(AutomationRule.id))
                .group_by(AutomationRule.enabled)
                .all()
            ):
                automation_rules.add_metric(["true" if enabled else "false"], float(count or 0))

            compliance_reports = GaugeMetricFamily(
                "netsphere_compliance_reports_total",
                "Compliance reports grouped by status.",
                labels=["status"],
            )
            for status, count in (
                db.query(ComplianceReport.status, func.count(ComplianceReport.id))
                .group_by(ComplianceReport.status)
                .all()
            ):
                compliance_reports.add_metric([str(status or "unknown").lower()], float(count or 0))

            compliance_score = GaugeMetricFamily(
                "netsphere_compliance_average_score",
                "Average compliance match percentage across reports.",
            )
            compliance_score.add_metric(
                [],
                float(db.query(func.avg(ComplianceReport.match_percentage)).scalar() or 0.0),
            )

            issues = GaugeMetricFamily(
                "netsphere_issues_total",
                "Current issues grouped by severity and status.",
                labels=["severity", "status"],
            )
            for severity, status, count in (
                db.query(Issue.severity, Issue.status, func.count(Issue.id))
                .group_by(Issue.severity, Issue.status)
                .all()
            ):
                issues.add_metric(
                    [str(severity or "unknown").lower(), str(status or "unknown").lower()],
                    float(count or 0),
                )

            controller_health = GaugeMetricFamily(
                "netsphere_controller_component_enabled",
                "Operational controller features and policy toggles exposed as 0 or 1.",
                labels=["component"],
            )
            controller_health.add_metric(
                ["closed_loop_engine"],
                1.0 if _as_bool(settings.get("closed_loop_engine_enabled"), default=True) else 0.0,
            )
            controller_health.add_metric(
                ["closed_loop_auto_execute"],
                1.0 if _as_bool(settings.get("closed_loop_auto_execute_enabled"), default=False) else 0.0,
            )
            controller_health.add_metric(
                ["closed_loop_execute_change_actions"],
                1.0 if _as_bool(settings.get("closed_loop_execute_change_actions"), default=False) else 0.0,
            )
            controller_health.add_metric(
                ["webhook_enabled"],
                1.0 if _as_bool(settings.get("webhook_enabled"), default=False) else 0.0,
            )
            controller_health.add_metric(
                ["webhook_url_configured"],
                1.0 if str(settings.get("webhook_url") or "").strip() else 0.0,
            )
            controller_health.add_metric(
                ["webhook_secret_configured"],
                1.0 if str(settings.get("webhook_secret") or "").strip() else 0.0,
            )
            controller_health.add_metric(
                ["intent_northbound_policy_enabled"],
                1.0 if _as_bool(settings.get("intent_northbound_policy_enabled"), default=False) else 0.0,
            )

            controller_settings = GaugeMetricFamily(
                "netsphere_controller_setting_value",
                "Numeric controller and northbound policy settings.",
                labels=["setting"],
            )
            controller_settings.add_metric(
                ["intent_northbound_max_auto_publish_risk_score"],
                float(settings.get("intent_northbound_max_auto_publish_risk_score") or 0.0),
            )
            controller_settings.add_metric(
                ["webhook_timeout_seconds"],
                float(settings.get("webhook_timeout_seconds") or 0.0),
            )
            controller_settings.add_metric(
                ["webhook_retry_attempts"],
                float(settings.get("webhook_retry_attempts") or 0.0),
            )
            controller_settings.add_metric(
                ["webhook_retry_backoff_seconds"],
                float(settings.get("webhook_retry_backoff_seconds") or 0.0),
            )
            controller_settings.add_metric(
                ["webhook_retry_max_backoff_seconds"],
                float(settings.get("webhook_retry_max_backoff_seconds") or 0.0),
            )
            controller_settings.add_metric(
                ["webhook_retry_jitter_seconds"],
                float(settings.get("webhook_retry_jitter_seconds") or 0.0),
            )

            fleet = GaugeMetricFamily(
                "netsphere_inventory_objects_total",
                "NetSphere inventory object totals by object type.",
                labels=["object_type"],
            )
            fleet.add_metric(["devices"], float(db.query(func.count(Device.id)).scalar() or 0))
            fleet.add_metric(["links"], float(db.query(func.count(Link.id)).scalar() or 0))
            fleet.add_metric(["issues"], float(db.query(func.count(Issue.id)).scalar() or 0))

            return [
                discovery_jobs,
                discovered_devices,
                topology_candidates,
                topology_links,
                approvals,
                automation_rules,
                compliance_reports,
                compliance_score,
                issues,
                controller_health,
                controller_settings,
                fleet,
            ]
        finally:
            db.close()


def register_ops_metrics(cache_ttl_seconds: int = 15) -> None:
    collector = OpsMetricsCollector(cache_ttl_seconds=cache_ttl_seconds)
    try:
        REGISTRY.register(collector)
    except ValueError:
        return
