import os
from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt
from swecc_jwt import MemberTokenPayload, validate_member_token


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "unit-test-secret")


def test_validate_member_token_round_trip():
    exp = datetime.now(timezone.utc) + timedelta(hours=1)
    payload = {
        "user_id": 7,
        "username": "alice",
        "groups": ["is_authenticated"],
        "exp": int(exp.timestamp()),
    }
    token = jwt.encode(payload, os.environ["JWT_SECRET"], algorithm="HS256")
    claims = validate_member_token(token, secret=os.environ["JWT_SECRET"])
    assert claims is not None
    assert claims["user_id"] == 7
    assert claims["username"] == "alice"
    assert "is_authenticated" in claims["groups"]


def test_validate_member_token_rejects_expired():
    exp = datetime.now(timezone.utc) - timedelta(hours=1)
    payload = {
        "user_id": 1,
        "username": "bob",
        "groups": [],
        "exp": int(exp.timestamp()),
    }
    token = jwt.encode(payload, os.environ["JWT_SECRET"], algorithm="HS256")
    assert validate_member_token(token, secret=os.environ["JWT_SECRET"]) is None


def test_member_token_payload_model():
    data = MemberTokenPayload(
        user_id=3,
        username="c",
        groups=["g"],
        exp=9999999999,
    )
    assert data.user_id == 3
