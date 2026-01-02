"""Tests for UselessAPIs."""

from unittest.mock import Mock, patch

import pytest
import requests
from APIs.UselessAPIs import UselessAPIs


class TestUselessAPIs:
    """Test suite for UselessAPIs."""

    @pytest.fixture
    def api(self):
        """Create a UselessAPIs instance for testing."""
        return UselessAPIs()

    def test_useless_facts_success(self, api):
        """Test getting useless facts successfully."""
        # Arrange
        mock_response = Mock()
        mock_response.json.return_value = {"text": "Bananas are berries, but strawberries are not."}

        # Act
        with patch("requests.get", return_value=mock_response) as mock_get:
            result = api.useless_facts()

        # Assert
        mock_get.assert_called_once_with("https://uselessfacts.jsph.pl/api/v2/facts/random")
        assert result == "Bananas are berries, but strawberries are not."

    def test_useless_facts_different_fact(self, api):
        """Test getting different useless fact."""
        # Arrange
        mock_response = Mock()
        mock_response.json.return_value = {"text": "A group of flamingos is called a flamboyance."}

        # Act
        with patch("requests.get", return_value=mock_response):
            result = api.useless_facts()

        # Assert
        assert result == "A group of flamingos is called a flamboyance."

    def test_useless_facts_with_long_text(self, api):
        """Test getting useless fact with long text."""
        # Arrange
        long_fact = "This is a very long useless fact that contains a lot of information about something completely useless and unnecessary."
        mock_response = Mock()
        mock_response.json.return_value = {"text": long_fact}

        # Act
        with patch("requests.get", return_value=mock_response):
            result = api.useless_facts()

        # Assert
        assert result == long_fact

    def test_kanye_quote_success(self, api):
        """Test getting Kanye quote successfully."""
        # Arrange
        mock_response = Mock()
        mock_response.json.return_value = {"quote": "I am a god"}

        # Act
        with patch("requests.get", return_value=mock_response) as mock_get:
            result = api.kanye_quote()

        # Assert
        mock_get.assert_called_once_with("https://api.kanye.rest/")
        assert result == "I am a god"

    def test_kanye_quote_different_quote(self, api):
        """Test getting different Kanye quote."""
        # Arrange
        mock_response = Mock()
        mock_response.json.return_value = {
            "quote": "Believe in your flyness...conquer your shyness."
        }

        # Act
        with patch("requests.get", return_value=mock_response):
            result = api.kanye_quote()

        # Assert
        assert result == "Believe in your flyness...conquer your shyness."

    def test_kanye_quote_with_special_characters(self, api):
        """Test getting Kanye quote with special characters."""
        # Arrange
        mock_response = Mock()
        mock_response.json.return_value = {"quote": "I'm nice at ping pong"}

        # Act
        with patch("requests.get", return_value=mock_response):
            result = api.kanye_quote()

        # Assert
        assert result == "I'm nice at ping pong"

    def test_cat_fact_success(self, api):
        """Test getting cat fact successfully."""
        # Arrange
        mock_response = Mock()
        mock_response.json.return_value = {"fact": "Cats sleep 70% of their lives."}

        # Act
        with patch("requests.get", return_value=mock_response) as mock_get:
            result = api.cat_fact()

        # Assert
        mock_get.assert_called_once_with("https://catfact.ninja/fact")
        assert result == "Cats sleep 70% of their lives."

    def test_cat_fact_different_fact(self, api):
        """Test getting different cat fact."""
        # Arrange
        mock_response = Mock()
        mock_response.json.return_value = {"fact": "A group of cats is called a clowder."}

        # Act
        with patch("requests.get", return_value=mock_response):
            result = api.cat_fact()

        # Assert
        assert result == "A group of cats is called a clowder."

    def test_cat_fact_with_long_fact(self, api):
        """Test getting cat fact with long text."""
        # Arrange
        long_fact = "Cats have over 20 vocalizations, including the purr, meow, hiss, growl, squeak, chirp, click, and many more."
        mock_response = Mock()
        mock_response.json.return_value = {"fact": long_fact}

        # Act
        with patch("requests.get", return_value=mock_response):
            result = api.cat_fact()

        # Assert
        assert result == long_fact

    def test_useless_facts_http_error(self, api):
        """Test useless facts with HTTP error."""
        # Arrange
        mock_response = Mock()
        mock_response.json.side_effect = requests.exceptions.JSONDecodeError("Error", "", 0)

        # Act & Assert
        with patch("requests.get", return_value=mock_response):
            with pytest.raises(requests.exceptions.JSONDecodeError):
                api.useless_facts()

    def test_kanye_quote_http_error(self, api):
        """Test Kanye quote with HTTP error."""
        # Arrange
        mock_response = Mock()
        mock_response.json.side_effect = requests.exceptions.JSONDecodeError("Error", "", 0)

        # Act & Assert
        with patch("requests.get", return_value=mock_response):
            with pytest.raises(requests.exceptions.JSONDecodeError):
                api.kanye_quote()

    def test_cat_fact_http_error(self, api):
        """Test cat fact with HTTP error."""
        # Arrange
        mock_response = Mock()
        mock_response.json.side_effect = requests.exceptions.JSONDecodeError("Error", "", 0)

        # Act & Assert
        with patch("requests.get", return_value=mock_response):
            with pytest.raises(requests.exceptions.JSONDecodeError):
                api.cat_fact()
