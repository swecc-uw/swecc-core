"""
Comprehensive tests for EchoHandler class.

Tests cover:
- Initialization
- Message echoing functionality
- Error handling
- Integration with EventEmitter
"""

import json
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.event_emitter import EventEmitter
from app.events import Event, EventType
from app.handlers.echo_handler import EchoHandler
from app.message import MessageType


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
def echo_handler(event_emitter):
    """Create an EchoHandler instance for testing."""
    return EchoHandler(event_emitter)


class TestEchoHandlerInitialization:
    """Test EchoHandler initialization."""

    def test_initialization_sets_service_name(self, event_emitter):
        # Arrange & Act
        handler = EchoHandler(event_emitter)

        # Assert
        assert handler.service_name == "Echo"
        assert handler.event_emitter is event_emitter

    def test_initialization_inherits_from_base_handler(self, event_emitter):
        # Arrange & Act
        handler = EchoHandler(event_emitter)

        # Assert
        assert hasattr(handler, "handle_connect")
        assert hasattr(handler, "handle_message")
        assert hasattr(handler, "handle_disconnect")
        assert hasattr(handler, "safe_send")

    def test_initialization_registers_event_listeners(self, event_emitter):
        # Arrange & Act
        handler = EchoHandler(event_emitter)

        # Assert
        assert EventType.MESSAGE in event_emitter.listeners
        assert handler.handle_message in event_emitter.listeners[EventType.MESSAGE]


class TestEchoHandlerMessageHandling:
    """Test message echoing functionality."""

    @pytest.mark.asyncio
    async def test_handle_message_echoes_content(self, echo_handler, mock_websocket):
        # Arrange
        event = Event(
            type=EventType.MESSAGE,
            user_id=123,
            username="testuser",
            data={"content": "Hello, Echo!"},
            websocket=mock_websocket,
        )

        # Act
        await echo_handler.handle_message(event)

        # Assert
        mock_websocket.send_text.assert_called_once()
        sent_data = json.loads(mock_websocket.send_text.call_args[0][0])
        assert sent_data["type"] == MessageType.ECHO
        assert sent_data["message"] == "Hello, Echo!"
        assert sent_data["user_id"] == 123
        assert sent_data["username"] == "testuser"

    @pytest.mark.asyncio
    async def test_handle_message_with_empty_content(self, echo_handler, mock_websocket):
        # Arrange
        event = Event(
            type=EventType.MESSAGE,
            user_id=456,
            username="alice",
            data={},  # No content field
            websocket=mock_websocket,
        )

        # Act
        await echo_handler.handle_message(event)

        # Assert
        mock_websocket.send_text.assert_called_once()
        sent_data = json.loads(mock_websocket.send_text.call_args[0][0])
        assert sent_data["message"] == ""  # Should default to empty string

    @pytest.mark.asyncio
    async def test_handle_message_with_special_characters(self, echo_handler, mock_websocket):
        # Arrange
        special_content = "Hello! 🎉 <script>alert('xss')</script> \n\t Special chars: @#$%"
        event = Event(
            type=EventType.MESSAGE,
            user_id=789,
            username="bob",
            data={"content": special_content},
            websocket=mock_websocket,
        )

        # Act
        await echo_handler.handle_message(event)

        # Assert
        mock_websocket.send_text.assert_called_once()
        sent_data = json.loads(mock_websocket.send_text.call_args[0][0])
        assert sent_data["message"] == special_content

    @pytest.mark.asyncio
    async def test_handle_message_logs_correctly(self, echo_handler, mock_websocket, caplog):
        # Arrange
        event = Event(
            type=EventType.MESSAGE,
            user_id=111,
            username="logger",
            data={"content": "Test message"},
            websocket=mock_websocket,
        )

        # Act
        with caplog.at_level(logging.INFO):
            await echo_handler.handle_message(event)

        # Assert
        assert any("Echo service" in record.message for record in caplog.records)
        assert any("logger" in record.message for record in caplog.records)
        assert any("111" in record.message for record in caplog.records)
        assert any("Test message" in record.message for record in caplog.records)


