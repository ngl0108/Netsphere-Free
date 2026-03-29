import json
import logging
import os
import re
import sys
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone

from app.core.request_context import get_method, get_path, get_request_id


class JsonFormatter(logging.Formatter):
    _redact_re = re.compile(
        r"(?i)\b(password|passwd|secret|token|api[_-]?key|snmp_community|community|auth[_-]?key|priv[_-]?key)\b\s*[:=]\s*([^\s,;]+)"
    )

    @classmethod
    def _redact(cls, msg: str) -> str:
        return cls._redact_re.sub(lambda m: f"{m.group(1)}=********", msg)

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": self._redact(record.getMessage()),
        }
        for k in ("request_id", "path", "method", "status_code", "user", "device_id", "job_id", "duration_ms"):
            v = getattr(record, k, None)
            if v is not None:
                payload[k] = v
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if getattr(record, "request_id", None) is None:
            rid = get_request_id()
            if rid is not None:
                record.request_id = rid
        if getattr(record, "path", None) is None:
            p = get_path()
            if p is not None:
                record.path = p
        if getattr(record, "method", None) is None:
            m = get_method()
            if m is not None:
                record.method = m
        return True


def configure_logging() -> None:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    fmt = os.getenv("LOG_FORMAT", "json").lower()
    root = logging.getLogger()
    root.setLevel(level)

    if fmt == "text":
        formatter: logging.Formatter = logging.Formatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    else:
        formatter = JsonFormatter()

    handlers: list[logging.Handler] = []
    ctx_filter = ContextFilter()

    stream = logging.StreamHandler(sys.stdout)
    stream.setLevel(level)
    stream.setFormatter(formatter)
    stream.addFilter(ctx_filter)
    handlers.append(stream)

    to_file = (os.getenv("LOG_TO_FILE") or "").strip().lower() in {"1", "true", "yes"}
    log_file = os.getenv("LOG_FILE", "").strip()
    if to_file or log_file:
        log_dir = os.getenv("LOG_DIR", "").strip() or "logs"
        if not log_file:
            log_file = os.path.join(log_dir, "app.log")
        try:
            os.makedirs(os.path.dirname(log_file) or ".", exist_ok=True)
            max_bytes = int(os.getenv("LOG_MAX_BYTES", str(10 * 1024 * 1024)))
            backup_count = int(os.getenv("LOG_BACKUP_COUNT", "5"))
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            file_handler.addFilter(ctx_filter)
            handlers.append(file_handler)
        except Exception:
            pass

    root.handlers = handlers

    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        logger = logging.getLogger(name)
        logger.setLevel(level)
        logger.handlers = handlers
        logger.propagate = False
