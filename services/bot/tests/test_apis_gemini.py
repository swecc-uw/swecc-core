"""Tests for GeminiAPI."""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
import requests
from APIs.GeminiAPI import GeminiAPI, Metadata


class TestMetadata:
    """Test suite for Metadata dataclass."""

    def test_metadata_creation(self):
        """Test creating Metadata instance."""
        # Arrange & Act
        metadata = Metadata(is_authorized=True, author="test_user")

        # Assert
        assert metadata.is_authorized is True
        assert metadata.author == "test_user"

    def test_metadata_frozen(self):
        """Test that Metadata is immutable."""
        # Arrange
        metadata = Metadata(is_authorized=True, author="test_user")

        # Act & Assert
        with pytest.raises((AttributeError, TypeError)):  # FrozenInstanceError
            metadata.is_authorized = False

    def test_metadata_optional_fields(self):
        """Test Metadata with None values."""
        # Arrange & Act
        metadata = Metadata(is_authorized=None, author=None)

        # Assert
        assert metadata.is_authorized is None
        assert metadata.author is None


class TestGeminiAPI:
    """Test suite for GeminiAPI."""

    @pytest.fixture
    def api(self):
        """Create a GeminiAPI instance for testing."""
        with patch.dict(
            "os.environ",
            {
                "OFF_TOPIC_CHANNEL_ID": "123456",
                "OFFICER_ROLE_ID": "789012",
                "AI_API_URL": "http://test-ai-server:8008",
            },
        ):
            return GeminiAPI()

    def test_init(self, api):
        """Test API initialization."""
        # Arrange & Act - done in fixture
        # Assert
        assert api.OFF_TOPIC_CHANNEL_ID == 123456
        assert api.allowlisted_roles_id == [789012]
        assert api.url == "http://test-ai-server:8008"
        assert api.max_context_length == 2000
        assert api.context_invalidation_time_seconds == 600
        assert isinstance(api.session, requests.Session)

    def test_init_with_custom_params(self):
        """Test API initialization with custom parameters."""
        # Arrange & Act
        with patch.dict(
            "os.environ", {"OFF_TOPIC_CHANNEL_ID": "123456", "OFFICER_ROLE_ID": "789012"}
        ):
            api = GeminiAPI(max_context_length=5000, context_invalidation_time_seconds=1200)

        # Assert
        assert api.max_context_length == 5000
        assert api.context_invalidation_time_seconds == 1200

    def test_generate_system_instruction(self, api):
        """Test system instruction generation."""
        # Arrange & Act
        instruction = api.generate_system_instruction()

        # Assert
        assert api.ROLE in instruction
        assert api.MESSAGE_FORMAT_INSTRUCTION in instruction
        assert api.AUTHORIZED_INSTRUCTION in instruction
        assert api.UNAUTHORIZED_INSTRUCTION in instruction

    def test_format_user_message(self, api):
        """Test formatting user message."""
        # Arrange
        mock_message = Mock()
        mock_message.content = "Gemini what is the weather?"

        # Act
        result = api.format_user_message(mock_message)

        # Assert
        assert result == "what is the weather?"

    def test_format_user_message_case_insensitive(self, api):
        """Test formatting user message is case insensitive."""
        # Arrange
        mock_message = Mock()
        mock_message.content = "GEMINI tell me a joke"

        # Act
        result = api.format_user_message(mock_message)

        # Assert
        assert result == "tell me a joke"

    def test_is_authorized_with_authorized_user(self, api):
        """Test authorization check for authorized user."""
        # Arrange
        mock_role = Mock()
        mock_role.id = 789012
        mock_message = Mock()
        mock_message.author.roles = [mock_role]

        # Act
        result = api.is_authorized(mock_message)

        # Assert
        assert result is True

    def test_is_authorized_with_unauthorized_user(self, api):
        """Test authorization check for unauthorized user."""
        # Arrange
        mock_role = Mock()
        mock_role.id = 999999
        mock_message = Mock()
        mock_message.author.roles = [mock_role]

        # Act
        result = api.is_authorized(mock_message)

        # Assert
        assert result is False

    def test_clean_response_removes_prefix(self, api):
        """Test cleaning response removes prefix."""
        # Arrange
        response = "Response: This is the actual response"

        # Act
        result = api.clean_response(response)

        # Assert
        assert result == "This is the actual response"

    def test_clean_response_truncates_long_response(self, api):
        """Test cleaning response truncates long messages."""
        # Arrange
        response = "a" * 2500

        # Act
        result = api.clean_response(response)

        # Assert
        assert len(result) == 2000
        assert result.endswith("...")

    def test_clean_response_blocks_mentions(self, api):
        """Test cleaning response blocks @ mentions."""
        # Arrange
        response = "Hello @user, how are you?"

        # Act
        result = api.clean_response(response)

        # Assert
        assert result == "NO"

    def test_initialize_config(self, api):
        """Test configuration initialization."""
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)

        # Act
        with patch.object(api.session, "post", return_value=mock_response) as mock_post:
            api.initialize_config()

        # Assert
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert "swecc-bot" in call_args[0][0]
        assert "json" in call_args[1]

    def test_initialize_config_handles_error(self, api):
        """Test configuration initialization handles errors."""
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)

        # Act
        with patch.object(api.session, "post", return_value=mock_response):
            api.initialize_config()  # Should not raise, just log error

        # Assert - no exception raised

    def test_request_completion_success(self, api):
        """Test successful completion request."""
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 202
        mock_response.json.return_value = {"request_id": "test-request-123"}
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        metadata = Metadata(is_authorized=True, author="test_user")

        # Act
        with patch.object(api.session, "post", return_value=mock_response):
            result = api.request_completion("test message", metadata, "test-key")

        # Assert
        assert result == "test-request-123"

    def test_request_completion_failure(self, api):
        """Test failed completion request."""
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Server Error"
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        metadata = Metadata(is_authorized=True, author="test_user")

        # Act
        with patch.object(api.session, "post", return_value=mock_response):
            result = api.request_completion("test message", metadata, "test-key")

        # Assert
        assert result is None

    def test_poll_for_response_success(self, api):
        """Test successful polling for response."""
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "success", "result": "Response: Test response"}
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)

        # Act
        with patch.object(api.session, "get", return_value=mock_response):
            result = api.poll_for_response("test-request-123")

        # Assert
        assert result == "Test response"

    def test_poll_for_response_pending_then_success(self, api):
        """Test polling with pending status then success."""
        # Arrange
        pending_response = Mock()
        pending_response.status_code = 200
        pending_response.json.return_value = {"status": "pending"}
        pending_response.__enter__ = Mock(return_value=pending_response)
        pending_response.__exit__ = Mock(return_value=False)

        success_response = Mock()
        success_response.status_code = 200
        success_response.json.return_value = {
            "status": "success",
            "result": "Response: Final response",
        }
        success_response.__enter__ = Mock(return_value=success_response)
        success_response.__exit__ = Mock(return_value=False)

        # Act
        with patch.object(api.session, "get", side_effect=[pending_response, success_response]):
            result = api.poll_for_response("test-request-123")

        # Assert
        assert result == "Final response"

    def test_poll_for_response_timeout(self, api):
        """Test polling timeout."""
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "pending"}
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)

        # Act
        with patch.object(api.session, "get", return_value=mock_response):
            result = api.poll_for_response("test-request-123")

        # Assert
        assert "Request failed" in result

    def test_poll_for_response_error_status(self, api):
        """Test polling with error status."""
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "error"}
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)

        # Act
        with patch.object(api.session, "get", return_value=mock_response):
            result = api.poll_for_response("test-request-123")

        # Assert
        assert "Error occurred" in result

    @pytest.mark.asyncio
    async def test_get_welcome_message(self, api):
        """Test getting welcome message."""
        # Arrange
        mock_init_response = Mock()
        mock_init_response.status_code = 200
        mock_init_response.__enter__ = Mock(return_value=mock_init_response)
        mock_init_response.__exit__ = Mock(return_value=False)

        mock_completion_response = Mock()
        mock_completion_response.status_code = 202
        mock_completion_response.json.return_value = {"request_id": "req-welcome"}
        mock_completion_response.__enter__ = Mock(return_value=mock_completion_response)
        mock_completion_response.__exit__ = Mock(return_value=False)

        mock_poll_response = Mock()
        mock_poll_response.status_code = 200
        mock_poll_response.json.return_value = {"status": "success", "result": "Welcome to SWECC!"}
        mock_poll_response.__enter__ = Mock(return_value=mock_poll_response)
        mock_poll_response.__exit__ = Mock(return_value=False)

        # Act
        with patch.object(
            api.session, "post", side_effect=[mock_init_response, mock_completion_response]
        ):
            with patch.object(api.session, "get", return_value=mock_poll_response):
                result = await api.get_welcome_message("TestUser", "123456789")

        # Assert
        assert result == "Welcome to SWECC!"
