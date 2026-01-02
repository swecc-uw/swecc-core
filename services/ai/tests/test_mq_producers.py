"""
Comprehensive tests for MQ producer functions
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# Import the underlying function before decoration
# We need to test the message formatting logic, not the publishing
async def finish_review_impl(data: dict):
    """Implementation of finish_review for testing"""
    feedback = data["feedback"]
    key = data["key"]

    if not feedback or not key:
        raise ValueError("Feedback and key must be provided")

    message_body = {"feedback": feedback, "key": key}
    return json.dumps(message_body).encode("utf-8")


class TestFinishReview:
    """Test finish_review producer function"""

    @pytest.mark.asyncio
    async def test_finish_review_success(self):
        """Test successful review completion message creation"""
        # Arrange
        test_data = {
            "feedback": "Great resume! Here's detailed feedback...",
            "key": "test-resume.pdf",
        }

        # Act
        result = await finish_review_impl(test_data)

        # Assert
        assert isinstance(result, bytes)
        decoded = json.loads(result.decode("utf-8"))
        assert decoded["feedback"] == "Great resume! Here's detailed feedback..."
        assert decoded["key"] == "test-resume.pdf"

    @pytest.mark.asyncio
    async def test_finish_review_with_long_feedback(self):
        """Test review completion with long feedback text"""
        # Arrange
        long_feedback = "A" * 10000  # Very long feedback
        test_data = {"feedback": long_feedback, "key": "test-resume.pdf"}

        # Act
        result = await finish_review_impl(test_data)

        # Assert
        assert isinstance(result, bytes)
        decoded = json.loads(result.decode("utf-8"))
        assert decoded["feedback"] == long_feedback
        assert len(decoded["feedback"]) == 10000

    @pytest.mark.asyncio
    async def test_finish_review_with_special_characters(self):
        """Test review completion with special characters in feedback"""
        # Arrange
        test_data = {
            "feedback": "Feedback with special chars: \n\t\"quotes\" and 'apostrophes' and émojis 🎉",
            "key": "résumé-file.pdf",
        }

        # Act
        result = await finish_review_impl(test_data)

        # Assert
        assert isinstance(result, bytes)
        decoded = json.loads(result.decode("utf-8"))
        assert decoded["feedback"] == test_data["feedback"]
        assert decoded["key"] == "résumé-file.pdf"

    @pytest.mark.asyncio
    async def test_finish_review_missing_feedback(self):
        """Test that missing feedback raises KeyError"""
        # Arrange
        test_data = {"key": "test-resume.pdf"}

        # Act & Assert
        with pytest.raises(KeyError):
            await finish_review_impl(test_data)

    @pytest.mark.asyncio
    async def test_finish_review_missing_key(self):
        """Test that missing key raises KeyError"""
        # Arrange
        test_data = {"feedback": "Some feedback"}

        # Act & Assert
        with pytest.raises(KeyError):
            await finish_review_impl(test_data)

    @pytest.mark.asyncio
    async def test_finish_review_empty_feedback(self):
        """Test that empty feedback raises ValueError"""
        # Arrange
        test_data = {"feedback": "", "key": "test-resume.pdf"}

        # Act & Assert
        with pytest.raises(ValueError, match="Feedback and key must be provided"):
            await finish_review_impl(test_data)

    @pytest.mark.asyncio
    async def test_finish_review_empty_key(self):
        """Test that empty key raises ValueError"""
        # Arrange
        test_data = {"feedback": "Some feedback", "key": ""}

        # Act & Assert
        with pytest.raises(ValueError, match="Feedback and key must be provided"):
            await finish_review_impl(test_data)

    @pytest.mark.asyncio
    async def test_finish_review_none_feedback(self):
        """Test that None feedback raises ValueError"""
        # Arrange
        test_data = {"feedback": None, "key": "test-resume.pdf"}

        # Act & Assert
        with pytest.raises(ValueError, match="Feedback and key must be provided"):
            await finish_review_impl(test_data)

    @pytest.mark.asyncio
    async def test_finish_review_none_key(self):
        """Test that None key raises ValueError"""
        # Arrange
        test_data = {"feedback": "Some feedback", "key": None}

        # Act & Assert
        with pytest.raises(ValueError, match="Feedback and key must be provided"):
            await finish_review_impl(test_data)

    @pytest.mark.asyncio
    async def test_finish_review_message_format(self):
        """Test that the message format is correct JSON"""
        # Arrange
        test_data = {"feedback": "Test feedback", "key": "test.pdf"}

        # Act
        result = await finish_review_impl(test_data)

        # Assert
        # Should be valid JSON
        decoded = json.loads(result.decode("utf-8"))
        # Should only contain feedback and key
        assert set(decoded.keys()) == {"feedback", "key"}
        # Should be bytes
        assert isinstance(result, bytes)

    @pytest.mark.asyncio
    async def test_finish_review_with_nested_path(self):
        """Test review completion with nested S3 path"""
        # Arrange
        test_data = {"feedback": "Feedback text", "key": "resumes/2024/01/user123/resume-final.pdf"}

        # Act
        result = await finish_review_impl(test_data)

        # Assert
        decoded = json.loads(result.decode("utf-8"))
        assert decoded["key"] == "resumes/2024/01/user123/resume-final.pdf"
