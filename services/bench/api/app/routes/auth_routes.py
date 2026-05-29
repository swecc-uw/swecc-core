from __future__ import annotations

import uuid
from datetime import timedelta

from app.auth.guest_tokens import encode_guest_token
from bench_common.config import settings
from django.utils import timezone
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from bench.models import BenchGuestSession

router = APIRouter(prefix="/v1/auth", tags=["auth"])

GUEST_TTL_DAYS = 7


def _cookie_path() -> str:
    prefix = (settings.gateway_prefix or "").rstrip("/")
    return f"{prefix}/" if prefix else "/"


class GuestResponse(BaseModel):
    guest_token: str
    expires_at: str


@router.post("/guest", response_model=GuestResponse)
async def create_guest(response: Response, request: Request) -> GuestResponse:
    session_id = uuid.uuid4()
    expires = timezone.now() + timedelta(days=GUEST_TTL_DAYS)
    await BenchGuestSession.objects.acreate(id=session_id, expires_at=expires)
    token = encode_guest_token(str(session_id), ttl_seconds=GUEST_TTL_DAYS * 86400)
    cookie_path = _cookie_path()
    response.set_cookie(
        key="bench_guest",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=GUEST_TTL_DAYS * 86400,
        path=cookie_path,
        secure=request.url.scheme == "https",
    )
    return GuestResponse(guest_token=token, expires_at=expires.isoformat())


@router.post("/guest/logout")
async def guest_logout(response: Response) -> dict:
    response.delete_cookie("bench_guest", path=_cookie_path())
    return {"detail": "ok"}
