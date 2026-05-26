from __future__ import annotations

import os
import time
from typing import Any

from jose import JWTError, jwt


def _secret() -> str:
    return os.environ["JWT_SECRET"]


def encode_guest_token(session_id: str, *, ttl_seconds: int = 86400 * 7) -> str:
    payload = {
        "type": "bench_guest",
        "guest_session_id": str(session_id),
        "exp": int(time.time()) + ttl_seconds,
    }
    return jwt.encode(payload, _secret(), algorithm="HS256")


def decode_guest_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, _secret(), algorithms=["HS256"])
        if payload.get("type") != "bench_guest":
            return None
        sid = payload.get("guest_session_id")
        return str(sid) if sid else None
    except JWTError:
        return None
