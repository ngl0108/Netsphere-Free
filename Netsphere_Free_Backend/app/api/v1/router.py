from fastapi import APIRouter, Depends

from app.api import deps
from app.api.license_deps import scope_dependencies
from app.api.v1.endpoints import (
    approval,
    audit,
    auth,
    automation_hub,
    cloud,
    compliance,
    config,
    config_template,
    discovery_hints,
    devices,
    diagnosis,
    discovery,
    fabric,
    ha,
    images,
    intent,
    intent_templates,
    issue_approval_context,
    issue_actions,
    issue_service_impact,
    issue_sop,
    jobs,
    known_errors,
    license,
    logs,
    misc,
    monitoring_profiles,
    observability,
    ops,
    policy,
    preventive_checks,
    preview,
    settings,
    state_history,
    source_of_truth,
    service_groups,
    sites,
    snmp_profiles,
    support,
    topology,
    traffic,
    variables,
    visual_config,
    ztp,
)

api_router = APIRouter(dependencies=[Depends(deps.enforce_preview_request_policy)])

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(devices.router, prefix="/devices", tags=["devices"])
api_router.include_router(sites.router, prefix="/sites", tags=["sites"])
api_router.include_router(logs.router, prefix="/logs", tags=["logs"])
api_router.include_router(misc.router, prefix="/sdn", tags=["sdn"])
api_router.include_router(issue_approval_context.router, prefix="/sdn", tags=["sdn-approval-context"])
api_router.include_router(issue_actions.router, prefix="/sdn", tags=["sdn-actions"])
api_router.include_router(issue_service_impact.router, prefix="/sdn", tags=["sdn-service-impact"])
api_router.include_router(issue_sop.router, prefix="/sdn", tags=["sdn-sop"])
api_router.include_router(known_errors.router, prefix="/sdn", tags=["sdn-knowledge"])

api_router.include_router(config.router, prefix="/config", tags=["config"])
api_router.include_router(config_template.router, prefix="/templates", tags=["templates"])
api_router.include_router(variables.router, prefix="/vars", tags=["variables"])
api_router.include_router(
    compliance.router,
    prefix="/compliance",
    tags=["compliance"],
    dependencies=scope_dependencies("compliance"),
)
api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
api_router.include_router(approval.router, prefix="/approval", tags=["approval"])

api_router.include_router(
    images.router,
    prefix="/sdn/images",
    tags=["images"],
    dependencies=scope_dependencies("images"),
)
api_router.include_router(
    policy.router,
    prefix="/sdn/policies",
    tags=["policies"],
    dependencies=scope_dependencies("policies"),
)
api_router.include_router(settings.router, prefix="/settings", tags=["settings"])
api_router.include_router(preview.router, prefix="/preview", tags=["preview"])
api_router.include_router(license.router, prefix="/license", tags=["license"])
api_router.include_router(support.router, prefix="/support", tags=["support"])
api_router.include_router(service_groups.router, prefix="/service-groups", tags=["service-groups"])
api_router.include_router(monitoring_profiles.router, prefix="/monitoring-profiles", tags=["monitoring-profiles"])
api_router.include_router(
    source_of_truth.router,
    prefix="/automation-hub/source-of-truth",
    tags=["source-of-truth"],
    dependencies=scope_dependencies("automation_hub"),
)
api_router.include_router(
    state_history.router,
    prefix="/automation-hub/state-history",
    tags=["state-history"],
    dependencies=scope_dependencies("automation_hub"),
)
api_router.include_router(
    cloud.router,
    prefix="/cloud",
    tags=["cloud"],
    dependencies=scope_dependencies("cloud"),
)

api_router.include_router(
    ztp.router,
    prefix="/ztp",
    tags=["ztp"],
    dependencies=scope_dependencies("ztp"),
)
api_router.include_router(audit.router, prefix="/audit", tags=["audit"])

api_router.include_router(topology.router, prefix="/topology", tags=["topology"])
api_router.include_router(
    fabric.router,
    prefix="/fabric",
    tags=["fabric"],
    dependencies=scope_dependencies("fabric"),
)
api_router.include_router(discovery.router, prefix="/discovery", tags=["discovery"])
api_router.include_router(discovery_hints.router, prefix="/discovery/hints", tags=["discovery-hints"])
api_router.include_router(
    visual_config.router,
    prefix="/visual",
    tags=["visual"],
    dependencies=scope_dependencies("visual"),
)
api_router.include_router(
    traffic.router,
    prefix="/traffic",
    tags=["traffic"],
    dependencies=scope_dependencies("traffic"),
)
api_router.include_router(snmp_profiles.router, prefix="/snmp-profiles", tags=["snmp-profiles"])
api_router.include_router(
    observability.router,
    prefix="/observability",
    tags=["observability"],
    dependencies=scope_dependencies("observability"),
)
api_router.include_router(
    automation_hub.router,
    prefix="/automation-hub",
    tags=["automation-hub"],
    dependencies=scope_dependencies("automation_hub"),
)
api_router.include_router(
    intent.router,
    prefix="/intent",
    tags=["intent"],
)
api_router.include_router(
    intent_templates.router,
    prefix="/intent/templates",
    tags=["intent-templates"],
)
api_router.include_router(
    diagnosis.router,
    prefix="/diagnosis",
    tags=["diagnosis"],
    dependencies=scope_dependencies("diagnosis"),
)
api_router.include_router(
    ops.router,
    prefix="/ops",
    tags=["ops"],
)
api_router.include_router(
    preventive_checks.router,
    prefix="/ops/preventive-checks",
    tags=["preventive-checks"],
)
api_router.include_router(ha.router, prefix="/ha", tags=["ha"])
