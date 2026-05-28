"""Validate HS256 JWTs issued by swecc-server CreateTokenView."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from jose import JWTError, jwt
from pydantic import BaseModel, ValidationError

# Token types we know about that are NOT member tokens. Listed explicitly
# because swecc-server's CreateTokenView currently emits member tokens with
# no `type` field at all (legacy), so we can't positively require type="member"
# without a coordinated server-side change. Until then: reject any token whose
# `type` claim names something we know to be a different audience.
_NON_MEMBER_TOKEN_TYPES = frozenset({"bench_guest"})


class MemberTokenPayload(BaseModel):
    user_id: int
    username: str
    groups: list[str] = []
    exp: datetime | int | float


def validate_member_token(
    token: str,
    *,
    secret: str,
    algorithm: str = "HS256",
) -> dict[str, Any] | None:
    """Decode and validate a member JWT. Returns claims dict or None if invalid/expired.

    Rejects tokens whose ``type`` claim identifies a non-member audience
    (e.g. ``bench_guest``).  Without this check, any token signed with the
    shared HS256 secret that happens to also carry ``user_id``/``username``/
    ``exp`` claims would authenticate as a member.
    """
    try:
        payload = jwt.decode(token, secret, algorithms=[algorithm])
        token_type = payload.get("type")
        if token_type in _NON_MEMBER_TOKEN_TYPES:
            return None
        token_data = MemberTokenPayload(**payload)
        exp = token_data.exp
        if isinstance(exp, (int, float)):
            exp_dt = datetime.fromtimestamp(exp, tz=timezone.utc)
        else:
            exp_dt = exp if exp.tzinfo else exp.replace(tzinfo=timezone.utc)
        if exp_dt < datetime.now(timezone.utc):
            return None
        return {
            "user_id": token_data.user_id,
            "username": token_data.username,
            "groups": token_data.groups,
        }
    except (JWTError, ValidationError):
        return None
