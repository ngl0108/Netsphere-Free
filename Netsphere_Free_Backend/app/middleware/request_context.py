from __future__ import annotations

import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.request_context import set_request_context


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        set_request_context(rid, request.url.path, request.method)

        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response

