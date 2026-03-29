from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse


def ok(data: Any = None) -> dict:
    return {"success": True, "data": data}


def fail(*, status_code: int, code: str, message: str, details: Any = None) -> JSONResponse:
    payload: dict[str, Any] = {"success": False, "error": {"code": code, "message": message}}
    if details is not None:
        payload["error"]["details"] = details
    return JSONResponse(status_code=status_code, content=payload)

