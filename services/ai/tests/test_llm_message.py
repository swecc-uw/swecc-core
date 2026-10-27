"""
Tests for Message class in app.llm.message module.
"""

from datetime import datetime

import pytest
from app.llm.message import Message


class TestMessage:
    """Test Message dataclass."""

    def test_message_creation(self):
        """Test creating a Message instance."""
        # Arrange
        timestamp = datetime(2024, 1, 1, 12, 0, 0)
        metadata = {"author": "test_user", "is_authorized": True}

        # Act
        message = Message(
            message="Hello, world!",
            response="Hi there!",
            timestamp=timestamp,
            metadata=metadata,
        )

        # Assert
        assert message.message == "Hello, world!"
        assert message.response == "Hi there!"
        assert message.timestamp == timestamp
        assert message.metadata == metadata

    def test_message_format_prompt(self):
        """Test format_prompt method."""
        # Arrange
        message = Message(
            message="What is Python?",
            response="Python is a programming language.",
            timestamp=datetime.now(),
            metadata={"author": "john_doe", "is_authorized": False},
        )

        # Act
        formatted = message.format_prompt()

        # Assert
        assert "author" not in formatted
        assert "is_authorized" not in formatted
        assert message.metadata["is_authorized"] is False
        assert "Message: What is Python?" in formatted
        assert formatted.startswith("\n")

    def test_message_format_prompt_empty_metadata(self):
        """Test format_prompt with empty metadata."""
        # Arrange
        message = Message(
            message="Test", response="Response", timestamp=datetime.now(), metadata={}
        )

        # Act
        formatted = message.format_prompt()

        # Assert
        assert formatted == "\nMessage: Test\n"

    def test_message_str_representation(self):
        """Test __str__ method."""
        # Arrange
        message = Message(
            message="Question",
            response="Answer",
            timestamp=datetime.now(),
            metadata={"key": "value"},
        )

        # Act
        str_repr = str(message)

        # Assert
        assert "Prompt:" in str_repr
        assert "Response: Answer" in str_repr
        assert "key" not in str_repr
        assert "Message: Question" in str_repr

    def test_message_repr_representation(self):
        """Test __repr__ method."""
        # Arrange
        message = Message(
            message="Question",
            response="Answer",
            timestamp=datetime.now(),
            metadata={"key": "value"},
        )

        # Act
        repr_str = repr(message)

        # Assert
        assert repr_str == str(message)

    def test_message_len(self):
        """Test __len__ method."""
        # Arrange
        message = Message(message="Short", response="OK", timestamp=datetime.now(), metadata={})

        # Act
        length = len(message)

        # Assert
        assert length == len(str(message))
        assert length > 0

    def test_message_len_ignores_metadata(self):
        """Metadata stays on the object and out of the model-facing text."""
        # Arrange
        message1 = Message(
            message="Test", response="Response", timestamp=datetime.now(), metadata={}
        )
        message2 = Message(
            message="Test",
            response="Response",
            timestamp=datetime.now(),
            metadata={"author": "user", "is_authorized": True},
        )

        # Act & Assert
        assert len(message2) == len(message1)
        assert message2.metadata["is_authorized"] is True

    def test_message_with_complex_metadata(self):
        """Test Message with complex metadata values."""
        # Arrange
        metadata = {
            "author": "test_user",
            "is_authorized": True,
            "channel_id": 12345,
            "tags": ["python", "testing"],
        }

        # Act
        message = Message(
            message="Complex test",
            response="Complex response",
            timestamp=datetime.now(),
            metadata=metadata,
        )

        # Assert
        formatted = message.format_prompt()
        assert "author" not in formatted
        assert "is_authorized" not in formatted
        assert "channel_id" not in formatted
        assert "Message: Complex test" in formatted
        assert message.metadata == metadata
