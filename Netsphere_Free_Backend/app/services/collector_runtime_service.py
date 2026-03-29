from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Callable, Dict, Iterable

from sqlalchemy.orm import Session


logger = logging.getLogger(__name__)


def _parse_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


class CollectorRuntimeService:
    LOCAL_EXECUTION_ENV_KEY = "PREVIEW_LOCAL_EMBEDDED_EXECUTION"

    @classmethod
    def is_local_embedded_execution_enabled(
        cls,
        *,
        db: Session | None = None,
        policy: Dict[str, Any] | None = None,
    ) -> bool:
        env_value = os.getenv(cls.LOCAL_EXECUTION_ENV_KEY)
        if env_value is not None and str(env_value).strip():
            return _parse_bool(env_value, default=False)

        resolved_policy = policy
        if resolved_policy is None and db is not None:
            try:
                from app.services.preview_edition_service import PreviewEditionService

                resolved_policy = PreviewEditionService.get_policy(db)
            except Exception:
                resolved_policy = None

        if isinstance(resolved_policy, dict):
            role = str(resolved_policy.get("deployment_role") or "").strip().lower()
            default = role == "collector_installed"
            return _parse_bool(resolved_policy.get("local_embedded_execution"), default=default)

        return False

    @classmethod
    def enqueue(
        cls,
        *,
        task_name: str,
        target: Callable[..., Any],
        args: Iterable[Any] | None = None,
        countdown: float | None = None,
    ) -> Dict[str, Any]:
        run_args = list(args or [])
        delay_seconds = max(0.0, float(countdown or 0.0))

        def _run() -> None:
            if delay_seconds > 0:
                time.sleep(delay_seconds)
            try:
                target(*run_args)
            except Exception:
                logger.exception("Embedded collector task failed: %s", task_name)

        thread = threading.Thread(
            target=_run,
            name=f"embedded_collector_{str(task_name or 'task').replace(' ', '_')}",
            daemon=True,
        )
        thread.start()
        return {
            "status": "enqueued",
            "executor": "embedded_local",
            "delivery": "local_thread",
            "task_name": str(task_name or "task"),
        }
