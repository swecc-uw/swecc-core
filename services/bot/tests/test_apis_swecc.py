"""Tests for SweccAPI."""

from unittest.mock import AsyncMock, Mock, patch

import aiohttp
import pytest
import requests
from APIs.SweccAPI import SweccAPI


class TestSweccAPI:
    """Test suite for SweccAPI."""

    @pytest.fixture
    def api(self):
        """Create a SweccAPI instance for testing."""
        with patch.dict(
            "os.environ",
            {
                "SWECC_URL": "https://test.swecc.org",
                "SWECC_API_KEY": "test-api-key-123",
                "NEW_GRAD_CHANNEL_ID": "111111",
                "INTERNSHIP_CHANNEL_ID": "222222",
            },
        ):
            return SweccAPI()

    def test_init(self, api):
        """Test API initialization."""
        # Arrange & Act - done in fixture
        # Assert
        assert api.url == "https://test.swecc.org"
        assert api.api_key == "test-api-key-123"
        assert api.headers["Authorization"] == "Api-Key test-api-key-123"
        assert api.headers["Content-Type"] == "application/json"
        assert 111111 in api.reaction_channel_subscriptions
        assert 222222 in api.reaction_channel_subscriptions
        assert api.COMPLETED_EMOJI == "✅"

    def test_set_and_get_session(self, api):
        """Test setting and getting aiohttp session."""
        # Arrange
        mock_session = Mock(spec=aiohttp.ClientSession)

        # Act
        api.set_session(mock_session)
        result = api.get_session()

        # Assert
        assert result == mock_session

    def test_get_session_not_set_raises_error(self, api):
        """Test getting session when not set raises error."""
        # Arrange - reset the global session
        from APIs.SweccAPI import aio_session_global

        original = aio_session_global[0]
        aio_session_global[0] = None
        try:
            # Act & Assert
            with pytest.raises(Exception, match="aiohttp session not set"):
                api.get_session()
        finally:
            # Restore original state
            aio_session_global[0] = original

    def test_register_success(self, api):
        """Test successful user registration."""
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"message": "User registered successfully"}

        # Act
        with patch.object(api.session, "post", return_value=mock_response):
            status_code, data = api.register(
                username="testuser",
                first_name="Test",
                last_name="User",
                email="test@example.com",
                password="password123",
                discord_username="testuser#1234",
            )

        # Assert
        assert status_code == 201
        assert data["message"] == "User registered successfully"

    def test_register_with_error(self, api):
        """Test registration with error response."""
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"error": "Username already exists"}

        # Act
        with patch.object(api.session, "post", return_value=mock_response):
            status_code, data = api.register(
                username="existinguser",
                first_name="Test",
                last_name="User",
                email="test@example.com",
                password="password123",
                discord_username="testuser#1234",
            )

        # Assert
        assert status_code == 400
        assert "error" in data

    def test_register_exception_handling(self, api):
        """Test registration exception handling."""
        # Arrange
        with patch.object(api.session, "post", side_effect=Exception("Network error")):
            # Act & Assert
            with pytest.raises(Exception, match="Network error"):
                api.register(
                    username="testuser",
                    first_name="Test",
                    last_name="User",
                    email="test@example.com",
                    password="password123",
                    discord_username="testuser#1234",
                )

    def test_auth_success(self, api):
        """Test successful authentication."""
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 200

        # Act
        with patch("requests.put", return_value=mock_response):
            status_code = api.auth(
                discord_username="testuser#1234", id="123456789", username="testuser"
            )

        # Assert
        assert status_code == 200

    def test_auth_failure(self, api):
        """Test failed authentication."""
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 404

        # Act
        with patch("requests.put", return_value=mock_response):
            status_code = api.auth(
                discord_username="testuser#1234", id="123456789", username="testuser"
            )

        # Assert
        assert status_code == 404

    def test_leetcode_leaderboard_success(self, api):
        """Test getting LeetCode leaderboard successfully."""
        # Arrange
        mock_data = [{"username": "user1", "total": 100}, {"username": "user2", "total": 90}]
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_data

        # Act
        with patch("requests.get", return_value=mock_response):
            result = api.leetcode_leaderboard(order_by="total")

        # Assert
        assert result == mock_data
        assert len(result) == 2

    def test_leetcode_leaderboard_failure(self, api):
        """Test LeetCode leaderboard with error."""
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 500

        # Act
        with patch("requests.get", return_value=mock_response):
            result = api.leetcode_leaderboard()

        # Assert
        assert result is None

    def test_github_leaderboard_success(self, api):
        """Test getting GitHub leaderboard successfully."""
        # Arrange
        mock_data = [{"username": "user1", "commits": 50}, {"username": "user2", "commits": 40}]
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_data

        # Act
        with patch("requests.get", return_value=mock_response):
            result = api.github_leaderboard(order_by="commits")

        # Assert
        assert result == mock_data

    def test_github_leaderboard_failure(self, api):
        """Test GitHub leaderboard with error."""
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 500

        # Act
        with patch("requests.get", return_value=mock_response):
            result = api.github_leaderboard()

        # Assert
        assert result is None

    @pytest.mark.asyncio
    async def test_reset_password(self, api):
        """Test password reset."""
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"uid": "test-uid-123", "token": "test-token-456"}

        # Act
        with patch("requests.post", return_value=mock_response):
            result = await api.reset_password("testuser#1234", "123456789")

        # Assert
        assert "test-uid-123" in result
        assert "test-token-456" in result
        assert "password-reset-confirm" in result

    @pytest.mark.asyncio
    async def test_process_reaction_event_add(self, api):
        """Test processing reaction add event."""
        # Arrange
        mock_session = AsyncMock(spec=aiohttp.ClientSession)
        mock_response = AsyncMock()
        mock_response.status = 202
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)
        mock_session.post.return_value = mock_response

        api.set_session(mock_session)

        mock_payload = Mock()
        mock_payload.user_id = 123456
        mock_payload.channel_id = 111111
        mock_payload.emoji = Mock()
        mock_payload.emoji.name = "✅"

        # Act
        await api.process_reaction_event(mock_payload, "REACTION_ADD")

        # Assert
        mock_session.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_reaction_event_remove(self, api):
        """Test processing reaction remove event."""
        # Arrange
        mock_session = AsyncMock(spec=aiohttp.ClientSession)
        mock_response = AsyncMock()
        mock_response.status = 202
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)
        mock_session.delete.return_value = mock_response

        api.set_session(mock_session)

        mock_payload = Mock()
        mock_payload.user_id = 123456
        mock_payload.channel_id = 111111
        mock_payload.emoji = Mock()
        mock_payload.emoji.name = "✅"

        # Act
        await api.process_reaction_event(mock_payload, "REACTION_REMOVE")

        # Assert
        mock_session.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_reaction_event_wrong_emoji(self, api):
        """Test that non-completed emoji reactions are ignored."""
        # Arrange
        mock_session = AsyncMock(spec=aiohttp.ClientSession)
        api.set_session(mock_session)

        mock_payload = Mock()
        mock_payload.user_id = 123456
        mock_payload.channel_id = 111111
        mock_payload.emoji = Mock()
        mock_payload.emoji.name = "👍"

        # Act
        await api.process_reaction_event(mock_payload, "REACTION_ADD")

        # Assert
        mock_session.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_message_event(self, api):
        """Test processing message event."""
        # Arrange
        mock_session = AsyncMock(spec=aiohttp.ClientSession)
        mock_response = AsyncMock()
        mock_response.status = 202
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)
        mock_session.post.return_value = mock_response

        api.set_session(mock_session)

        mock_message = Mock()
        mock_message.author.id = 123456
        mock_message.channel.id = 111111

        # Act
        await api.process_message_event(mock_message)

        # Assert
        mock_session.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_attend_event_success(self, api):
        """Test successful event attendance."""
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 201

        # Act
        with patch("requests.post", return_value=mock_response):
            status_code, data = await api.attend_event(123456, "session-key-123")

        # Assert
        assert status_code == 201
        assert data == {}

    @pytest.mark.asyncio
    async def test_attend_event_with_error_response(self, api):
        """Test event attendance with error response."""
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"error": "Invalid session key"}

        # Act
        with patch("requests.post", return_value=mock_response):
            status_code, data = await api.attend_event(123456, "invalid-key")

        # Assert
        assert status_code == 400
        assert "error" in data

    @pytest.mark.asyncio
    async def test_sync_channels_success(self, api):
        """Test successful channel sync."""
        # Arrange
        mock_session = AsyncMock(spec=aiohttp.ClientSession)
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"synced": True})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)
        mock_session.post.return_value = mock_response

        api.set_session(mock_session)

        channels = [{"id": 123, "name": "general"}]

        # Act
        result = await api.sync_channels(channels)

        # Assert
        assert result == 200

    @pytest.mark.asyncio
    async def test_update_cohort_stats_success(self, api):
        """Test successful cohort stats update."""
        # Arrange
        mock_session = AsyncMock(spec=aiohttp.ClientSession)
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"updated_cohorts": ["cohort1", "cohort2"]})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)
        mock_session.put.return_value = mock_response

        api.set_session(mock_session)

        # Act
        updated_cohorts, error = await api.update_cohort_stats(123456, "test-stat-url", "cohort1")

        # Assert
        assert updated_cohorts == ["cohort1", "cohort2"]
        assert error is None

    @pytest.mark.asyncio
    async def test_update_cohort_stats_error(self, api):
        """Test cohort stats update with error."""
        # Arrange
        mock_session = AsyncMock(spec=aiohttp.ClientSession)
        mock_response = AsyncMock()
        mock_response.status = 400
        mock_response.json = AsyncMock(return_value={"error": "Invalid cohort"})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)
        mock_session.put.return_value = mock_response

        api.set_session(mock_session)

        # Act
        updated_cohorts, error = await api.update_cohort_stats(123456, "test-stat-url")

        # Assert
        assert updated_cohorts is None
        assert "message" in error

    @pytest.mark.asyncio
    async def test_get_cohort_stats_success(self, api):
        """Test getting cohort stats successfully."""
        # Arrange
        mock_session = AsyncMock(spec=aiohttp.ClientSession)
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"stats": "data"})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)
        mock_session.get.return_value = mock_response

        api.set_session(mock_session)

        # Act
        result = await api.get_cohort_stats(discord_id=123456)

        # Assert
        assert result == {"stats": "data"}

    @pytest.mark.asyncio
    async def test_get_cohort_stats_error(self, api):
        """Test getting cohort stats with error."""
        # Arrange
        mock_session = AsyncMock(spec=aiohttp.ClientSession)
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.json = AsyncMock(return_value={"error": "Server error"})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)
        mock_session.get.return_value = mock_response

        api.set_session(mock_session)

        # Act
        result = await api.get_cohort_stats()

        # Assert
        assert result is None

    @pytest.mark.asyncio
    async def test_get_school_email_verification_url_success(self, api):
        """Test getting school email verification URL successfully."""
        # Arrange
        mock_session = AsyncMock(spec=aiohttp.ClientSession)
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"url": "https://verify.com"})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)
        mock_session.post.return_value = mock_response

        api.set_session(mock_session)

        # Act
        result = await api.get_school_email_verification_url(123456, "test@uw.edu")

        # Assert
        assert result is True

    @pytest.mark.asyncio
    async def test_get_school_email_verification_url_error(self, api):
        """Test getting school email verification URL with error."""
        # Arrange
        mock_session = AsyncMock(spec=aiohttp.ClientSession)
        mock_response = AsyncMock()
        mock_response.status = 400
        mock_response.json = AsyncMock(return_value={"error": "Invalid email"})

        # Create a proper async context manager mock
        mock_ctx_manager = AsyncMock()
        mock_ctx_manager.__aenter__ = AsyncMock(return_value=mock_response)
        mock_ctx_manager.__aexit__ = AsyncMock(return_value=False)
        mock_session.post.return_value = mock_ctx_manager

        api.set_session(mock_session)

        # Act
        result = await api.get_school_email_verification_url(123456, "invalid@example.com")

        # Assert
        assert result is None

    @pytest.mark.asyncio
    async def test_get_cohort_metadata_success(self, api):
        """Test getting cohort metadata successfully."""
        # Arrange
        mock_session = AsyncMock(spec=aiohttp.ClientSession)
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"cohorts": ["cohort1", "cohort2"]})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)
        mock_session.get.return_value = mock_response

        api.set_session(mock_session)

        # Act
        result = await api.get_cohort_metadata()

        # Assert
        assert result == {"cohorts": ["cohort1", "cohort2"]}

    @pytest.mark.asyncio
    async def test_upload_cohort_metadata_success(self, api):
        """Test uploading cohort metadata successfully."""
        # Arrange
        mock_session = AsyncMock(spec=aiohttp.ClientSession)
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"success": True})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)
        mock_session.post.return_value = mock_response

        api.set_session(mock_session)

        data = {"cohorts": ["cohort1"]}

        # Act
        result = await api.upload_cohort_metadata(data)

        # Assert
        assert result == {"success": True}
