"""
Comprehensive tests for BaseHandler class.

Tests cover:
- Initialization and setup
- Event handler registration
- Connection handling
- Message handling
- Disconnection handling
- Safe send functionality
- Error handling
"""

import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.event_emitter import EventEmitter
from app.events import Event, EventType
from app.handlers.base_handler import BaseHandler
from app.message import Message, MessageType


@pytest.fixture
def event_emitter():
    """Create a fresh EventEmitter instance for each test."""
    return EventEmitter()


@pytest.fixture
def mock_websocket():
    """Create a mock WebSocket with async send_text method."""
    websocket = MagicMock()
    websocket.send_text = AsyncMock()
    return websocket


@pytest.fixture
def base_handler(event_emitter):
    """Create a BaseHandler instance for testing."""
    return BaseHandler(event_emitter, "Test")


class TestBaseHandlerInitialization:
    """Test BaseHandler initialization and setup."""

    def test_initialization_sets_attributes(self, event_emitter):
        # Arrange & Act
        handler = BaseHandler(event_emitter, "TestService")

        # Assert
        assert handler.event_emitter is event_emitter
        assert handler.service_name == "TestService"
        assert isinstance(handler.logger, logging.Logger)
        assert handler.logger.name == "TestServiceHandler"

    def test_initialization_registers_event_listeners(self, event_emitter):
        # Arrange & Act
        handler = BaseHandler(event_emitter, "Test")

        # Assert
        assert EventType.CONNECTION in event_emitter.listeners
        assert EventType.MESSAGE in event_emitter.listeners
        assert EventType.DISCONNECT in event_emitter.listeners
        assert handler.handle_connect in event_emitter.listeners[EventType.CONNECTION]
        assert handler.handle_message in event_emitter.listeners[EventType.MESSAGE]
        assert handler.handle_disconnect in event_emitter.listeners[EventType.DISCONNECT]


class TestBaseHandlerConnect:
    """Test connection handling."""

    @pytest.mark.asyncio
    async def test_handle_connect_sends_welcome_message(self, base_handler, mock_websocket):
        # Arrange
        event = Event(
            type=EventType.CONNECTION,
            user_id=123,
            username="testuser",
            websocket=mock_websocket,
        )

        # Act
        await base_handler.handle_connect(event)

        # Assert
        mock_websocket.send_text.assert_called_once()
        sent_data = json.loads(mock_websocket.send_text.call_args[0][0])
        assert sent_data["type"] == MessageType.SYSTEM
        assert "testuser" in sent_data["message"]
        assert "Test service" in sent_data["message"]

    @pytest.mark.asyncio
    async def test_handle_connect_logs_connection(self, base_handler, mock_websocket, caplog):
        # Arrange
        event = Event(
            type=EventType.CONNECTION,
            user_id=456,
            username="alice",
            websocket=mock_websocket,
        )

        # Act
        with caplog.at_level(logging.INFO):
            await base_handler.handle_connect(event)

        # Assert
        assert any("alice" in record.message for record in caplog.records)
        assert any("456" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_handle_connect_handles_send_error(self, base_handler, mock_websocket, caplog):
        # Arrange
        event = Event(
            type=EventType.CONNECTION,
            user_id=789,
            username="bob",
            websocket=mock_websocket,
        )
        mock_websocket.send_text.side_effect = Exception("Connection closed")

        # Act
        with caplog.at_level(logging.DEBUG):
            await base_handler.handle_connect(event)

        # Assert - should not raise, just log
        assert any("Could not send message" in record.message for record in caplog.records)


class TestBaseHandlerMessage:
    """Test message handling."""

    @pytest.mark.asyncio
    async def test_handle_message_logs_message(self, base_handler, caplog):
        # Arrange
        event = Event(
            type=EventType.MESSAGE,
            user_id=123,
            username="testuser",
            data={"content": "Hello, world!"},
        )

        # Act
        with caplog.at_level(logging.INFO):
            await base_handler.handle_message(event)

        # Assert
        assert any("testuser" in record.message for record in caplog.records)
        assert any("123" in record.message for record in caplog.records)


class TestBaseHandlerDisconnect:
    """Test disconnection handling."""

    @pytest.mark.asyncio
    async def test_handle_disconnect_logs_disconnection(self, base_handler, caplog):
        # Arrange
        event = Event(
            type=EventType.DISCONNECT,
            user_id=123,
            username="testuser",
        )

        # Act
        with caplog.at_level(logging.INFO):
            await base_handler.handle_disconnect(event)

        # Assert
        assert any("testuser" in record.message for record in caplog.records)
        assert any("123" in record.message for record in caplog.records)
        assert any("disconnected" in record.message.lower() for record in caplog.records)

    @pytest.mark.asyncio
    async def test_handle_disconnect_with_none_user_id(self, base_handler, caplog):
        # Arrange
        event = Event(
            type=EventType.DISCONNECT,
            user_id=None,
            username="testuser",
        )

        # Act
        with caplog.at_level(logging.INFO):
            await base_handler.handle_disconnect(event)

        # Assert - should handle gracefully and log with None
        assert any("testuser" in record.message for record in caplog.records)
        assert any("disconnected" in record.message.lower() for record in caplog.records)


class TestBaseHandlerSafeSend:
    """Test safe send functionality."""

    @pytest.mark.asyncio
    async def test_safe_send_sends_json_data(self, base_handler, mock_websocket):
        # Arrange
        data = {"type": "test", "message": "Hello"}

        # Act
        await base_handler.safe_send(mock_websocket, data)

        # Assert
        mock_websocket.send_text.assert_called_once()
        sent_json = mock_websocket.send_text.call_args[0][0]
        assert json.loads(sent_json) == data

    @pytest.mark.asyncio
    async def test_safe_send_handles_websocket_error(self, base_handler, mock_websocket, caplog):
        # Arrange
        data = {"type": "test", "message": "Hello"}
        mock_websocket.send_text.side_effect = RuntimeError("WebSocket closed")

        # Act
        with caplog.at_level(logging.DEBUG):
            await base_handler.safe_send(mock_websocket, data)

        # Assert - should not raise, just log
        assert any("Could not send message" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_safe_send_handles_serialization_error(
        self, base_handler, mock_websocket, caplog
    ):
        # Arrange
        # Create non-serializable data
        class NonSerializable:
            pass

        data = {"obj": NonSerializable()}

        # Act
        with caplog.at_level(logging.DEBUG):
            await base_handler.safe_send(mock_websocket, data)

        # Assert - should not raise, just log
        assert any("Could not send message" in record.message for record in caplog.records)


class TestBaseHandlerIntegration:
    """Integration tests for BaseHandler with EventEmitter."""

    @pytest.mark.asyncio
    async def test_event_emitter_triggers_handlers(self, event_emitter, mock_websocket):
        # Arrange
        handler = BaseHandler(event_emitter, "Integration")
        event = Event(
            type=EventType.CONNECTION,
            user_id=999,
            username="integrationuser",
            websocket=mock_websocket,
        )

        # Act
        await event_emitter.emit(event)

        # Assert
        mock_websocket.send_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_multiple_handlers_receive_events(self, event_emitter, mock_websocket):
        # Arrange
        handler1 = BaseHandler(event_emitter, "Handler1")
        handler2 = BaseHandler(event_emitter, "Handler2")
        event = Event(
            type=EventType.CONNECTION,
            user_id=111,
            username="multiuser",
            websocket=mock_websocket,
        )

        # Act
        await event_emitter.emit(event)

        # Assert
        # Both handlers should send a message
        assert mock_websocket.send_text.call_count == 2
