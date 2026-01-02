"""Tests for connection manager module."""

from unittest.mock import AsyncMock

import pytest
from app.connection_manager import ConnectionManager
from app.handlers import HandlerKind


@pytest.mark.asyncio
class TestConnectionManager:
    """Test ConnectionManager class."""

    async def test_connection_manager_singleton(self):
        """Test that ConnectionManager is a singleton."""
        # Arrange
        ConnectionManager.instance = None

        # Act
        manager1 = ConnectionManager()
        manager2 = ConnectionManager()

        # Assert
        assert manager1 is manager2

    async def test_connection_manager_initialization(self, connection_manager):
        """Test ConnectionManager initializes with empty connections."""
        # Arrange & Act & Assert
        assert connection_manager.closing_connections == set()
        assert connection_manager.user_connections == {}
        assert connection_manager.ws_connections == {}
        assert connection_manager.initialized is True

    async def test_register_connection_new_user(self, connection_manager, mock_websocket):
        """Test registering a new WebSocket connection."""
        # Arrange
        user_id = 1
        kind = HandlerKind.Echo

        # Act
        result = await connection_manager.register_connection(kind, user_id, mock_websocket)

        # Assert
        assert result == mock_websocket
        mock_websocket.accept.assert_called_once()
        assert (kind, user_id) in connection_manager.user_connections
        assert id(mock_websocket) in connection_manager.ws_connections

    async def test_register_connection_existing_user(self, connection_manager, mock_websocket):
        """Test registering connection for already connected user."""
        # Arrange
        user_id = 1
        kind = HandlerKind.Echo
        await connection_manager.register_connection(kind, user_id, mock_websocket)
        new_websocket = AsyncMock()

        # Act
        result = await connection_manager.register_connection(kind, user_id, new_websocket)

        # Assert
        assert result == mock_websocket  # Returns existing connection
        new_websocket.accept.assert_not_called()

    async def test_register_connection_same_user_different_handlers(
        self, connection_manager, mock_websocket
    ):
        """Test registering same user for different handler types."""
        # Arrange
        user_id = 1
        echo_ws = mock_websocket
        logs_ws = AsyncMock()

        # Act
        await connection_manager.register_connection(HandlerKind.Echo, user_id, echo_ws)
        await connection_manager.register_connection(HandlerKind.Logs, user_id, logs_ws)

        # Assert
        assert (HandlerKind.Echo, user_id) in connection_manager.user_connections
        assert (HandlerKind.Logs, user_id) in connection_manager.user_connections
        assert len(connection_manager.ws_connections) == 2

    async def test_get_websocket_connection_exists(self, connection_manager, mock_websocket):
        """Test getting an existing WebSocket connection."""
        # Arrange
        user_id = 1
        kind = HandlerKind.Echo
        await connection_manager.register_connection(kind, user_id, mock_websocket)

        # Act
        result = connection_manager.get_websocket_connection(kind, user_id)

        # Assert
        assert result == mock_websocket

    async def test_get_websocket_connection_not_exists(self, connection_manager):
        """Test getting a non-existent WebSocket connection."""
        # Arrange
        user_id = 999
        kind = HandlerKind.Echo

        # Act
        result = connection_manager.get_websocket_connection(kind, user_id)

        # Assert
        assert result is None

    async def test_get_websocket_connection_closing(self, connection_manager, mock_websocket):
        """Test getting a WebSocket connection that is closing."""
        # Arrange
        user_id = 1
        kind = HandlerKind.Echo
        await connection_manager.register_connection(kind, user_id, mock_websocket)
        connection_manager.closing_connections.add(id(mock_websocket))

        # Act
        result = connection_manager.get_websocket_connection(kind, user_id)

        # Assert
        assert result is None

    async def test_is_connection_closing_true(self, connection_manager, mock_websocket):
        """Test checking if connection is closing - true case."""
        # Arrange
        connection_manager.closing_connections.add(id(mock_websocket))

        # Act
        result = connection_manager.is_connection_closing(mock_websocket)

        # Assert
        assert result is True

    async def test_is_connection_closing_false(self, connection_manager, mock_websocket):
        """Test checking if connection is closing - false case."""
        # Arrange & Act
        result = connection_manager.is_connection_closing(mock_websocket)

        # Assert
        assert result is False

    async def test_disconnect_existing_connection(self, connection_manager, mock_websocket):
        """Test disconnecting an existing connection."""
        # Arrange
        user_id = 1
        kind = HandlerKind.Echo
        await connection_manager.register_connection(kind, user_id, mock_websocket)

        # Act
        connection_manager.disconnect(kind, user_id)

        # Assert
        assert (kind, user_id) not in connection_manager.user_connections
        assert id(mock_websocket) not in connection_manager.ws_connections
        assert id(mock_websocket) in connection_manager.closing_connections

    async def test_disconnect_nonexistent_connection(self, connection_manager):
        """Test disconnecting a non-existent connection."""
        # Arrange
        user_id = 999
        kind = HandlerKind.Echo

        # Act & Assert - should not raise exception
        connection_manager.disconnect(kind, user_id)

    async def test_get_active_user_ids_empty(self, connection_manager):
        """Test getting active user IDs when no connections."""
        # Arrange & Act
        active_users = connection_manager.get_active_user_ids()

        # Assert
        assert active_users == set()

    async def test_get_active_user_ids_with_connections(self, connection_manager):
        """Test getting active user IDs with multiple connections."""
        # Arrange
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        ws3 = AsyncMock()
        await connection_manager.register_connection(HandlerKind.Echo, 1, ws1)
        await connection_manager.register_connection(HandlerKind.Logs, 2, ws2)
        await connection_manager.register_connection(HandlerKind.Echo, 3, ws3)

        # Act
        active_users = connection_manager.get_active_user_ids()

        # Assert
        assert active_users == {1, 2, 3}

    async def test_get_active_user_ids_same_user_multiple_handlers(self, connection_manager):
        """Test getting active user IDs when same user has multiple handlers."""
        # Arrange
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        await connection_manager.register_connection(HandlerKind.Echo, 1, ws1)
        await connection_manager.register_connection(HandlerKind.Logs, 1, ws2)

        # Act
        active_users = connection_manager.get_active_user_ids()

        # Assert
        assert active_users == {1}  # Same user, counted once

    async def test_multiple_disconnects_same_connection(self, connection_manager, mock_websocket):
        """Test multiple disconnects of the same connection."""
        # Arrange
        user_id = 1
        kind = HandlerKind.Echo
        await connection_manager.register_connection(kind, user_id, mock_websocket)

        # Act
        connection_manager.disconnect(kind, user_id)
        connection_manager.disconnect(kind, user_id)  # Second disconnect

        # Assert - should handle gracefully
        assert (kind, user_id) not in connection_manager.user_connections
