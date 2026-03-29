from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
from app.db.session import SessionLocal
from app.services.audit_service import AuditService
from app.core import security
from app.api import deps
import traceback
import logging

logger = logging.getLogger(__name__)

class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 1. Process the request
        response = await call_next(request)

        # 2. Log only "Write" operations (POST, PUT, DELETE, PATCH)
        #    Skip Login endpoint to avoid logging passwords (though audit service handles details carefully)
        #    Skip audit logs themselves to avoid recursion
        if request.method in ["POST", "PUT", "DELETE", "PATCH"]:
            path = request.url.path
            if "/audit" in path or "/login" in path or "/logout" in path:
                return response

            # 3. Background Logging (Fire and Forget)
            #    We use a separate DB session for logging to not interfere with the main request
            try:
                db = SessionLocal()
                try:
                    # Attempt to identify user from Authorization header
                    # We duplicate some auth logic here because Middleware runs outside dependency injection
                    auth_header = request.headers.get("Authorization")
                    user = None
                    if auth_header and auth_header.startswith("Bearer "):
                        token = auth_header.split(" ")[1]
                        try:
                            # Verify token simply to get user ID/Name
                            payload = security.decode_access_token(token)
                            if payload:
                                # We create a mock user object or fetch strictly if needed
                                # Here we just need the ID/Username for logging
                                class MockUser:
                                    def __init__(self, id, username):
                                        self.id = id
                                        self.username = username
                                user = MockUser(id=payload.get("uid") or payload.get("sub"), username=payload.get("sub"))
                        except:
                            pass # Invalid token, logged as 'system' or 'anonymous'

                    # Determine Resource
                    resource_type = path.strip("/").split("/")[2] if len(path.split("/")) > 3 else "system"
                    
                    # Log it
                    AuditService.log(
                        db=db,
                        user=user,
                        action=request.method,
                        resource_type=resource_type,
                        resource_name=path,
                        details=f"Status: {response.status_code}",
                        status="success" if response.status_code < 400 else "failed",
                        ip=request.client.host
                    )
                finally:
                    db.close()
            except Exception as e:
                # Middleware should never crash the app
                logger.exception("Audit Log Error")
                # traceback.print_exc()

        return response
