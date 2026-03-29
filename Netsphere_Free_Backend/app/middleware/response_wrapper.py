from __future__ import annotations

import json
from typing import Any

class ResponseWrapperMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = str(scope.get("path") or "").strip()
        if path in {"/openapi.json", "/docs", "/docs/", "/docs/oauth2-redirect", "/redoc", "/redoc/"}:
            await self.app(scope, receive, send)
            return

        buffered = False
        passthrough = False
        status_code: int | None = None
        headers: list[tuple[bytes, bytes]] = []
        body_chunks: list[bytes] = []

        async def send_wrapper(message):
            nonlocal buffered, passthrough, status_code, headers, body_chunks

            if message["type"] == "http.response.start":
                status_code = int(message.get("status") or 0)
                headers = list(message.get("headers") or [])

                ct = ""
                for k, v in headers:
                    if k.lower() == b"content-type":
                        try:
                            ct = v.decode("latin-1")
                        except Exception:
                            ct = ""
                        break
                ct_l = ct.lower()

                if status_code < 200 or status_code >= 300 or status_code in (204, 304):
                    passthrough = True
                elif "text/event-stream" in ct_l:
                    passthrough = True
                elif "application/json" not in ct_l:
                    passthrough = True

                if passthrough:
                    await send(message)
                    return

                buffered = True
                return

            if message["type"] == "http.response.body":
                if passthrough or not buffered:
                    await send(message)
                    return

                body_chunks.append(message.get("body", b"") or b"")
                if message.get("more_body", False):
                    return

                body = b"".join(body_chunks)
                out_body = body

                try:
                    decoded = json.loads(body.decode("utf-8")) if body else None
                except Exception:
                    decoded = None

                if decoded is not None and not (isinstance(decoded, dict) and "success" in decoded):
                    wrapped: dict[str, Any] = {"success": True, "data": decoded}
                    out_body = json.dumps(wrapped, ensure_ascii=False).encode("utf-8")

                out_headers: list[tuple[bytes, bytes]] = []
                for k, v in headers:
                    if k.lower() == b"content-length":
                        continue
                    out_headers.append((k, v))
                out_headers.append((b"content-length", str(len(out_body)).encode("ascii")))

                await send({"type": "http.response.start", "status": status_code or 200, "headers": out_headers})
                await send({"type": "http.response.body", "body": out_body, "more_body": False})
                return

            await send(message)

        await self.app(scope, receive, send_wrapper)
