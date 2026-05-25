from __future__ import annotations

import os
import uuid

from app.auth.guest_tokens import decode_guest_token
from app.auth.principal import Anonymous, Guest, Member
from bench.models import BenchGuestSession
from django.utils import timezone
from fastapi import Request
from swecc_jwt import validate_member_token


def auth_disabled() -> bool:
    return os.environ.get("BENCH_AUTH_DISABLED", "").lower() in ("1", "true", "yes")


async def _valid_guest_session(token: str) -> str | None:
    guest_id = decode_guest_token(token)
    if not guest_id:
        return None
    try:
        sid = uuid.UUID(guest_id)
    except ValueError:
        return None
    row = await BenchGuestSession.objects.filter(id=sid, expires_at__gt=timezone.now()).afirst()
    if row is None:
        return None
    return guest_id


async def resolve_principal(request: Request) -> Anonymous | Guest | Member:
    if auth_disabled():
        return Member(user_id=0, username="local", groups=("is_authenticated",))

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        member = validate_member_token(token, secret=os.environ["JWT_SECRET"])
        if member:
            return Member(
                user_id=member["user_id"],
                username=member["username"],
                groups=tuple(member.get("groups") or []),
            )
        guest_id = await _valid_guest_session(token)
        if guest_id:
            return Guest(session_id=guest_id)

    cookie = request.cookies.get("bench_guest")
    if cookie:
        guest_id = await _valid_guest_session(cookie)
        if guest_id:
            return Guest(session_id=guest_id)

    return Anonymous()
