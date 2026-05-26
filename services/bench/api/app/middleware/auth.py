from django.db import close_old_connections
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.auth.resolve import resolve_principal


class PrincipalMiddleware(BaseHTTPMiddleware):
    """
    Resolve bench principal per request and refresh Django DB connections.

    FastAPI runs sync ORM work via threadpool; without close_old_connections(),
    Postgres connections opened in worker threads can go stale and raise
    OperationalError (\"the connection is closed\") — browsers then show
    \"Failed to fetch\" when 500 responses omit CORS headers.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        close_old_connections()
        request.state.principal = await resolve_principal(request)
        return await call_next(request)
