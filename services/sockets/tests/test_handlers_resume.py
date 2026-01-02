"""
Comprehensive tests for ResumeHandler class.

Tests cover:
- Initialization
- Inheritance from BaseHandler
- Event handling (connection, message, disconnect)
- Integration with EventEmitter
"""

import json
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.event_emitter import EventEmitter
from app.events import Event, EventType
from app.handlers.resume_handler import ResumeHandler
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
def resume_handler(event_emitter):
    """Create a ResumeHandler instance for testing."""
    return ResumeHandler(event_emitter)


class TestResumeHandlerInitialization:
    """Test ResumeHandler initialization."""

    def test_initialization_sets_service_name(self, event_emitter):
        # Arrange & Act
        handler = ResumeHandler(event_emitter)

        # Assert
        assert handler.service_name == "Resume"
        assert handler.event_emitter is event_emitter

    def test_initialization_inherits_from_base_handler(self, event_emitter):
        # Arrange & Act
        handler = ResumeHandler(event_emitter)

        # Assert
        assert hasattr(handler, "handle_connect")
        assert hasattr(handler, "handle_message")
        assert hasattr(handler, "handle_disconnect")
        assert hasattr(handler, "safe_send")
        assert hasattr(handler, "logger")

    def test_initialization_registers_event_listeners(self, event_emitter):
        # Arrange & Act
        handler = ResumeHandler(event_emitter)

        # Assert
        assert EventType.CONNECTION in event_emitter.listeners
        assert EventType.MESSAGE in event_emitter.listeners
        assert EventType.DISCONNECT in event_emitter.listeners
        assert handler.handle_connect in event_emitter.listeners[EventType.CONNECTION]
        assert handler.handle_message in event_emitter.listeners[EventType.MESSAGE]
        assert handler.handle_disconnect in event_emitter.listeners[EventType.DISCONNECT]

    def test_logger_name_is_correct(self, event_emitter):
        # Arrange & Act
        handler = ResumeHandler(event_emitter)

        # Assert
        assert handler.logger.name == "ResumeHandler"


class TestResumeHandlerConnectionHandling:
    """Test connection handling for ResumeHandler."""

    @pytest.mark.asyncio
    async def test_handle_connect_sends_welcome_message(self, resume_handler, mock_websocket):
        # Arrange
        event = Event(
            type=EventType.CONNECTION,
            user_id=123,
            username="resumeuser",
            websocket=mock_websocket,
        )

        # Act
        await resume_handler.handle_connect(event)

        # Assert
        mock_websocket.send_text.assert_called_once()
        sent_data = json.loads(mock_websocket.send_text.call_args[0][0])
        assert sent_data["type"] == MessageType.SYSTEM
        assert "Resume service" in sent_data["message"]
        assert "resumeuser" in sent_data["message"]

    @pytest.mark.asyncio
    async def test_handle_connect_logs_connection(self, resume_handler, mock_websocket, caplog):
        # Arrange
        event = Event(
            type=EventType.CONNECTION,
            user_id=456,
            username="alice",
            websocket=mock_websocket,
        )

        # Act
        with caplog.at_level(logging.INFO):
            await resume_handler.handle_connect(event)

        # Assert
        assert any("Resume service" in record.message for record in caplog.records)
        assert any("alice" in record.message for record in caplog.records)
        assert any("456" in record.message for record in caplog.records)


