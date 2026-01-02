"""Pytest fixtures for sockets service tests."""

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from types import ModuleType
from typing import AsyncGenerator, Dict
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

# Mock docker module before any app imports that use it
# Create a proper mock module structure for docker and docker.errors
mock_docker = MagicMock()
mock_docker.from_env.return_value = MagicMock()

# Create docker.errors as a proper module with exception classes
mock_docker_errors = ModuleType("docker.errors")
mock_docker_errors.NotFound = type("NotFound", (Exception,), {})
mock_docker_errors.APIError = type("APIError", (Exception,), {})
mock_docker.errors = mock_docker_errors

sys.modules["docker"] = mock_docker
sys.modules["docker.errors"] = mock_docker_errors

from app.config import settings
from app.connection_manager import ConnectionManager
from app.event_emitter import EventEmitter
from app.events import Event, EventType
from app.handlers import HandlerKind
from fastapi import WebSocket
from jose import jwt


@pytest.fixture
def event_loop():
    """Create an instance of the default event loop for each test case."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_websocket():
    """Create a mock WebSocket connection."""
    websocket = AsyncMock(spec=WebSocket)
    websocket.accept = AsyncMock()
    websocket.send_text = AsyncMock()
    websocket.send_json = AsyncMock()
    websocket.receive_text = AsyncMock()
    websocket.receive_json = AsyncMock()
    websocket.close = AsyncMock()
    return websocket


@pytest.fixture
def valid_token():
    """Generate a valid JWT token for testing."""
    payload = {
        "user_id": 1,
        "username": "testuser",
        "groups": ["users"],
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token


@pytest.fixture
def expired_token():
    """Generate an expired JWT token for testing."""
    payload = {
        "user_id": 1,
        "username": "testuser",
        "groups": ["users"],
        "exp": datetime.now(timezone.utc) - timedelta(hours=1),
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token


@pytest.fixture
def admin_token():
    """Generate a valid JWT token with admin privileges."""
    payload = {
        "user_id": 2,
        "username": "adminuser",
        "groups": ["admin", "users"],
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token


@pytest.fixture
def user_data():
    """Sample user data."""
    return {"user_id": 1, "username": "testuser", "groups": ["users"]}


@pytest.fixture
def admin_user_data():
    """Sample admin user data."""
    return {"user_id": 2, "username": "adminuser", "groups": ["admin", "users"]}


@pytest.fixture
def event_emitter():
    """Create a fresh EventEmitter instance."""
    return EventEmitter()


@pytest.fixture
def connection_manager():
    """Create a fresh ConnectionManager instance."""
    # Save the old instance
    old_instance = ConnectionManager.instance
    # Reset the singleton instance completely
    ConnectionManager.instance = None
    # Create new instance - this will set itself as the new singleton
    manager = ConnectionManager()
    yield manager
    # Restore the old instance after test
    ConnectionManager.instance = old_instance


@pytest.fixture
def sample_event(user_data, mock_websocket):
    """Create a sample event for testing."""
    return Event(
        type=EventType.MESSAGE,
        user_id=user_data["user_id"],
        username=user_data["username"],
        data={"message": "test message"},
        websocket=mock_websocket,
    )


@pytest.fixture
def connection_event(user_data, mock_websocket):
    """Create a connection event for testing."""
    return Event(
        type=EventType.CONNECTION,
        user_id=user_data["user_id"],
        username=user_data["username"],
        websocket=mock_websocket,
    )


@pytest.fixture
def disconnect_event(user_data):
    """Create a disconnect event for testing."""
    return Event(
        type=EventType.DISCONNECT,
        user_id=user_data["user_id"],
        username=user_data["username"],
    )
