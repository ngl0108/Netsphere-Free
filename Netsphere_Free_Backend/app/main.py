from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import uvicorn
import asyncio
from contextlib import asynccontextmanager
import logging
import os # [FIX] Import os
from pathlib import Path

from app.core.logging_config import configure_logging

configure_logging()
logger = logging.getLogger(__name__)

# [중요] Celery 앱 로드
try:
    import celery_app
except ImportError:
    logger.warning("Celery not found. Task scheduling will be disabled.")
    celery_app = None

from app.api.v1.router import api_router
from app.db.session import engine, Base
from app.models import device as device_models
from app.models import user as user_models
from app.models import user_password_history
from app.models import license_state
from app.models import user_session
from app.models import mfa_challenge
from app.models import email_verification
from app.models import ha_lease
from app.models import automation # [NEW] Automation Rules
from app.models import preview_collector_registration
from app.models import ztp_queue as ztp_models  # [NEW] ZTP 모델 임포트
from app.models import discovery # [NEW] Discovery Models
from app.models import topology # [NEW] Topology Layout
from app.models import topology_candidate
from app.models import endpoint
from app.models import device_inventory
from app.models import visual_config
from app.models import approval # [NEW] Approval
from app.models import credentials
from app.models import cloud
from app.models import ip_intel
from app.models import discovery_hint
from app.models import discovery_hint_learning
from app.models import asset_change_event
from app.models import monitoring_profile
from app.models import known_error
from app.models import operation_action
from app.models import preventive_check
from app.models import service_group
from app.services.syslog_service import SyslogProtocol  
from app.services.netflow_collector import NetflowProtocol
from app.services.snmp_trap_service import SnmpTrapServer
from app.core import security
from app.db.session import SessionLocal
from app.db.migrations import run_migrations
import secrets
from datetime import datetime, timezone

app_env = (os.getenv("APP_ENV") or "").strip().lower()
if app_env not in {"test", "pytest"}:
    Base.metadata.create_all(bind=engine)
    run_migrations(engine)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _preview_deployment_role() -> str:
    return str(os.getenv("PREVIEW_DEPLOYMENT_ROLE", "") or "").strip().lower()


def _is_preview_installed_collector() -> bool:
    edition = str(os.getenv("NETSPHERE_EDITION", "") or "").strip().lower()
    role = _preview_deployment_role()
    return edition == "preview" and role in {"collector_installed", "collector", "installed_collector", "local_collector"}



