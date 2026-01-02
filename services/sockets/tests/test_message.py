"""Tests for message module."""

import pytest
from app.message import Message, MessageType
from pydantic import ValidationError


class TestMessageType:
    """Test MessageType enum."""

    def test_message_type_values(self):
        """Test that MessageType has expected values."""
        # Arrange & Act & Assert
        assert MessageType.SYSTEM == "system"
        assert MessageType.ERROR == "error"
        assert MessageType.ECHO == "echo"
        assert MessageType.LOG_LINE == "log_line"
        assert MessageType.LOGS_STARTED == "logs_started"
        assert MessageType.LOGS_STOPPED == "logs_stopped"
        assert MessageType.RESUME_REVIEWED == "resume_reviewed"

    def test_message_type_is_string_enum(self):
        """Test that MessageType is a string enum."""
        # Arrange & Act & Assert
        assert isinstance(MessageType.SYSTEM.value, str)
        assert isinstance(MessageType.ERROR.value, str)
        assert isinstance(MessageType.ECHO.value, str)

    def test_all_message_types_exist(self):
        """Test that all expected message types exist."""
        # Arrange
        expected_types = [
            "system",
            "error",
            "echo",
            "log_line",
            "logs_started",
            "logs_stopped",
            "resume_reviewed",
        ]

        # Act
        actual_types = [t.value for t in MessageType]

        # Assert
        for expected in expected_types:
            assert expected in actual_types


class TestMessage:
    """Test Message class."""

    def test_message_creation_with_all_fields(self):
        """Test creating a message with all fields."""
        # Arrange
        data = {"key": "value", "number": 42}

        # Act
        message = Message(
            type=MessageType.ECHO,
            message="Test message",
            user_id=1,
            username="testuser",
            data=data,
        )

        # Assert
        assert message.type == MessageType.ECHO
        assert message.message == "Test message"
        assert message.user_id == 1
        assert message.username == "testuser"
        assert message.data == data

    def test_message_creation_with_required_fields_only(self):
        """Test creating a message with only required fields."""
        # Arrange & Act
        message = Message(type=MessageType.SYSTEM)

        # Assert
        assert message.type == MessageType.SYSTEM
        assert message.message is None
        assert message.user_id is None
        assert message.username is None
        assert message.data is None

    def test_message_with_error_type(self):
        """Test creating an error message."""
        # Arrange & Act
        message = Message(type=MessageType.ERROR, message="An error occurred")

        # Assert
        assert message.type == MessageType.ERROR
        assert message.message == "An error occurred"

    def test_message_with_log_line_type(self):
        """Test creating a log line message."""
        # Arrange
        log_data = {"container": "app", "line": "Starting server..."}

        # Act
        message = Message(type=MessageType.LOG_LINE, data=log_data)

        # Assert
        assert message.type == MessageType.LOG_LINE
        assert message.data == log_data

    def test_message_with_resume_reviewed_type(self):
        """Test creating a resume reviewed message."""
        # Arrange
        review_data = {"resume_id": 123, "status": "approved"}

        # Act
        message = Message(
            type=MessageType.RESUME_REVIEWED,
            user_id=5,
            username="reviewer",
            data=review_data,
        )

        # Assert
        assert message.type == MessageType.RESUME_REVIEWED
        assert message.user_id == 5
        assert message.username == "reviewer"
        assert message.data["resume_id"] == 123

    def test_message_serialization(self):
        """Test that message can be serialized to dict."""
        # Arrange
        message = Message(
            type=MessageType.ECHO,
            message="Hello",
            user_id=1,
            username="user1",
        )

        # Act
        message_dict = message.model_dump()

        # Assert
        assert isinstance(message_dict, dict)
        assert message_dict["type"] == "echo"
        assert message_dict["message"] == "Hello"
        assert message_dict["user_id"] == 1
        assert message_dict["username"] == "user1"

    def test_message_json_serialization(self):
        """Test that message can be serialized to JSON."""
        # Arrange
        message = Message(type=MessageType.SYSTEM, message="System message")

        # Act
        message_json = message.model_dump_json()

        # Assert
        assert isinstance(message_json, str)
        assert "system" in message_json
        assert "System message" in message_json

    def test_message_with_complex_data(self):
        """Test message with complex nested data."""
        # Arrange
        complex_data = {
            "nested": {"deep": {"value": 42}},
            "list": [1, 2, 3],
            "mixed": {"numbers": [1, 2], "strings": ["a", "b"]},
        }

        # Act
        message = Message(type=MessageType.ECHO, data=complex_data)

        # Assert
        assert message.data == complex_data
        assert message.data["nested"]["deep"]["value"] == 42

    def test_message_type_validation(self):
        """Test that invalid message type raises validation error."""
        # Arrange & Act & Assert
        with pytest.raises(ValidationError):
            Message(type="invalid_type")
