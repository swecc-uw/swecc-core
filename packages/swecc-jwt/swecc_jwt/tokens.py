"""Validate HS256 JWTs issued by swecc-server CreateTokenView."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from jose import JWTError, jwt
from pydantic import BaseModel, ValidationError


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
    """Decode and validate a member JWT. Returns claims dict or None if invalid/expired."""
    try:
        payload = jwt.decode(token, secret, algorithms=[algorithm])
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
