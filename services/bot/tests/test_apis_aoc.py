"""Tests for AdventOfCodeAPI."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, Mock, patch

import pytest
import requests
from APIs.AdventOfCodeAPI import AdventOfCodeAPI


class TestAdventOfCodeAPI:
    """Test suite for AdventOfCodeAPI."""

    @pytest.fixture
    def api(self):
        """Create an AdventOfCodeAPI instance for testing."""
        with patch.dict(
            "os.environ",
            {"AOC_LEADERBOARD_ID": "test_leaderboard_123", "AOC_SESSION": "test_session_token"},
        ):
            return AdventOfCodeAPI()

    def test_init(self, api):
        """Test API initialization."""
        # Arrange & Act - done in fixture
        # Assert
        assert api.leaderboard_id == "test_leaderboard_123"
        assert api.year == datetime.now().year
        assert "test_leaderboard_123" in api.url
        assert api.headers["Cookie"] == "session=test_session_token"
        assert api.cache["last_accessed"] is None
        assert api.cache["data"] is None

    def test_get_leaderboard_url(self, api):
        """Test getting leaderboard URL."""
        # Arrange & Act
        url = api.get_leaderboard_url()

        # Assert
        assert "adventofcode.com" in url
        assert "test_leaderboard_123" in url
        assert str(datetime.now().year) in url

    def test_parse_leaderboard_with_valid_data(self, api):
        """Test parsing leaderboard with valid data."""
        # Arrange
        mock_data = {
            "members": {
                "1": {"name": "Alice", "local_score": 100},
                "2": {"name": "Bob", "local_score": 200},
                "3": {"local_score": 50},  # No name - should be Anonymous
            }
        }

        # Act
        result = api.parse_leaderboard(mock_data)

        # Assert
        assert len(result) == 3
        assert result[0]["name"] == "Bob"
        assert result[0]["local_score"] == 200
        assert result[1]["name"] == "Alice"
        assert result[1]["local_score"] == 100
        assert result[2]["name"] == "Anonymous"
        assert result[2]["local_score"] == 50

    def test_parse_leaderboard_with_empty_members(self, api):
        """Test parsing leaderboard with no members."""
        # Arrange
        mock_data = {"members": {}}

        # Act
        result = api.parse_leaderboard(mock_data)

        # Assert
        assert result == []

    def test_parse_leaderboard_with_missing_members_key(self, api):
        """Test parsing leaderboard with missing members key."""
        # Arrange
        mock_data = {}

        # Act
        result = api.parse_leaderboard(mock_data)

        # Assert
        assert result == []

    @pytest.mark.asyncio
    async def test_get_leaderboard_fresh_fetch(self, api):
        """Test fetching leaderboard when cache is empty."""
        # Arrange
        mock_response_data = {"members": {"1": {"name": "Alice", "local_score": 100}}}
        mock_response = Mock()
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status = Mock()

        # Act
        with patch("requests.get", return_value=mock_response) as mock_get:
            result = await api.get_leaderboard()

        # Assert
        mock_get.assert_called_once_with(api.url, headers=api.headers)
        assert len(result) == 1
        assert result[0]["name"] == "Alice"
        assert api.cache["data"] == result
        assert api.cache["last_accessed"] is not None

    @pytest.mark.asyncio
    async def test_get_leaderboard_uses_cache_when_fresh(self, api):
        """Test that cached data is returned when cache is fresh."""
        # Arrange
        cached_data = [{"name": "Cached", "local_score": 999}]
        api.cache["data"] = cached_data
        api.cache["last_accessed"] = datetime.now() - timedelta(minutes=10)

        # Act
        with patch("requests.get") as mock_get:
            result = await api.get_leaderboard()

        # Assert
        mock_get.assert_not_called()
        assert result == cached_data

    @pytest.mark.asyncio
    async def test_get_leaderboard_refreshes_stale_cache(self, api):
        """Test that stale cache is refreshed."""
        # Arrange
        api.cache["data"] = [{"name": "Old", "local_score": 1}]
        api.cache["last_accessed"] = datetime.now() - timedelta(minutes=20)

        mock_response_data = {"members": {"1": {"name": "New", "local_score": 100}}}
        mock_response = Mock()
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status = Mock()

        # Act
        with patch("requests.get", return_value=mock_response):
            result = await api.get_leaderboard()

        # Assert
        assert result[0]["name"] == "New"
        assert result[0]["local_score"] == 100

    @pytest.mark.asyncio
    async def test_get_leaderboard_handles_http_error(self, api):
        """Test error handling when HTTP request fails."""
        # Arrange
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("404 Not Found")

        # Act & Assert
        with patch("requests.get", return_value=mock_response):
            with pytest.raises(requests.HTTPError):
                await api.get_leaderboard()
