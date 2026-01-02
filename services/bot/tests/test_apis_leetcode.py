"""Tests for LeetcodeAPI."""

from unittest.mock import Mock, patch

import pytest
import requests
from APIs.LeetcodeAPI import LeetcodeAPI


class TestLeetcodeAPI:
    """Test suite for LeetcodeAPI."""

    @pytest.fixture
    def api(self):
        """Create a LeetcodeAPI instance for testing."""
        return LeetcodeAPI()

    def test_init(self, api):
        """Test API initialization."""
        # Arrange & Act - done in fixture
        # Assert
        assert api.url == "https://leetcode.com/graphql/"

    def test_get_leetcode_daily_success(self, api):
        """Test getting daily LeetCode problem successfully."""
        # Arrange
        mock_response_data = {
            "data": {
                "activeDailyCodingChallengeQuestion": {
                    "link": "/problems/two-sum",
                    "question": {
                        "difficulty": "Easy",
                        "title": "Two Sum",
                        "topicTags": [{"name": "Array"}, {"name": "Hash Table"}],
                    },
                }
            }
        }
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data

        # Act
        with patch("requests.post", return_value=mock_response) as mock_post:
            result = api.get_leetcode_daily()

        # Assert
        mock_post.assert_called_once()
        assert result is not None
        assert result["link"] == "https://leetcode.com/problems/two-sum"
        assert result["question"]["difficulty"] == "Easy"
        assert result["question"]["title"] == "Two Sum"
        assert len(result["question"]["topicTags"]) == 2
        assert "Array" in result["question"]["topicTags"]
        assert "Hash Table" in result["question"]["topicTags"]

    def test_get_leetcode_daily_with_medium_difficulty(self, api):
        """Test getting daily LeetCode problem with medium difficulty."""
        # Arrange
        mock_response_data = {
            "data": {
                "activeDailyCodingChallengeQuestion": {
                    "link": "/problems/add-two-numbers",
                    "question": {
                        "difficulty": "Medium",
                        "title": "Add Two Numbers",
                        "topicTags": [{"name": "Linked List"}, {"name": "Math"}],
                    },
                }
            }
        }
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data

        # Act
        with patch("requests.post", return_value=mock_response):
            result = api.get_leetcode_daily()

        # Assert
        assert result["question"]["difficulty"] == "Medium"
        assert result["question"]["title"] == "Add Two Numbers"

    def test_get_leetcode_daily_with_hard_difficulty(self, api):
        """Test getting daily LeetCode problem with hard difficulty."""
        # Arrange
        mock_response_data = {
            "data": {
                "activeDailyCodingChallengeQuestion": {
                    "link": "/problems/median-of-two-sorted-arrays",
                    "question": {
                        "difficulty": "Hard",
                        "title": "Median of Two Sorted Arrays",
                        "topicTags": [{"name": "Array"}, {"name": "Binary Search"}],
                    },
                }
            }
        }
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data

        # Act
        with patch("requests.post", return_value=mock_response):
            result = api.get_leetcode_daily()

        # Assert
        assert result["question"]["difficulty"] == "Hard"

    def test_get_leetcode_daily_with_no_tags(self, api):
        """Test getting daily LeetCode problem with no topic tags."""
        # Arrange
        mock_response_data = {
            "data": {
                "activeDailyCodingChallengeQuestion": {
                    "link": "/problems/test-problem",
                    "question": {"difficulty": "Easy", "title": "Test Problem", "topicTags": []},
                }
            }
        }
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data

        # Act
        with patch("requests.post", return_value=mock_response):
            result = api.get_leetcode_daily()

        # Assert
        assert result["question"]["topicTags"] == []

    def test_get_leetcode_daily_http_error(self, api):
        """Test handling HTTP error when fetching daily problem."""
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 500

        # Act
        with patch("requests.post", return_value=mock_response):
            result = api.get_leetcode_daily()

        # Assert
        assert result is None

    def test_get_leetcode_daily_not_found(self, api):
        """Test handling 404 error when fetching daily problem."""
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 404

        # Act
        with patch("requests.post", return_value=mock_response):
            result = api.get_leetcode_daily()

        # Assert
        assert result is None

    def test_get_leetcode_daily_request_payload(self, api):
        """Test that the correct GraphQL query is sent."""
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "activeDailyCodingChallengeQuestion": {
                    "link": "/problems/test",
                    "question": {"difficulty": "Easy", "title": "Test", "topicTags": []},
                }
            }
        }

        # Act
        with patch("requests.post", return_value=mock_response) as mock_post:
            api.get_leetcode_daily()

        # Assert
        call_args = mock_post.call_args
        assert call_args[0][0] == api.url
        payload = call_args[1]["json"]
        assert "query" in payload
        assert "activeDailyCodingChallengeQuestion" in payload["query"]
        assert payload["operationName"] == "questionOfToday"