class TestResumeHandlerMessageHandling:
    """Test message handling for ResumeHandler."""

    @pytest.mark.asyncio
    async def test_handle_message_logs_message(self, resume_handler, caplog):
        # Arrange
        event = Event(
            type=EventType.MESSAGE,
            user_id=789,
            username="bob",
            data={"action": "review_resume", "resume_id": 42},
        )

        # Act
        with caplog.at_level(logging.INFO):
            await resume_handler.handle_message(event)

        # Assert
        assert any("Resume service" in record.message for record in caplog.records)
        assert any("bob" in record.message for record in caplog.records)
        assert any("789" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_handle_message_with_empty_data(self, resume_handler, caplog):
        # Arrange
        event = Event(
            type=EventType.MESSAGE,
            user_id=111,
            username="charlie",
            data={},
        )

        # Act
        with caplog.at_level(logging.INFO):
            await resume_handler.handle_message(event)

        # Assert
        assert any("Resume service" in record.message for record in caplog.records)


class TestResumeHandlerDisconnectionHandling:
    """Test disconnection handling for ResumeHandler."""

    @pytest.mark.asyncio
    async def test_handle_disconnect_logs_disconnection(self, resume_handler, caplog):
        # Arrange
        event = Event(
            type=EventType.DISCONNECT,
            user_id=222,
            username="dave",
        )

        # Act
        with caplog.at_level(logging.INFO):
            await resume_handler.handle_disconnect(event)

        # Assert
        assert any("Resume service" in record.message for record in caplog.records)
        assert any("dave" in record.message for record in caplog.records)
        assert any("222" in record.message for record in caplog.records)
        assert any("disconnected" in record.message.lower() for record in caplog.records)


class TestResumeHandlerIntegration:
    """Integration tests for ResumeHandler with EventEmitter."""

    @pytest.mark.asyncio
    async def test_resume_handler_receives_connection_events(self, event_emitter, mock_websocket):
        # Arrange
        handler = ResumeHandler(event_emitter)
        event = Event(
            type=EventType.CONNECTION,
            user_id=333,
            username="integration",
            websocket=mock_websocket,
        )

        # Act
        await event_emitter.emit(event)

        # Assert
        mock_websocket.send_text.assert_called_once()
        sent_data = json.loads(mock_websocket.send_text.call_args[0][0])
        assert sent_data["type"] == MessageType.SYSTEM
        assert "integration" in sent_data["message"]

    @pytest.mark.asyncio
    async def test_resume_handler_receives_message_events(self, event_emitter, caplog):
        # Arrange
        handler = ResumeHandler(event_emitter)
        event = Event(
            type=EventType.MESSAGE,
            user_id=444,
            username="msguser",
            data={"test": "data"},
        )

        # Act
        with caplog.at_level(logging.INFO):
            await event_emitter.emit(event)

        # Assert
        assert any("msguser" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_resume_handler_receives_disconnect_events(self, event_emitter, caplog):
        # Arrange
        handler = ResumeHandler(event_emitter)
        event = Event(
            type=EventType.DISCONNECT,
            user_id=555,
            username="disconnector",
        )

        # Act
        with caplog.at_level(logging.INFO):
            await event_emitter.emit(event)

        # Assert
        assert any("disconnector" in record.message for record in caplog.records)
        assert any("disconnected" in record.message.lower() for record in caplog.records)

    @pytest.mark.asyncio
    async def test_multiple_resume_handlers_receive_events(self, event_emitter, mock_websocket):
        # Arrange
        handler1 = ResumeHandler(event_emitter)
        handler2 = ResumeHandler(event_emitter)
        event = Event(
            type=EventType.CONNECTION,
            user_id=666,
            username="multiuser",
            websocket=mock_websocket,
        )

        # Act
        await event_emitter.emit(event)

        # Assert
        # Both handlers should send a message
        assert mock_websocket.send_text.call_count == 2


class TestResumeHandlerErrorHandling:
    """Test error handling in ResumeHandler."""

    @pytest.mark.asyncio
    async def test_handle_connect_with_websocket_error(
        self, resume_handler, mock_websocket, caplog
    ):
        # Arrange
        event = Event(
            type=EventType.CONNECTION,
            user_id=777,
            username="erroruser",
            websocket=mock_websocket,
        )
        mock_websocket.send_text.side_effect = RuntimeError("WebSocket error")

        # Act
        with caplog.at_level(logging.DEBUG):
            await resume_handler.handle_connect(event)

        # Assert - should not raise, error is handled by safe_send
        assert any("Could not send message" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_handle_disconnect_with_missing_user_id(self, resume_handler, caplog):
        # Arrange
        event = Event(
            type=EventType.DISCONNECT,
            user_id=None,
            username="nouser",
        )

        # Act
        with caplog.at_level(logging.INFO):
            await resume_handler.handle_disconnect(event)

        # Assert - should handle gracefully and log with None
        assert any("nouser" in record.message for record in caplog.records)
        assert any("disconnected" in record.message.lower() for record in caplog.records)


class TestResumeHandlerSafeSend:
    """Test safe send functionality inherited from BaseHandler."""

    @pytest.mark.asyncio
    async def test_safe_send_sends_data(self, resume_handler, mock_websocket):
        # Arrange
        data = {"type": "test", "message": "Test message"}

        # Act
        await resume_handler.safe_send(mock_websocket, data)

        # Assert
        mock_websocket.send_text.assert_called_once()
        sent_json = mock_websocket.send_text.call_args[0][0]
        assert json.loads(sent_json) == data

    @pytest.mark.asyncio
    async def test_safe_send_handles_error(self, resume_handler, mock_websocket, caplog):
        # Arrange
        data = {"type": "test"}
        mock_websocket.send_text.side_effect = Exception("Send failed")

        # Act
        with caplog.at_level(logging.DEBUG):
            await resume_handler.safe_send(mock_websocket, data)

        # Assert - should not raise
        assert any("Could not send message" in record.message for record in caplog.records)


class TestResumeHandlerEdgeCases:
    """Test edge cases for ResumeHandler."""

    @pytest.mark.asyncio
    async def test_handle_message_with_none_data(self, resume_handler, caplog):
        # Arrange
        event = Event(
            type=EventType.MESSAGE,
            user_id=888,
            username="nonedata",
            data=None,
        )

        # Act
        with caplog.at_level(logging.INFO):
            await resume_handler.handle_message(event)

        # Assert - should handle gracefully
        assert any("Resume service" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_handle_message_with_complex_data(self, resume_handler, caplog):
        # Arrange
        complex_data = {
            "action": "review",
            "resume_id": 123,
            "metadata": {"reviewer": "admin", "timestamp": "2024-01-01"},
            "nested": {"deep": {"value": "test"}},
        }
        event = Event(
            type=EventType.MESSAGE,
            user_id=999,
            username="complexuser",
            data=complex_data,
        )

        # Act
        with caplog.at_level(logging.INFO):
            await resume_handler.handle_message(event)

        # Assert
        assert any("complexuser" in record.message for record in caplog.records)
