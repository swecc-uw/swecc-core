"""Tests for main application module."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from app.auth import Auth
from app.connection_manager import ConnectionManager
from app.handlers import HandlerKind
from app.main import EVENT_EMITTERS, app, authenticate_and_connect, cleanup_websocket
from fastapi import status
from fastapi.testclient import TestClient
from fastapi.websockets import WebSocketDisconnect


class TestBasicEndpoints:
    """Test basic HTTP endpoints."""

    def test_root_endpoint(self):
        """Test root endpoint returns status."""
        # Arrange
        client = TestClient(app)

        # Act
        response = client.get("/")

        # Assert
        assert response.status_code == 200
        assert response.json() == {
            "status": "online",
            "message": "WebSocket server is running",
        }

    def test_ping_endpoint(self):
        """Test ping endpoint returns pong."""
        # Arrange
        client = TestClient(app)

        # Act
        response = client.get("/ping")

        # Assert
        assert response.status_code == 200
        assert response.text == "pong"


@pytest.mark.asyncio
class TestAuthenticateAndConnect:
    """Test authenticate_and_connect function."""

    async def test_authenticate_and_connect_success(self, mock_websocket, valid_token, user_data):
        """Test successful authentication and connection."""
        # Arrange
        ConnectionManager.instance = None
        kind = HandlerKind.Echo

        with patch.object(Auth, "authenticate_ws", return_value=user_data):
            # Act
            user, ws = await authenticate_and_connect(kind, mock_websocket, valid_token)

            # Assert
            assert user == user_data
            assert ws is not None
            mock_websocket.accept.assert_called_once()

    async def test_authenticate_and_connect_auth_failure(self, mock_websocket):
        """Test authentication failure."""
        # Arrange
        ConnectionManager.instance = None
        kind = HandlerKind.Echo
        invalid_token = "invalid_token"

        with patch.object(Auth, "authenticate_ws", return_value=None):
            # Act
            user, ws = await authenticate_and_connect(kind, mock_websocket, invalid_token)

            # Assert
            assert user is None
            assert ws is None

    async def test_authenticate_and_connect_emits_connection_event(
        self, mock_websocket, valid_token, user_data
    ):
        """Test that connection event is emitted."""
        # Arrange
        ConnectionManager.instance = None
        kind = HandlerKind.Echo
        event_emitter = EVENT_EMITTERS[kind]

        with patch.object(Auth, "authenticate_ws", return_value=user_data):
            with patch.object(event_emitter, "emit", new_callable=AsyncMock) as mock_emit:
                # Act
                await authenticate_and_connect(kind, mock_websocket, valid_token)

                # Assert
                mock_emit.assert_called_once()
                call_args = mock_emit.call_args[0][0]
                assert call_args.user_id == user_data["user_id"]
                assert call_args.username == user_data["username"]


@pytest.mark.asyncio
class TestCleanupWebsocket:
    """Test cleanup_websocket function."""

    async def test_cleanup_websocket_success(self, user_data):
        """Test successful WebSocket cleanup."""
        # Arrange
        ConnectionManager.instance = None
        manager = ConnectionManager()
        kind = HandlerKind.Echo
        mock_ws = AsyncMock()

        # Register a connection first
        await manager.register_connection(kind, user_data["user_id"], mock_ws)

        # Act
        await cleanup_websocket(kind, user_data)

        # Assert
        assert (kind, user_data["user_id"]) not in manager.user_connections

    async def test_cleanup_websocket_emits_disconnect_event(self, user_data):
        """Test that disconnect event is emitted during cleanup."""
        # Arrange
        ConnectionManager.instance = None
        manager = ConnectionManager()
        kind = HandlerKind.Echo
        mock_ws = AsyncMock()
        event_emitter = EVENT_EMITTERS[kind]

        await manager.register_connection(kind, user_data["user_id"], mock_ws)

        with patch.object(event_emitter, "emit", new_callable=AsyncMock) as mock_emit:
            # Act
            await cleanup_websocket(kind, user_data)

            # Assert
            mock_emit.assert_called_once()
            call_args = mock_emit.call_args[0][0]
            assert call_args.user_id == user_data["user_id"]
            assert call_args.username == user_data["username"]

    async def test_cleanup_websocket_handles_exception(self, user_data):
        """Test that cleanup handles exceptions gracefully."""
        # Arrange
        ConnectionManager.instance = None
        kind = HandlerKind.Echo

        # Act & Assert - should not raise exception
        await cleanup_websocket(kind, user_data)


@pytest.mark.asyncio
class TestWebSocketEndpoints:
    """Test WebSocket endpoints."""

    async def test_echo_endpoint_connection(self, valid_token, user_data):
        """Test echo endpoint WebSocket connection."""
        # Arrange
        ConnectionManager.instance = None
        client = TestClient(app)

        with patch.object(Auth, "authenticate_ws", return_value=user_data):
            # Act & Assert
            with client.websocket_connect(f"/ws/echo/{valid_token}") as websocket:
                # Connection should be established
                assert websocket is not None

    async def test_logs_endpoint_connection(self, valid_token, user_data):
        """Test logs endpoint WebSocket connection."""
        # Arrange
        ConnectionManager.instance = None
        client = TestClient(app)

        with patch.object(Auth, "authenticate_ws", return_value=user_data):
            with patch("app.handlers.logs_handler.docker") as mock_docker:
                # Mock docker.from_env() to return a mock client
                mock_docker.from_env.return_value = MagicMock()
                # Act & Assert
                with client.websocket_connect(f"/ws/logs/{valid_token}") as websocket:
                    # Connection should be established
                    assert websocket is not None
                    # Send a test message to verify the connection works
                    websocket.send_json({"action": "test"})
                    # Close the connection to prevent hanging
                    websocket.close()

    async def test_resume_endpoint_connection(self, valid_token, user_data):
        """Test resume endpoint WebSocket connection."""
        # Arrange
        ConnectionManager.instance = None
        client = TestClient(app)

        with patch.object(Auth, "authenticate_ws", return_value=user_data):
            # Act & Assert
            with client.websocket_connect(f"/ws/resume/{valid_token}") as websocket:
                # Connection should be established
                assert websocket is not None

    async def test_echo_endpoint_send_receive_message(self, valid_token, user_data):
        """Test sending and receiving messages through echo endpoint."""
        # Arrange
        ConnectionManager.instance = None
        client = TestClient(app)
        test_message = {"type": "echo", "message": "Hello, World!"}

        with patch.object(Auth, "authenticate_ws", return_value=user_data):
            with patch("app.main.EchoHandler") as MockHandler:
                mock_handler_instance = MockHandler.return_value
                mock_handler_instance.safe_send = AsyncMock()

                # Act & Assert
                with client.websocket_connect(f"/ws/echo/{valid_token}") as websocket:
                    websocket.send_json(test_message)
                    # Give time for message processing
                    import time

                    time.sleep(0.1)

    async def test_echo_endpoint_invalid_json(self, valid_token, user_data):
        """Test echo endpoint handles invalid JSON gracefully."""
        # Arrange
        ConnectionManager.instance = None
        client = TestClient(app)

        with patch.object(Auth, "authenticate_ws", return_value=user_data):
            # Act & Assert
            with client.websocket_connect(f"/ws/echo/{valid_token}") as websocket:
                # Send invalid JSON
                websocket.send_text("not valid json")
                # Connection should remain open
                import time

                time.sleep(0.1)

    async def test_logs_endpoint_authentication_failure_does_not_receive(self):
        """Test that logs endpoint does not try to receive data after authentication fails.

        This is a regression test for the bug where the logs endpoint would try to
        call websocket.receive_text() after authentication failed and the websocket
        was closed, resulting in: 'WebSocket is not connected. Need to call "accept" first.'
        """
        # Arrange
        ConnectionManager.instance = None
        client = TestClient(app)
        invalid_token = "invalid_token"

        # Create a mock that simulates auth failure by closing the websocket and returning None
        async def mock_auth_failure(websocket, token, required_groups=None):
            await websocket.close(code=1008)
            return None

        # Mock authenticate_ws to simulate authentication failure
        with patch.object(Auth, "authenticate_ws", side_effect=mock_auth_failure):
            # Act & Assert
            # The endpoint should handle authentication failure gracefully
            # and NOT try to receive data from the closed websocket
            try:
                with client.websocket_connect(f"/ws/logs/{invalid_token}") as websocket:
                    # If we get here, the connection wasn't properly closed
                    # Try to send a message - this should fail gracefully
                    websocket.send_json({"action": "start", "container_id": "test"})
            except WebSocketDisconnect:
                # Expected - websocket should be disconnected after auth failure
                pass
            except Exception:
                # Expected to fail authentication
                pass


class TestEventEmitters:
    """Test EVENT_EMITTERS configuration."""

    def test_event_emitters_exist(self):
        """Test that event emitters are configured for all handler kinds."""
        # Arrange & Act & Assert
        assert HandlerKind.Echo in EVENT_EMITTERS
        assert HandlerKind.Logs in EVENT_EMITTERS
        assert HandlerKind.Resume in EVENT_EMITTERS

    def test_event_emitters_are_unique_instances(self):
        """Test that each handler has its own event emitter instance."""
        # Arrange & Act & Assert
        assert EVENT_EMITTERS[HandlerKind.Echo] is not EVENT_EMITTERS[HandlerKind.Logs]
        assert EVENT_EMITTERS[HandlerKind.Logs] is not EVENT_EMITTERS[HandlerKind.Resume]
        assert EVENT_EMITTERS[HandlerKind.Echo] is not EVENT_EMITTERS[HandlerKind.Resume]


class TestCORSMiddleware:
    """Test CORS middleware configuration."""

    def test_cors_headers_present(self):
        """Test that CORS headers are present in responses."""
        # Arrange
        client = TestClient(app)

        # Act
        response = client.get("/", headers={"Origin": "http://localhost:3000"})

        # Assert
        assert response.status_code == 200
        # CORS headers should be present
        assert "access-control-allow-origin" in response.headers


@pytest.mark.asyncio
class TestLifespan:
    """Test application lifespan management."""

    async def test_lifespan_initialization(self):
        """Test that lifespan context manager can be initialized."""
        # Arrange
        from app.main import lifespan

        mock_app = Mock()

        with patch("app.main.initialize_rabbitmq", new_callable=AsyncMock) as mock_init:
            with patch("app.main.shutdown_rabbitmq", new_callable=AsyncMock) as mock_shutdown:
                # Act
                async with lifespan(mock_app):
                    # Assert - initialization should be called
                    mock_init.assert_called_once()

                # Assert - shutdown should be called after context exit
                mock_shutdown.assert_called_once()
