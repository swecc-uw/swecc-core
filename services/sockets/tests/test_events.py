"""Tests for events module."""

from unittest.mock import Mock

import pytest
from app.events import Event, EventType


class TestEventType:
    """Test EventType enum."""

    def test_event_type_values(self):
        """Test that EventType has expected values."""
        # Arrange & Act & Assert
        assert EventType.CONNECTION == "connection"
        assert EventType.MESSAGE == "message"
        assert EventType.DISCONNECT == "disconnect"

    def test_event_type_is_string_enum(self):
        """Test that EventType is a string enum."""
        # Arrange & Act & Assert
        assert isinstance(EventType.CONNECTION.value, str)
        assert isinstance(EventType.MESSAGE.value, str)
        assert isinstance(EventType.DISCONNECT.value, str)

    def test_event_type_membership(self):
        """Test EventType membership checks."""
        # Arrange & Act & Assert
        assert "connection" in [e.value for e in EventType]
        assert "message" in [e.value for e in EventType]
        assert "disconnect" in [e.value for e in EventType]


class TestEvent:
    """Test Event class."""

    def test_event_creation_with_all_fields(self):
        """Test creating an event with all fields."""
        # Arrange
        mock_websocket = Mock()
        data = {"key": "value"}

        # Act
        event = Event(
            type=EventType.MESSAGE,
            user_id=1,
            username="testuser",
            data=data,
            websocket=mock_websocket,
        )

        # Assert
        assert event.type == EventType.MESSAGE
        assert event.user_id == 1
        assert event.username == "testuser"
        assert event.data == data
        assert event.websocket == mock_websocket

    def test_event_creation_without_optional_fields(self):
        """Test creating an event without optional fields."""
        # Arrange & Act
        event = Event(
            type=EventType.DISCONNECT,
            user_id=2,
            username="anotheruser",
        )

        # Assert
        assert event.type == EventType.DISCONNECT
        assert event.user_id == 2
        assert event.username == "anotheruser"
        assert event.data == {}
        assert event.websocket is None

    def test_event_data_defaults_to_empty_dict(self):
        """Test that event data defaults to empty dict when None."""
        # Arrange & Act
        event = Event(
            type=EventType.CONNECTION,
            user_id=3,
            username="user3",
            data=None,
        )

        # Assert
        assert event.data == {}
        assert isinstance(event.data, dict)

    def test_event_with_complex_data(self):
        """Test event with complex nested data."""
        # Arrange
        complex_data = {
            "nested": {"key": "value"},
            "list": [1, 2, 3],
            "string": "test",
            "number": 42,
        }

        # Act
        event = Event(
            type=EventType.MESSAGE,
            user_id=4,
            username="user4",
            data=complex_data,
        )

        # Assert
        assert event.data == complex_data
        assert event.data["nested"]["key"] == "value"
        assert event.data["list"] == [1, 2, 3]

    def test_connection_event(self):
        """Test creating a connection event."""
        # Arrange
        mock_websocket = Mock()

        # Act
        event = Event(
            type=EventType.CONNECTION,
            user_id=5,
            username="user5",
            websocket=mock_websocket,
        )

        # Assert
        assert event.type == EventType.CONNECTION
        assert event.websocket == mock_websocket

    def test_message_event(self):
        """Test creating a message event."""
        # Arrange
        message_data = {"message": "Hello, World!"}

        # Act
        event = Event(
            type=EventType.MESSAGE,
            user_id=6,
            username="user6",
            data=message_data,
        )

        # Assert
        assert event.type == EventType.MESSAGE
        assert event.data["message"] == "Hello, World!"

    def test_disconnect_event(self):
        """Test creating a disconnect event."""
        # Arrange & Act
        event = Event(
            type=EventType.DISCONNECT,
            user_id=7,
            username="user7",
        )

        # Assert
        assert event.type == EventType.DISCONNECT
        assert event.data == {}
        assert event.websocket is None
