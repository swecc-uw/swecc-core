"""
Tests for ContextManager class in app.llm.context module.
"""

from collections import deque
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from app.llm.context import ContextConfig, ContextManager
from app.llm.message import Message


class TestContextConfig:
    """Test ContextConfig dataclass."""

    def test_context_config_creation(self):
        """Test creating a ContextConfig instance."""
        # Arrange & Act
        config = ContextConfig(
            max_context_length=1000,
            context_invalidation_time_seconds=600,
            system_instruction="You are a helpful assistant.",
        )

        # Assert
        assert config.max_context_length == 1000
        assert config.context_invalidation_time_seconds == 600
        assert config.system_instruction == "You are a helpful assistant."


class TestContextManager:
    """Test ContextManager singleton class."""

    def test_singleton_pattern(self):
        """Test ContextManager follows singleton pattern."""
        # Act
        manager1 = ContextManager()
        manager2 = ContextManager()

        # Assert
        assert manager1 is manager2

    def test_initialization(self):
        """Test ContextManager initialization."""
        # Act
        manager = ContextManager()

        # Assert
        assert hasattr(manager, "context_configs")
        assert hasattr(manager, "context")
        assert hasattr(manager, "initialized")
        assert isinstance(manager.context_configs, dict)
        assert isinstance(manager.context, dict)
        assert manager.initialized is True

    def test_add_context_config(self, sample_context_config):
        """Test adding a context configuration."""
        # Arrange
        manager = ContextManager()
        key = "test_key"

        # Act
        manager.add_context_config(key, **sample_context_config)

        # Assert
        assert key in manager.context_configs
        assert key in manager.context
        assert isinstance(manager.context[key], deque)
        assert manager.context_configs[key].max_context_length == 1000
        assert manager.context_configs[key].context_invalidation_time_seconds == 600

    def test_add_context_config_multiple_keys(self, sample_context_config):
        """Test adding multiple context configurations."""
        # Arrange
        manager = ContextManager()

        # Act
        manager.add_context_config("key1", **sample_context_config)
        manager.add_context_config("key2", **sample_context_config)

        # Assert
        assert "key1" in manager.context_configs
        assert "key2" in manager.context_configs
        assert len(manager.context_configs) == 2

    def test_is_registered(self, sample_context_config):
        """Test is_registered method."""
        # Arrange
        manager = ContextManager()
        manager.add_context_config("registered_key", **sample_context_config)

        # Act & Assert
        assert manager.is_registered("registered_key") is True
        assert manager.is_registered("unregistered_key") is False

    def test_add_message_to_context(self, sample_context_config, sample_message):
        """Test adding a message to context."""
        # Arrange
        manager = ContextManager()
        key = "test_key"
        manager.add_context_config(key, **sample_context_config)

        # Act
        manager.add_message_to_context(key, sample_message)

        # Assert
        assert len(manager.context[key]) == 1
        assert manager.context[key][0] == sample_message

    def test_add_message_to_nonexistent_context(self, sample_message):
        """Test adding message to non-existent context raises ValueError."""
        # Arrange
        manager = ContextManager()

        # Act & Assert
        with pytest.raises(ValueError, match="Context key `nonexistent` not found"):
            manager.add_message_to_context("nonexistent", sample_message)

    def test_update_context_removes_old_messages(self, sample_context_config):
        """Test that _update_context removes old messages when max length exceeded."""
        # Arrange
        manager = ContextManager()
        key = "test_key"
        config = sample_context_config.copy()
        config["max_context_length"] = 250  # Small limit
        manager.add_context_config(key, **config)

        # Create messages that will exceed the limit
        messages = [
            Message(
                message=f"Message {i}" * 10,
                response=f"Response {i}" * 10,
                timestamp=datetime.now(),
                metadata={},
            )
            for i in range(5)
        ]

        # Act
        for msg in messages:
            manager.add_message_to_context(key, msg)

        # Assert
        # Should have removed some messages to stay under limit
        total_length = sum(len(msg) for msg in manager.context[key])
        assert total_length < config["max_context_length"]
        assert len(manager.context[key]) < len(messages)

    def test_contextualize_prompt_with_empty_context(self, sample_context_config):
        """Test contextualize_prompt with empty context."""
        # Arrange
        manager = ContextManager()
        key = "test_key"
        manager.add_context_config(key, **sample_context_config)
        prompt = "What is Python?"

        # Act
        result = manager.contextualize_prompt(key, prompt)

        # Assert
        assert "<CONTEXT>" in result
        assert "</CONTEXT>" in result
        assert prompt in result
        assert result == f"<CONTEXT>\n\n</CONTEXT>\n{prompt}"

    def test_contextualize_prompt_with_messages(self, sample_context_config):
        """Test contextualize_prompt with messages in context."""
        # Arrange
        manager = ContextManager()
        key = "test_key"
        manager.add_context_config(key, **sample_context_config)

        # Create and add a message
        message = Message(
            message="Test message",
            response="Test response",
            timestamp=datetime.now(),
            metadata={"author": "test_user"},
        )
        manager.add_message_to_context(key, message)
        prompt = "New question"

        # Act
        result = manager.contextualize_prompt(key, prompt)

        # Assert
        assert "<CONTEXT>" in result
        assert "</CONTEXT>" in result
        assert prompt in result
        assert "Test message" in result
        assert "Test response" in result

    def test_contextualize_prompt_nonexistent_key(self):
        """Test contextualize_prompt with non-existent key raises ValueError."""
        # Arrange
        manager = ContextManager()

        # Act & Assert
        with pytest.raises(ValueError, match="Context key `nonexistent` not found"):
            manager.contextualize_prompt("nonexistent", "test prompt")

    @patch("app.llm.context.datetime")
    def test_ensure_relevant_context_clears_old_context(self, mock_datetime, sample_context_config):
        """Test that old context is cleared based on invalidation time."""
        # Arrange
        manager = ContextManager()
        key = "test_key"
        config = sample_context_config.copy()
        config["context_invalidation_time_seconds"] = 60  # 1 minute
        manager.add_context_config(key, **config)

        # Add a message with old timestamp
        old_time = datetime(2024, 1, 1, 12, 0, 0)
        message = Message(
            message="Old message",
            response="Old response",
            timestamp=old_time,
            metadata={},
        )
        manager.add_message_to_context(key, message)

        # Mock current time to be 2 minutes later
        current_time = old_time + timedelta(minutes=2)
        mock_datetime.now.return_value = current_time

        # Act
        manager.contextualize_prompt(key, "New prompt")

        # Assert
        assert len(manager.context[key]) == 0

    @patch("app.llm.context.datetime")
    def test_ensure_relevant_context_keeps_recent_context(
        self, mock_datetime, sample_context_config
    ):
        """Test that recent context is kept."""
        # Arrange
        manager = ContextManager()
        key = "test_key"
        config = sample_context_config.copy()
        config["context_invalidation_time_seconds"] = 600  # 10 minutes
        manager.add_context_config(key, **config)

        # Add a recent message
        recent_time = datetime(2024, 1, 1, 12, 0, 0)
        message = Message(
            message="Recent message",
            response="Recent response",
            timestamp=recent_time,
            metadata={},
        )
        manager.add_message_to_context(key, message)

        # Mock current time to be 5 minutes later (within invalidation time)
        current_time = recent_time + timedelta(minutes=5)
        mock_datetime.now.return_value = current_time

        # Act
        manager.contextualize_prompt(key, "New prompt")

        # Assert
        assert len(manager.context[key]) == 1

    def test_multiple_messages_in_context(self, sample_context_config):
        """Test adding multiple messages to context."""
        # Arrange
        manager = ContextManager()
        key = "test_key"
        manager.add_context_config(key, **sample_context_config)

        messages = [
            Message(
                message=f"Message {i}",
                response=f"Response {i}",
                timestamp=datetime.now(),
                metadata={"index": i},
            )
            for i in range(3)
        ]

        # Act
        for msg in messages:
            manager.add_message_to_context(key, msg)

        # Assert
        assert len(manager.context[key]) == 3
        for i, msg in enumerate(manager.context[key]):
            assert msg.message == f"Message {i}"