@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("NetSphere API Server Starting...")
    scheduler = None
    discovery_hint_sync_scheduler = None
    ha_manager = None
    disable_integrated_servers = _env_bool(
        "PREVIEW_DISABLE_INTEGRATED_SERVERS",
        default=_is_preview_installed_collector(),
    )

    db = SessionLocal()
    try:
        system_user = db.query(user_models.User).filter(user_models.User.username == "system").first()
        if not system_user:
            hashed_pw = security.get_password_hash(secrets.token_urlsafe(32))
            new_system = user_models.User(
                username="system",
                hashed_password=hashed_pw,
                full_name="System Automation",
                role="admin",
                is_active=True,
                must_change_password=False,
                eula_accepted=True,
                password_changed_at=datetime.now(timezone.utc),
            )
            db.add(new_system)
            db.commit()
            try:
                from app.services.password_policy_service import PasswordPolicyService

                PasswordPolicyService.record_password(db, new_system)
                db.commit()
            except Exception:
                pass
        
        # [NEW] Seed default configuration templates
        from app.services.default_templates import seed_default_templates
        seed_default_templates(db)
        
    except Exception:
        logger.exception("Bootstrap provisioning failed")
    finally:
        db.close()

    try:
        from app.services.ha_service import HaManager

        ha_manager = HaManager()
        ha_manager.start()
        app.state.ha_manager = ha_manager
        logger.info("HA manager started (settings-controlled)")
    except Exception:
        logger.exception("HA manager failed to start")

    def _should_run_background() -> bool:
        mgr = getattr(app.state, "ha_manager", None) or ha_manager
        if not mgr:
            return True
        st = mgr.get_state()
        if not st or not st.enabled:
            return True
        return st.role == "active"

    if _should_run_background():
        if disable_integrated_servers:
            logger.info("Integrated listeners are disabled for this runtime profile")
        else:
            loop = asyncio.get_running_loop()
            try:
                transport, protocol = await loop.create_datagram_endpoint(
                    lambda: SyslogProtocol(),
                    local_addr=("0.0.0.0", 514),
                )
                logger.info("Syslog Server is running on UDP port 514 (Integrated)")
            except PermissionError:
                logger.warning("Port 514 requires Admin privileges. Syslog server failed to start.")
            except Exception:
                logger.exception("Syslog server failed to start")

            try:
                trap_server = SnmpTrapServer(host="0.0.0.0", port=162, community="public")
                trap_server.start()
                logger.info("SNMP Trap Receiver is running on UDP port 162 (v2c)")
            except PermissionError:
                try:
                    trap_server = SnmpTrapServer(host="0.0.0.0", port=2162, community="public")
                    trap_server.start()
                    logger.info("SNMP Trap Receiver is running on UDP port 2162 (v2c)")
                except Exception:
                    logger.exception("SNMP Trap receiver failed to start")
            except Exception:
                logger.exception("SNMP Trap receiver failed to start")

            try:
                transport_nf, protocol_nf = await loop.create_datagram_endpoint(
                    lambda: NetflowProtocol(),
                    local_addr=("0.0.0.0", 2055),
                )
                logger.info("NetFlow Collector is running on UDP port 2055 (v5)")
            except Exception:
                logger.exception("NetFlow collector failed to start")

            try:
                from app.services.dhcp_service import start_dhcp_server_if_enabled

                start_dhcp_server_if_enabled()
            except Exception:
                logger.exception("DHCP Failed to initialize builtin DHCP")

        try:
            from app.services.auto_discovery_scheduler import AutoDiscoveryScheduler

            scheduler = AutoDiscoveryScheduler()
            scheduler.start()
            app.state.auto_discovery_scheduler = scheduler
            logger.info("Auto Discovery Scheduler started (settings-controlled)")
        except Exception:
            logger.exception("Auto Discovery Scheduler failed to start")

        try:
            from app.services.discovery_hint_seed_rule_service import DiscoveryHintSeedRuleService

            seed_result = DiscoveryHintSeedRuleService.install_defaults()
            logger.info(
                "Discovery hint seed defaults ensured: installed=%s available=%s",
                int(seed_result.get("installed") or 0),
                int(seed_result.get("available") or 0),
            )
        except Exception:
            logger.exception("Discovery hint seed defaults failed to initialize")

        try:
            from app.services.monitoring_profile_service import MonitoringProfileService

            profile_db = SessionLocal()
            try:
                seed_result = MonitoringProfileService.install_defaults(profile_db)
                logger.info(
                    "Monitoring profile defaults ensured: installed=%s available=%s",
                    int(seed_result.get("installed") or 0),
                    int(seed_result.get("available") or 0),
                )
            finally:
                profile_db.close()
        except Exception:
            logger.exception("Monitoring profile defaults failed to initialize")

        try:
            from app.services.preventive_check_service import PreventiveCheckService

            preventive_db = SessionLocal()
            try:
                preventive_result = PreventiveCheckService.install_defaults(db=preventive_db)
            finally:
                preventive_db.close()
            logger.info(
                "Preventive check defaults ensured: installed=%s available=%s",
                int(preventive_result.get("installed") or 0),
                int(preventive_result.get("available") or 0),
            )
        except Exception:
            logger.exception("Preventive check defaults failed to initialize")

        try:
            from app.services.discovery_hint_sync_scheduler import DiscoveryHintSyncScheduler

            discovery_hint_sync_scheduler = DiscoveryHintSyncScheduler()
            discovery_hint_sync_scheduler.start()
            app.state.discovery_hint_sync_scheduler = discovery_hint_sync_scheduler
            logger.info("Discovery hint sync scheduler started")
        except Exception:
            logger.exception("Discovery hint sync scheduler failed to start")
    else:
        logger.info("HA standby: background collectors/schedulers are disabled")

    yield

    try:
        mgr = getattr(app.state, "ha_manager", None) or ha_manager
        if mgr:
            mgr.stop()
    except Exception:
        pass

    try:
        sch = getattr(app.state, "auto_discovery_scheduler", None) or scheduler
        if sch:
            sch.stop()
    except Exception:
        pass

    try:
        hint_sync = getattr(app.state, "discovery_hint_sync_scheduler", None) or discovery_hint_sync_scheduler
        if hint_sync:
            hint_sync.stop()
    except Exception:
        pass

    logger.info("NetSphere API Server Stopping...")


app = FastAPI(title="NetSphere API", lifespan=lifespan)

try:
    from prometheus_fastapi_instrumentator import Instrumentator

    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

    from app.observability.device_metrics import register_device_metrics
    from app.observability.ops_metrics import register_ops_metrics

    register_device_metrics(cache_ttl_seconds=int(os.getenv("DEVICE_METRICS_CACHE_TTL_SECONDS", "60") or 60))
    register_ops_metrics(cache_ttl_seconds=int(os.getenv("OPS_METRICS_CACHE_TTL_SECONDS", "60") or 60))
except Exception:
    pass

