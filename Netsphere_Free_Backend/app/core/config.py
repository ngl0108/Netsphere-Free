
import os
import logging

logger = logging.getLogger("uvicorn")

# [Security] Force explicit SECRET_KEY in production
_env_secret = os.getenv("SECRET_KEY")
if not _env_secret:
    if os.getenv("APP_ENV") == "production":
        raise ValueError("CRITICAL: SECRET_KEY environment variable is missing in production!")
    else:
        # Use deterministic dev key so auth tokens survive process restarts in local/dev.
        # (Production still requires explicit SECRET_KEY.)
        _env_secret = os.getenv("DEV_SECRET_KEY", "netmanager-dev-secret-change-me")
        logger.warning("SECRET_KEY not set. Using deterministic development key.")

SECRET_KEY = _env_secret
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
ACCESS_TOKEN_REFRESH_GRACE_SECONDS = int(os.getenv("ACCESS_TOKEN_REFRESH_GRACE_SECONDS", "120"))
