"""
Comprehensive tests for MQ consumer functions.
Tests consumer functions with WebSocket integration.
"""

import json
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from app.handlers import HandlerKind
from app.message import Message, MessageType
from app.mq.consumers import ReviewedResumeMessage, reviewed_resume_consumer
from pydantic import ValidationError


class TestReviewedResumeMessage:
    """Test ReviewedResumeMessage schema."""

    def test_valid_message(self):
        """Test creating a valid ReviewedResumeMessage."""
        # Arrange & Act
        message = ReviewedResumeMessage(feedback="Great resume!", key="123-456-resume.pdf")

        # Assert
        assert message.feedback == "Great resume!"
        assert message.key == "123-456-resume.pdf"

    def test_missing_feedback(self):
        """Test creating message without feedback raises error."""
        # Act & Assert
        with pytest.raises(ValidationError):
            ReviewedResumeMessage(key="123-456-resume.pdf")

    def test_missing_key(self):
        """Test creating message without key raises error."""
        # Act & Assert
        with pytest.raises(ValidationError):
            ReviewedResumeMessage(feedback="Great resume!")

    def test_extra_fields_ignored(self):
        """Test that extra fields are ignored."""
        # Arrange & Act
        message = ReviewedResumeMessage(
            feedback="Great resume!", key="123-456-resume.pdf", extra_field="ignored"
        )

        # Assert
        assert message.feedback == "Great resume!"
        assert message.key == "123-456-resume.pdf"
        assert not hasattr(message, "extra_field")


class TestReviewedResumeConsumer:
    """Test reviewed_resume_consumer function."""

    @pytest.mark.asyncio
    async def test_consumer_success(self):
        """Test successful message consumption and WebSocket send."""
        # Arrange
        mock_websocket = AsyncMock()
        mock_ws_connection_manager = MagicMock()
        mock_ws_connection_manager.get_websocket_connection.return_value = mock_websocket

        body = ReviewedResumeMessage(
            feedback="Excellent resume with strong technical skills.",
            key="42-789-john_doe_resume.pdf",
        )
        properties = MagicMock()

        with patch("app.mq.consumers.ConnectionManager", return_value=mock_ws_connection_manager):
            # Act
            await reviewed_resume_consumer(body, properties)

            # Assert
            mock_ws_connection_manager.get_websocket_connection.assert_called_once_with(
                HandlerKind.Resume, 42
            )
            mock_websocket.send_text.assert_called_once()

            # Verify message content
            call_args = mock_websocket.send_text.call_args
            sent_message = json.loads(call_args[0][0])
            assert sent_message["type"] == MessageType.RESUME_REVIEWED
            assert sent_message["user_id"] == 42
            assert sent_message["data"]["resume_id"] == "789"
            assert sent_message["data"]["file_name"] == "john_doe_resume.pdf"
            assert (
                sent_message["data"]["feedback"] == "Excellent resume with strong technical skills."
            )

    @pytest.mark.asyncio
    async def test_consumer_no_websocket_connection(self):
        """Test consumer when no WebSocket connection exists."""
        # Arrange
        mock_ws_connection_manager = MagicMock()
        mock_ws_connection_manager.get_websocket_connection.return_value = None

        body = ReviewedResumeMessage(feedback="Good resume.", key="42-789-resume.pdf")
        properties = MagicMock()

        with patch("app.mq.consumers.ConnectionManager", return_value=mock_ws_connection_manager):
            # Act
            await reviewed_resume_consumer(body, properties)

            # Assert
            mock_ws_connection_manager.get_websocket_connection.assert_called_once_with(
                HandlerKind.Resume, 42
            )
            # No exception should be raised, just a warning logged

    @pytest.mark.asyncio
    async def test_consumer_websocket_send_failure(self):
        """Test consumer when WebSocket send fails."""
        # Arrange
        mock_websocket = AsyncMock()
        mock_websocket.send_text.side_effect = Exception("WebSocket closed")

        mock_ws_connection_manager = MagicMock()
        mock_ws_connection_manager.get_websocket_connection.return_value = mock_websocket

        body = ReviewedResumeMessage(feedback="Good resume.", key="42-789-resume.pdf")
        properties = MagicMock()

        with patch("app.mq.consumers.ConnectionManager", return_value=mock_ws_connection_manager):
            # Act
            await reviewed_resume_consumer(body, properties)

            # Assert
            mock_websocket.send_text.assert_called_once()
            # No exception should be raised, just an error logged

    @pytest.mark.asyncio
    async def test_consumer_key_parsing(self):
        """Test consumer correctly parses key components."""
        # Arrange
        mock_websocket = AsyncMock()
        mock_ws_connection_manager = MagicMock()
        mock_ws_connection_manager.get_websocket_connection.return_value = mock_websocket

        body = ReviewedResumeMessage(
            feedback="Needs improvement.", key="999-12345-my_awesome_resume_v2.pdf"
        )
        properties = MagicMock()

        with patch("app.mq.consumers.ConnectionManager", return_value=mock_ws_connection_manager):
            # Act
            await reviewed_resume_consumer(body, properties)

            # Assert
            call_args = mock_websocket.send_text.call_args
            sent_message = json.loads(call_args[0][0])
            assert sent_message["user_id"] == 999
            assert sent_message["data"]["resume_id"] == "12345"
            assert sent_message["data"]["file_name"] == "my_awesome_resume_v2.pdf"