class TestEchoHandlerErrorHandling:
    """Test error handling in EchoHandler."""

    @pytest.mark.asyncio
    async def test_handle_message_handles_websocket_error(
        self, echo_handler, mock_websocket, caplog
    ):
        # Arrange
        event = Event(
            type=EventType.MESSAGE,
            user_id=222,
            username="erroruser",
            data={"content": "This will fail"},
            websocket=mock_websocket,
        )
        mock_websocket.send_text.side_effect = RuntimeError("WebSocket closed")

        # Act
        with caplog.at_level(logging.DEBUG):
            await echo_handler.handle_message(event)

        # Assert - should not raise, error is handled by safe_send
        assert mock_websocket.send_text.called

    @pytest.mark.asyncio
    async def test_handle_message_handles_missing_data(self, echo_handler, mock_websocket):
        # Arrange
        event = Event(
            type=EventType.MESSAGE,
            user_id=333,
            username="nodata",
            data=None,  # This could cause issues
            websocket=mock_websocket,
        )

        # Act & Assert - should handle gracefully
        try:
            await echo_handler.handle_message(event)
        except Exception as e:
            pytest.fail(f"Should handle missing data gracefully, but raised: {e}")

    @pytest.mark.asyncio
    async def test_handle_message_with_none_websocket(self, echo_handler, caplog):
        # Arrange
        event = Event(
            type=EventType.MESSAGE,
            user_id=444,
            username="exception",
            data={"content": "test"},
            websocket=None,  # This will cause an error in safe_send
        )

        # Act
        with caplog.at_level(logging.DEBUG):
            await echo_handler.handle_message(event)

        # Assert - should handle gracefully (safe_send will log debug message)
        # The handler itself doesn't crash
        assert any("exception" in record.message for record in caplog.records)


class TestEchoHandlerIntegration:
    """Integration tests for EchoHandler with EventEmitter."""

    @pytest.mark.asyncio
    async def test_echo_handler_receives_message_events(self, event_emitter, mock_websocket):
        # Arrange
        handler = EchoHandler(event_emitter)
        event = Event(
            type=EventType.MESSAGE,
            user_id=555,
            username="integration",
            data={"content": "Integration test"},
            websocket=mock_websocket,
        )

        # Act
        await event_emitter.emit(event)

        # Assert
        mock_websocket.send_text.assert_called_once()
        sent_data = json.loads(mock_websocket.send_text.call_args[0][0])
        assert sent_data["message"] == "Integration test"

    @pytest.mark.asyncio
    async def test_echo_handler_connection_event(self, event_emitter, mock_websocket):
        # Arrange
        handler = EchoHandler(event_emitter)
        event = Event(
            type=EventType.CONNECTION,
            user_id=666,
            username="connector",
            websocket=mock_websocket,
        )

        # Act
        await event_emitter.emit(event)

        # Assert - should send welcome message from base handler
        mock_websocket.send_text.assert_called_once()
        sent_data = json.loads(mock_websocket.send_text.call_args[0][0])
        assert sent_data["type"] == MessageType.SYSTEM
        assert "connector" in sent_data["message"]

    @pytest.mark.asyncio
    async def test_multiple_echo_messages(self, echo_handler, mock_websocket):
        # Arrange
        messages = ["First", "Second", "Third"]

        # Act
        for i, msg in enumerate(messages):
            event = Event(
                type=EventType.MESSAGE,
                user_id=i,
                username=f"user{i}",
                data={"content": msg},
                websocket=mock_websocket,
            )
            await echo_handler.handle_message(event)

        # Assert
        assert mock_websocket.send_text.call_count == 3
        for i, call in enumerate(mock_websocket.send_text.call_args_list):
            sent_data = json.loads(call[0][0])
            assert sent_data["message"] == messages[i]
