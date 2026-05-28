import structlog
from app.auth.resolve import resolve_principal
from django.db import close_old_connections
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

log = structlog.get_logger()


class PrincipalMiddleware(BaseHTTPMiddleware):
    """
    Resolve bench principal per request and refresh Django DB connections.

    FastAPI runs sync ORM work via threadpool; without close_old_connections(),
    Postgres connections opened in worker threads can go stale and raise
    OperationalError ("the connection is closed") — browsers then show
    "Failed to fetch" when 500 responses omit CORS headers.

    Exceptions raised here (e.g. JWT_SECRET unset, principal resolution bugs)
    are caught and returned as a JSON 500 WITH manual CORS headers attached.
    Without this, an exception from resolve_principal bypasses Starlette's
    CORSMiddleware on the way out and the browser sees an opaque CORS error
    instead of a useful 500 status.
    """

    def __init__(self, app, cors_origins: list[str] | None = None) -> None:
        super().__init__(app)
        self._cors_origins = cors_origins or []

    def _cors_headers(self, request: Request) -> dict[str, str]:
        origin = request.headers.get("origin")
        if origin and origin in self._cors_origins:
            return {
                "access-control-allow-origin": origin,
                "access-control-allow-credentials": "true",
                "vary": "Origin",
            }
        return {}

    async def dispatch(self, request: Request, call_next) -> Response:
        try:
            close_old_connections()
            request.state.principal = await resolve_principal(request)
            return await call_next(request)
        except Exception:
            log.exception("principal_middleware_error", path=request.url.path)
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error"},
                headers=self._cors_headers(request),
            )