# CORS 설정 (프론트엔드 연동용)
# [Security] Whitelist domains in production
allow_origins = ["*"]
if os.getenv("APP_ENV") == "production":
    allow_origins = os.getenv("CORS_ORIGINS", "").split(",")
    if not allow_origins or allow_origins == [""]:
        allow_origins = []  # Empty list means no access by default in prod if not configured

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# [NEW] Response Wrapper (standardize success payload for JSON responses)
from app.middleware.response_wrapper import ResponseWrapperMiddleware
app.add_middleware(ResponseWrapperMiddleware)

# [NEW] Request Context (request_id/path/method propagation)
from app.middleware.request_context import RequestContextMiddleware
app.add_middleware(RequestContextMiddleware)

# [NEW] HA Standby Guard
from app.middleware.ha import HaStandbyMiddleware
app.add_middleware(HaStandbyMiddleware)

# [NEW] Audit Middleware Registration
from app.middleware.audit import AuditMiddleware
app.add_middleware(AuditMiddleware)

from fastapi import Request, status, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.core.api_response import fail

@app.exception_handler(HTTPException)
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: Exception):
    status_code = int(getattr(exc, "status_code", 500) or 500)
    detail = getattr(exc, "detail", None)
    details = None
    message = "HTTP error"
    code = f"HTTP_{status_code}"
    if isinstance(detail, str):
        message = detail
    elif isinstance(detail, dict):
        custom_code = str(detail.get("code") or "").strip()
        if custom_code:
            code = custom_code
        message = str(detail.get("message") or detail.get("detail") or message)
        if "details" in detail:
            details = detail.get("details")
        else:
            extra = {k: v for k, v in detail.items() if k not in {"code", "message", "detail"}}
            if extra:
                details = extra
    elif detail is not None:
        details = detail

    # OAuth2 dependency raises bare "Not authenticated" errors; normalize these.
    if code == f"HTTP_{status_code}" and status_code == status.HTTP_401_UNAUTHORIZED:
        lowered = str(message or "").strip().lower()
        if lowered == "not authenticated":
            code = "AUTH_NOT_AUTHENTICATED"
            message = "Authentication is required"
        elif "validate credentials" in lowered:
            code = "AUTH_CREDENTIALS_INVALID"

    return fail(
        status_code=status_code,
        code=code,
        message=message,
        details=details,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return fail(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        code="VALIDATION_ERROR",
        message="Request validation failed",
        details=exc.errors(),
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import traceback
    
    # Log full stack trace for debugging
    error_details = traceback.format_exc()
    logger.error(f"Unhandled exception at {request.method} {request.url.path}: {str(exc)}\n{error_details}")
    
    # Determine if we should expose details (dev mode only)
    is_production = os.getenv("APP_ENV") == "production"
    
    return fail(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code="INTERNAL_SERVER_ERROR",
        message="Internal Server Error" if is_production else str(exc),
        details=None if is_production else {"trace": error_details.splitlines()[-3:]} # Show last 3 lines in dev
    )

app.include_router(api_router, prefix="/api/v1")


def _resolve_frontend_dist_dir() -> Path | None:
    if not _env_bool("NETSPHERE_SERVE_FRONTEND_STATIC", default=False):
        return None

    configured = str(os.getenv("NETSPHERE_FRONTEND_DIST_DIR", "") or "").strip()
    if configured:
        candidate = Path(configured)
        if not candidate.is_absolute():
            candidate = Path(__file__).resolve().parents[2] / candidate
    else:
        candidate = Path(__file__).resolve().parents[2] / "Netsphere_Free_Frontend" / "dist"

    index_file = candidate / "index.html"
    if not index_file.exists():
        logger.warning("Frontend static serving requested but dist not found: %s", candidate)
        return None
    return candidate


FRONTEND_DIST_DIR = _resolve_frontend_dist_dir()


def _frontend_static_headers() -> dict[str, str] | None:
    if not _is_preview_installed_collector():
        return None
    # Collector-local is a test harness, so stale browser bundles cause more
    # pain than the small performance gain of caching static assets.
    return {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0",
    }


if FRONTEND_DIST_DIR is None:
    @app.get("/")
    def read_root():
        return {"message": "NetSphere API Server is Running!"}
else:
    @app.get("/", include_in_schema=False)
    def read_root():
        return FileResponse(FRONTEND_DIST_DIR / "index.html", headers=_frontend_static_headers())


    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_frontend_app(full_path: str):
        normalized = str(full_path or "").lstrip("/")
        if normalized in {"api", "docs", "redoc", "openapi.json", "metrics"} or normalized.startswith(
            ("api/", "docs/", "redoc/", "metrics/")
        ):
            raise HTTPException(status_code=404, detail="Not Found")
        candidate = FRONTEND_DIST_DIR / normalized
        if candidate.exists() and candidate.is_file():
            return FileResponse(candidate, headers=_frontend_static_headers())
        return FileResponse(FRONTEND_DIST_DIR / "index.html", headers=_frontend_static_headers())


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True, log_config=None)
