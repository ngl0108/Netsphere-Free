from __future__ import annotations

from contextvars import ContextVar


request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
path_var: ContextVar[str | None] = ContextVar("path", default=None)
method_var: ContextVar[str | None] = ContextVar("method", default=None)


def set_request_context(request_id: str | None, path: str | None, method: str | None) -> None:
    request_id_var.set(request_id)
    path_var.set(path)
    method_var.set(method)


def clear_request_context() -> None:
    set_request_context(None, None, None)


def get_request_id() -> str | None:
    return request_id_var.get()


def get_path() -> str | None:
    return path_var.get()


def get_method() -> str | None:
    return method_var.get()
