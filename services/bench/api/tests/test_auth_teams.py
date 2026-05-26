import os

import jwt
import pytest
from swecc_jwt import validate_member_token


@pytest.fixture(autouse=True)
def _jwt_secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-for-bench-auth")


def test_validate_member_token_accepts_server_shape():
    payload = {
        "user_id": 42,
        "username": "tester",
        "groups": ["is_authenticated"],
        "exp": 9999999999,
    }
    token = jwt.encode(payload, os.environ["JWT_SECRET"], algorithm="HS256")
    claims = validate_member_token(token, secret=os.environ["JWT_SECRET"])
    assert claims is not None
    assert claims["user_id"] == 42
    assert claims["username"] == "tester"


def test_join_code_alphabet():
    import secrets
    import string

    alphabet = string.ascii_uppercase + string.digits
    code = "".join(secrets.choice(alphabet) for _ in range(4))
    assert len(code) == 4
    assert code.isalnum()
