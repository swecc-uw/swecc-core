"""Tests for authentication module."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from app.auth import Auth, TokenPayload
from app.config import settings
from fastapi import status
from jose import jwt


class TestTokenPayload:
    """Test TokenPayload model."""

    def test_token_payload_creation(self):
        """Test creating a TokenPayload with all fields."""
        # Arrange
        exp_time = datetime.now(timezone.utc) + timedelta(hours=1)

        # Act
        payload = TokenPayload(
            user_id=1, username="testuser", groups=["users", "admin"], exp=exp_time
        )

        # Assert
        assert payload.user_id == 1
        assert payload.username == "testuser"
        assert payload.groups == ["users", "admin"]
        assert payload.exp == exp_time

    def test_token_payload_default_groups(self):
        """Test that groups defaults to empty list."""
        # Arrange
        exp_time = datetime.now(timezone.utc) + timedelta(hours=1)

        # Act
        payload = TokenPayload(user_id=2, username="user2", exp=exp_time)

        # Assert
        assert payload.groups == []


@pytest.mark.asyncio
class TestAuth:
    """Test Auth class."""

    async def test_validate_token_success(self, valid_token):
        """Test successful token validation."""
        # Arrange & Act
        result = await Auth.validate_token(valid_token)

        # Assert
        assert result is not None
        assert result["user_id"] == 1
        assert result["username"] == "testuser"
        assert result["groups"] == ["users"]

    async def test_validate_token_expired(self, expired_token):
        """Test validation of expired token."""
        # Arrange & Act
        result = await Auth.validate_token(expired_token)

        # Assert
        assert result is None

    async def test_validate_token_invalid_signature(self):
        """Test validation of token with invalid signature."""
        # Arrange
        payload = {
            "user_id": 1,
            "username": "testuser",
            "groups": ["users"],
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        # Create token with wrong secret
        invalid_token = jwt.encode(payload, "wrong_secret", algorithm=settings.jwt_algorithm)

        # Act
        result = await Auth.validate_token(invalid_token)

        # Assert
        assert result is None

    async def test_validate_token_malformed(self):
        """Test validation of malformed token."""
        # Arrange
        malformed_token = "not.a.valid.jwt.token"

        # Act
        result = await Auth.validate_token(malformed_token)

        # Assert
        assert result is None

    async def test_validate_token_missing_fields(self):
        """Test validation of token with missing required fields."""
        # Arrange
        payload = {
            "user_id": 1,
            # Missing username and exp
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

        # Act
        result = await Auth.validate_token(token)

        # Assert
        assert result is None

    async def test_authenticate_ws_success(self, mock_websocket, valid_token):
        """Test successful WebSocket authentication."""
        # Arrange & Act
        result = await Auth.authenticate_ws(mock_websocket, valid_token)

        # Assert
        assert result is not None
        assert result["user_id"] == 1
        assert result["username"] == "testuser"
        mock_websocket.close.assert_not_called()

    async def test_authenticate_ws_invalid_token(self, mock_websocket):
        """Test WebSocket authentication with invalid token."""
        # Arrange
        invalid_token = "invalid.token.here"

        # Act
        result = await Auth.authenticate_ws(mock_websocket, invalid_token)

        # Assert
        assert result is None
        mock_websocket.close.assert_called_once_with(code=status.WS_1008_POLICY_VIOLATION)

    async def test_authenticate_ws_expired_token(self, mock_websocket, expired_token):
        """Test WebSocket authentication with expired token."""
        # Arrange & Act
        result = await Auth.authenticate_ws(mock_websocket, expired_token)

        # Assert
        assert result is None
        mock_websocket.close.assert_called_once_with(code=status.WS_1008_POLICY_VIOLATION)

    async def test_authenticate_ws_with_required_groups_success(self, mock_websocket, admin_token):
        """Test WebSocket authentication with required groups - success."""
        # Arrange & Act
        result = await Auth.authenticate_ws(mock_websocket, admin_token, required_groups=["admin"])

        # Assert
        assert result is not None
        assert "admin" in result["groups"]
        mock_websocket.close.assert_not_called()

    async def test_authenticate_ws_with_required_groups_failure(self, mock_websocket, valid_token):
        """Test WebSocket authentication with required groups - failure."""
        # Arrange & Act
        result = await Auth.authenticate_ws(mock_websocket, valid_token, required_groups=["admin"])

        # Assert
        assert result is None
        mock_websocket.close.assert_called_once_with(code=status.WS_1008_POLICY_VIOLATION)

    async def test_authenticate_ws_with_multiple_required_groups(self, mock_websocket, admin_token):
        """Test WebSocket authentication with multiple required groups."""
        # Arrange & Act
        result = await Auth.authenticate_ws(
            mock_websocket, admin_token, required_groups=["admin", "superuser"]
        )

        # Assert
        assert result is not None  # User has 'admin' which is in required_groups
        mock_websocket.close.assert_not_called()

    async def test_authenticate_ws_no_required_groups(self, mock_websocket, valid_token):
        """Test WebSocket authentication without required groups."""
        # Arrange & Act
        result = await Auth.authenticate_ws(mock_websocket, valid_token, required_groups=None)

        # Assert
        assert result is not None
        mock_websocket.close.assert_not_called()
