"""
Tests for polling.py module.

Tests cover:
- Status enum values
- PollingRequest dataclass
- generate_request_id function
"""

import uuid
from unittest.mock import patch

import pytest
from app.polling import PollingRequest, Status, generate_request_id


class TestStatusEnum:
    """Test Status enum values and behavior."""

    def test_status_enum_values(self):
        """Test that Status enum has all expected values."""
        # Arrange & Act & Assert
        assert Status.PENDING.value == "pending"
        assert Status.IN_PROGRESS.value == "in_progress"
        assert Status.SUCCESS.value == "success"
        assert Status.ERROR.value == "error"

    def test_status_enum_members(self):
        """Test that Status enum has exactly 4 members."""
        # Arrange & Act
        members = list(Status)

        # Assert
        assert len(members) == 4
        assert Status.PENDING in members
        assert Status.IN_PROGRESS in members
        assert Status.SUCCESS in members
        assert Status.ERROR in members


class TestPollingRequest:
    """Test PollingRequest dataclass."""

    def test_polling_request_creation_with_all_fields(self):
        """Test creating PollingRequest with all fields."""
        # Arrange
        request_id = "test-123"
        status = Status.PENDING
        result = "test result"
        error = None

        # Act
        request = PollingRequest(
            request_id=request_id,
            status=status,
            result=result,
            error=error,
        )

        # Assert
        assert request.request_id == request_id
        assert request.status == status
        assert request.result == result
        assert request.error is None

    def test_polling_request_with_error(self):
        """Test creating PollingRequest with error."""
        # Arrange
        request_id = "test-456"
        status = Status.ERROR
        error_msg = "Something went wrong"

        # Act
        request = PollingRequest(
            request_id=request_id,
            status=status,
            result=None,
            error=error_msg,
        )

        # Assert
        assert request.request_id == request_id
        assert request.status == Status.ERROR
        assert request.result is None
        assert request.error == error_msg

    def test_polling_request_status_transitions(self):
        """Test that PollingRequest status can be updated."""
        # Arrange
        request = PollingRequest(
            request_id="test-789",
            status=Status.PENDING,
            result=None,
            error=None,
        )

        # Act & Assert - transition to IN_PROGRESS
        request.status = Status.IN_PROGRESS
        assert request.status == Status.IN_PROGRESS

        # Act & Assert - transition to SUCCESS
        request.status = Status.SUCCESS
        request.result = "completed"
        assert request.status == Status.SUCCESS
        assert request.result == "completed"


class TestGenerateRequestId:
    """Test generate_request_id function."""

    def test_generate_request_id_returns_string(self):
        """Test that generate_request_id returns a string."""
        # Arrange & Act
        request_id = generate_request_id()

        # Assert
        assert isinstance(request_id, str)

    def test_generate_request_id_returns_valid_uuid(self):
        """Test that generate_request_id returns a valid UUID string."""
        # Arrange & Act
        request_id = generate_request_id()

        # Assert - should not raise ValueError
        uuid.UUID(request_id)

    def test_generate_request_id_returns_unique_ids(self):
        """Test that generate_request_id returns unique IDs."""
        # Arrange & Act
        id1 = generate_request_id()
        id2 = generate_request_id()
        id3 = generate_request_id()

        # Assert
        assert id1 != id2
        assert id2 != id3
        assert id1 != id3

    @patch("app.polling.uuid.uuid4")
    def test_generate_request_id_uses_uuid4(self, mock_uuid4):
        """Test that generate_request_id uses uuid.uuid4."""
        # Arrange
        mock_uuid = uuid.UUID("12345678-1234-5678-1234-567812345678")
        mock_uuid4.return_value = mock_uuid

        # Act
        request_id = generate_request_id()

        # Assert
        mock_uuid4.assert_called_once()
        assert request_id == str(mock_uuid)
