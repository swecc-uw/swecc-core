"""
Comprehensive tests for MQ consumer functions
"""

import json
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from app.mq.consumers import consume_to_review_message


class TestConsumeToReviewMessage:
    """Test consume_to_review_message consumer function"""

    @pytest.mark.asyncio
    async def test_consume_to_review_message_success(self):
        """Test successful message consumption and processing"""
        # Arrange
        test_message = {"key": "test-resume.pdf"}
        body = json.dumps(test_message).encode("utf-8")
        properties = MagicMock()

        mock_file_content = b"PDF file content"
        mock_feedback = "Great resume! Here's some feedback..."

        with patch("app.mq.consumers.S3Client") as mock_s3_class, patch(
            "app.mq.consumers.Gemini"
        ) as mock_gemini_class, patch("app.mq.consumers.finish_review") as mock_finish_review:

            # Setup S3 mock
            mock_s3_instance = MagicMock()
            mock_s3_instance.retrieve_object.return_value = mock_file_content
            mock_s3_class.return_value = mock_s3_instance

            # Setup Gemini mock
            mock_gemini_instance = MagicMock()
            mock_gemini_instance.prompt_file = AsyncMock(return_value=mock_feedback)
            mock_gemini_class.return_value = mock_gemini_instance

            # Setup finish_review mock
            mock_finish_review.return_value = AsyncMock()

            # Act
            await consume_to_review_message(body, properties)

            # Assert
            mock_s3_instance.retrieve_object.assert_called_once_with("test-resume.pdf")
            mock_gemini_instance.prompt_file.assert_called_once()
            call_args = mock_gemini_instance.prompt_file.call_args
            assert call_args[1]["bytes"] == mock_file_content
            assert "resume" in call_args[1]["prompt"].lower()
            assert call_args[1]["mime_type"] == "application/pdf"

            mock_finish_review.assert_called_once()
            finish_args = mock_finish_review.call_args[0][0]
            assert finish_args["feedback"] == mock_feedback
            assert finish_args["key"] == "test-resume.pdf"

    @pytest.mark.asyncio
    async def test_consume_to_review_message_with_different_key(self):
        """Test message consumption with different file key"""
        # Arrange
        test_message = {"key": "resumes/user123/resume-v2.pdf"}
        body = json.dumps(test_message).encode("utf-8")
        properties = MagicMock()

        mock_file_content = b"PDF content"
        mock_feedback = "Feedback text"

        with patch("app.mq.consumers.S3Client") as mock_s3_class, patch(
            "app.mq.consumers.Gemini"
        ) as mock_gemini_class, patch("app.mq.consumers.finish_review") as mock_finish_review:

            mock_s3_instance = MagicMock()
            mock_s3_instance.retrieve_object.return_value = mock_file_content
            mock_s3_class.return_value = mock_s3_instance

            mock_gemini_instance = MagicMock()
            mock_gemini_instance.prompt_file = AsyncMock(return_value=mock_feedback)
            mock_gemini_class.return_value = mock_gemini_instance

            mock_finish_review.return_value = AsyncMock()

            # Act
            await consume_to_review_message(body, properties)

            # Assert
            mock_s3_instance.retrieve_object.assert_called_once_with(
                "resumes/user123/resume-v2.pdf"
            )
            finish_args = mock_finish_review.call_args[0][0]
            assert finish_args["key"] == "resumes/user123/resume-v2.pdf"

    @pytest.mark.asyncio
    async def test_consume_to_review_message_s3_error(self):
        """Test handling S3 retrieval error"""
        # Arrange
        test_message = {"key": "test-resume.pdf"}
        body = json.dumps(test_message).encode("utf-8")
        properties = MagicMock()

        with patch("app.mq.consumers.S3Client") as mock_s3_class:
            mock_s3_instance = MagicMock()
            mock_s3_instance.retrieve_object.side_effect = Exception("S3 error")
            mock_s3_class.return_value = mock_s3_instance

            # Act & Assert
            with pytest.raises(Exception, match="S3 error"):
                await consume_to_review_message(body, properties)

    @pytest.mark.asyncio
    async def test_consume_to_review_message_gemini_error(self):
        """Test handling Gemini API error"""
        # Arrange
        test_message = {"key": "test-resume.pdf"}
        body = json.dumps(test_message).encode("utf-8")
        properties = MagicMock()

        mock_file_content = b"PDF content"

        with patch("app.mq.consumers.S3Client") as mock_s3_class, patch(
            "app.mq.consumers.Gemini"
        ) as mock_gemini_class:

            mock_s3_instance = MagicMock()
            mock_s3_instance.retrieve_object.return_value = mock_file_content
            mock_s3_class.return_value = mock_s3_instance

            mock_gemini_instance = MagicMock()
            mock_gemini_instance.prompt_file = AsyncMock(side_effect=Exception("Gemini API error"))
            mock_gemini_class.return_value = mock_gemini_instance

            # Act & Assert
            with pytest.raises(Exception, match="Gemini API error"):
                await consume_to_review_message(body, properties)

    @pytest.mark.asyncio
    async def test_consume_to_review_message_invalid_json(self):
        """Test handling invalid JSON in message body"""
        # Arrange
        body = b"invalid json {{"
        properties = MagicMock()

        # Act & Assert
        with pytest.raises(json.JSONDecodeError):
            await consume_to_review_message(body, properties)

    @pytest.mark.asyncio
    async def test_consume_to_review_message_missing_key(self):
        """Test handling message with missing key field"""
        # Arrange
        test_message = {}
        body = json.dumps(test_message).encode("utf-8")
        properties = MagicMock()

        # Act & Assert
        with pytest.raises(KeyError):
            await consume_to_review_message(body, properties)
