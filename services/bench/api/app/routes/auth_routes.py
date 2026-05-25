from __future__ import annotations

import uuid
from datetime import timedelta

from app.auth.guest_tokens import encode_guest_token
from bench.models import BenchGuestSession
from django.utils import timezone
from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

router = APIRouter(prefix="/v1/auth", tags=["auth"])

GUEST_TTL_DAYS = 7


class GuestResponse(BaseModel):
    guest_token: str
    expires_at: str


@router.post("/guest", response_model=GuestResponse)
async def create_guest(response: Response) -> GuestResponse:
    session_id = uuid.uuid4()
    expires = timezone.now() + timedelta(days=GUEST_TTL_DAYS)
    await BenchGuestSession.objects.acreate(id=session_id, expires_at=expires)
    token = encode_guest_token(str(session_id), ttl_seconds=GUEST_TTL_DAYS * 86400)
    response.set_cookie(
        key="bench_guest",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=GUEST_TTL_DAYS * 86400,
        path="/bench/",
    )
    return GuestResponse(guest_token=token, expires_at=expires.isoformat())


@router.post("/guest/logout")
async def guest_logout(response: Response) -> dict:
    response.delete_cookie("bench_guest", path="/bench/")
    return {"detail": "ok"}


