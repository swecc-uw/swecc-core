from __future__ import annotations

from fastapi import HTTPException, Request

from app.auth.principal import Anonymous, Guest, Member, Principal
from app.auth.resolve import resolve_principal


async def get_optional_principal(request: Request) -> Principal:
    if hasattr(request.state, "principal"):
        return request.state.principal
    return await resolve_principal(request)


async def get_principal(request: Request) -> Guest | Member:
    p = await get_optional_principal(request)
    if isinstance(p, Anonymous):
        raise HTTPException(status_code=401, detail="Authentication required")
    return p


async def require_member(request: Request) -> Member:
    from app.auth.resolve import auth_disabled

    if auth_disabled():
        return Member(user_id=0, username="local", groups=("is_authenticated",))
    p = await get_principal(request)
    if not isinstance(p, Member):
        raise HTTPException(status_code=403, detail="SWECC member account required")
    return p
