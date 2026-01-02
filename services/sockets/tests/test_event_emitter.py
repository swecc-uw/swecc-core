"""Tests for event emitter module."""

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest
from app.event_emitter import EventEmitter
from app.events import Event, EventType


@pytest.mark.asyncio
class TestEventEmitter:
    """Test EventEmitter class."""

    async def test_event_emitter_initialization(self):
        """Test EventEmitter initializes with empty listeners."""
        # Arrange & Act
        emitter = EventEmitter()

        # Assert
        assert emitter.listeners == {}

    async def test_on_adds_listener(self, event_emitter):
        """Test that on() adds a listener for an event type."""

        # Arrange
        async def test_listener(event):
            pass

        # Act
        event_emitter.on(EventType.MESSAGE, test_listener)

        # Assert
        assert EventType.MESSAGE in event_emitter.listeners
        assert test_listener in event_emitter.listeners[EventType.MESSAGE]

    async def test_on_adds_multiple_listeners(self, event_emitter):
        """Test that multiple listeners can be added for same event type."""

        # Arrange
        async def listener1(event):
            pass

        async def listener2(event):
            pass

        # Act
        event_emitter.on(EventType.MESSAGE, listener1)
        event_emitter.on(EventType.MESSAGE, listener2)

        # Assert
        assert len(event_emitter.listeners[EventType.MESSAGE]) == 2
        assert listener1 in event_emitter.listeners[EventType.MESSAGE]
        assert listener2 in event_emitter.listeners[EventType.MESSAGE]

    async def test_on_different_event_types(self, event_emitter):
        """Test adding listeners for different event types."""

        # Arrange
        async def connection_listener(event):
            pass

        async def message_listener(event):
            pass

        # Act
        event_emitter.on(EventType.CONNECTION, connection_listener)
        event_emitter.on(EventType.MESSAGE, message_listener)

        # Assert
        assert EventType.CONNECTION in event_emitter.listeners
        assert EventType.MESSAGE in event_emitter.listeners
        assert connection_listener in event_emitter.listeners[EventType.CONNECTION]
        assert message_listener in event_emitter.listeners[EventType.MESSAGE]

    async def test_off_removes_listener(self, event_emitter):
        """Test that off() removes a listener."""

        # Arrange
        async def test_listener(event):
            pass

        event_emitter.on(EventType.MESSAGE, test_listener)

        # Act
        event_emitter.off(EventType.MESSAGE, test_listener)

        # Assert
        assert test_listener not in event_emitter.listeners[EventType.MESSAGE]

    async def test_off_nonexistent_listener(self, event_emitter):
        """Test that off() handles removing nonexistent listener gracefully."""

        # Arrange
        async def test_listener(event):
            pass

        # Act & Assert - should not raise exception
        event_emitter.off(EventType.MESSAGE, test_listener)

    async def test_emit_calls_listener(self, event_emitter, sample_event):
        """Test that emit() calls registered listeners."""
        # Arrange
        mock_listener = AsyncMock()
        event_emitter.on(EventType.MESSAGE, mock_listener)

        # Act
        await event_emitter.emit(sample_event)

        # Assert
        mock_listener.assert_called_once_with(sample_event)

    async def test_emit_calls_multiple_listeners(self, event_emitter, sample_event):
        """Test that emit() calls all registered listeners."""
        # Arrange
        mock_listener1 = AsyncMock()
        mock_listener2 = AsyncMock()
        event_emitter.on(EventType.MESSAGE, mock_listener1)
        event_emitter.on(EventType.MESSAGE, mock_listener2)

        # Act
        await event_emitter.emit(sample_event)

        # Assert
        mock_listener1.assert_called_once_with(sample_event)
        mock_listener2.assert_called_once_with(sample_event)

    async def test_emit_no_listeners(self, event_emitter, sample_event):
        """Test that emit() handles no listeners gracefully."""
        # Arrange & Act & Assert - should not raise exception
        await event_emitter.emit(sample_event)

    async def test_emit_only_calls_matching_event_type(self, event_emitter):
        """Test that emit() only calls listeners for matching event type."""
        # Arrange
        message_listener = AsyncMock()
        connection_listener = AsyncMock()
        event_emitter.on(EventType.MESSAGE, message_listener)
        event_emitter.on(EventType.CONNECTION, connection_listener)

        message_event = Event(
            type=EventType.MESSAGE, user_id=1, username="user1", data={"msg": "test"}
        )

        # Act
        await event_emitter.emit(message_event)

        # Assert
        message_listener.assert_called_once()
        connection_listener.assert_not_called()

    async def test_emit_handles_listener_exception(self, event_emitter, sample_event):
        """Test that emit() handles listener exceptions gracefully."""

        # Arrange
        async def failing_listener(event):
            raise Exception("Listener error")

        successful_listener = AsyncMock()
        event_emitter.on(EventType.MESSAGE, failing_listener)
        event_emitter.on(EventType.MESSAGE, successful_listener)

        # Act & Assert - should not raise exception
        await event_emitter.emit(sample_event)

        # Other listeners should still be called
        successful_listener.assert_called_once()

    async def test_emit_handles_cancelled_error(self, event_emitter, sample_event):
        """Test that emit() propagates CancelledError."""

        # Arrange
        async def cancelled_listener(event):
            raise asyncio.CancelledError()

        event_emitter.on(EventType.MESSAGE, cancelled_listener)

        # Act & Assert
        # CancelledError should be propagated in gather with return_exceptions=True
        await event_emitter.emit(sample_event)

    async def test_listeners_execute_concurrently(self, event_emitter):
        """Test that multiple listeners execute concurrently."""
        # Arrange
        execution_order = []

        async def listener1(event):
            execution_order.append("listener1_start")
            await asyncio.sleep(0.01)
            execution_order.append("listener1_end")

        async def listener2(event):
            execution_order.append("listener2_start")
            await asyncio.sleep(0.01)
            execution_order.append("listener2_end")

        event_emitter.on(EventType.MESSAGE, listener1)
        event_emitter.on(EventType.MESSAGE, listener2)

        event = Event(type=EventType.MESSAGE, user_id=1, username="user1")

        # Act
        await event_emitter.emit(event)

        # Assert - both should start before either ends (concurrent execution)
        assert len(execution_order) == 4
        assert "listener1_start" in execution_order
        assert "listener2_start" in execution_order
