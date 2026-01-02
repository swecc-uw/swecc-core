"""Tests for CalendarAPI."""

from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest
import pytz
import requests
from APIs.CalendarAPI import CalendarAPI


class TestCalendarAPI:
    """Test suite for CalendarAPI."""

    @pytest.fixture
    def api(self):
        """Create a CalendarAPI instance for testing."""
        with patch.dict("os.environ", {"CALENDAR_URL": "https://example.com/calendar.ics"}):
            return CalendarAPI()

    def test_init(self, api):
        """Test API initialization."""
        # Arrange & Act - done in fixture
        # Assert
        assert api.url == "https://example.com/calendar.ics"

    def test_get_url(self, api):
        """Test getting calendar URL."""
        # Arrange & Act
        url = api.get_url()

        # Assert
        assert url == "https://example.com/calendar.ics"

    @pytest.mark.parametrize(
        "day,expected_suffix",
        [
            (1, "1st"),
            (2, "2nd"),
            (3, "3rd"),
            (4, "4th"),
            (11, "11th"),
            (12, "12th"),
            (13, "13th"),
            (21, "21st"),
            (22, "22nd"),
            (23, "23rd"),
            (24, "24th"),
            (30, "30th"),
            (31, "31st"),
        ],
    )
    def test_get_suffix(self, api, day, expected_suffix):
        """Test getting correct suffix for day numbers."""
        # Arrange & Act
        result = api.get_suffix(day)

        # Assert
        assert result == expected_suffix

    def test_format_date(self, api):
        """Test date formatting."""
        # Arrange
        tz = pytz.timezone("America/Los_Angeles")
        start = tz.localize(datetime(2026, 1, 15, 14, 30))
        end = tz.localize(datetime(2026, 1, 15, 16, 0))

        # Act
        result = api.format_date(start, end)

        # Assert
        assert "Thu, Jan 15th" in result
        assert "2:30 PM" in result
        assert "4:00 PM" in result

    def test_format_date_with_leading_zero_hour(self, api):
        """Test date formatting with leading zero in hour."""
        # Arrange
        tz = pytz.timezone("America/Los_Angeles")
        start = tz.localize(datetime(2026, 1, 15, 9, 0))
        end = tz.localize(datetime(2026, 1, 15, 10, 30))

        # Act
        result = api.format_date(start, end)

        # Assert
        assert "9:00 AM" in result  # No leading zero
        assert "10:30 AM" in result

    @pytest.mark.asyncio
    async def test_get_next_meeting_with_simple_event(self, api):
        """Test getting next meeting with a simple non-recurring event."""
        # Arrange
        future_date = datetime.now(pytz.utc) + timedelta(days=1)
        future_date_str = future_date.strftime("%Y%m%dT%H%M%S")

        calendar_text = f"""BEGIN:VCALENDAR
BEGIN:VEVENT
DTSTART;TZID=America/Los_Angeles:{future_date_str}
DTEND;TZID=America/Los_Angeles:{future_date_str}
SUMMARY:Test Meeting
LOCATION:Test Location
DESCRIPTION:Test Description
END:VEVENT
END:VCALENDAR"""

        mock_response = Mock()
        mock_response.text = calendar_text
        mock_response.raise_for_status = Mock()

        # Act
        with patch("requests.get", return_value=mock_response):
            result = await api.get_next_meeting()

        # Assert
        assert isinstance(result, dict)
        assert result["name"] == "Test Meeting"
        assert result["location"] == "Test Location"
        assert result["description"] == "Test Description"

    @pytest.mark.asyncio
    async def test_get_next_meeting_no_upcoming_events(self, api):
        """Test getting next meeting when there are no upcoming events."""
        # Arrange
        past_date = datetime.now(pytz.utc) - timedelta(days=1)
        past_date_str = past_date.strftime("%Y%m%dT%H%M%S")

        calendar_text = f"""BEGIN:VCALENDAR
BEGIN:VEVENT
DTSTART;TZID=America/Los_Angeles:{past_date_str}
DTEND;TZID=America/Los_Angeles:{past_date_str}
SUMMARY:Past Meeting
END:VEVENT
END:VCALENDAR"""

        mock_response = Mock()
        mock_response.text = calendar_text
        mock_response.raise_for_status = Mock()

        # Act
        with patch("requests.get", return_value=mock_response):
            result = await api.get_next_meeting()

        # Assert
        assert result == "No upcoming meetings."

    @pytest.mark.asyncio
    async def test_get_next_meeting_with_recurring_event(self, api):
        """Test getting next meeting with a recurring event."""
        # Arrange
        # Create a recurring event that happens every week
        base_date = datetime.now(pytz.timezone("America/Los_Angeles"))
        # Set to a future date
        future_date = base_date + timedelta(days=7)
        future_date_str = future_date.strftime("%Y%m%dT%H%M%S")

        calendar_text = f"""BEGIN:VCALENDAR
BEGIN:VEVENT
DTSTART;TZID=America/Los_Angeles:{future_date_str}
DTEND;TZID=America/Los_Angeles:{future_date_str}
RRULE:FREQ=WEEKLY;COUNT=5
SUMMARY:Weekly Meeting
LOCATION:Conference Room
DESCRIPTION:Weekly sync
END:VEVENT
END:VCALENDAR"""

        mock_response = Mock()
        mock_response.text = calendar_text
        mock_response.raise_for_status = Mock()

        # Act
        with patch("requests.get", return_value=mock_response):
            result = await api.get_next_meeting()

        # Assert
        assert isinstance(result, dict)
        assert result["name"] == "Weekly Meeting"

    @pytest.mark.asyncio
    async def test_get_next_meeting_handles_http_error(self, api):
        """Test error handling when HTTP request fails."""
        # Arrange
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("404 Not Found")

        # Act & Assert
        with patch("requests.get", return_value=mock_response):
            with pytest.raises(requests.HTTPError):
                await api.get_next_meeting()

    @pytest.mark.asyncio
    async def test_get_next_meeting_with_missing_fields(self, api):
        """Test getting next meeting with missing optional fields."""
        # Arrange
        future_date = datetime.now(pytz.utc) + timedelta(days=1)
        future_date_str = future_date.strftime("%Y%m%dT%H%M%S")

        calendar_text = f"""BEGIN:VCALENDAR
BEGIN:VEVENT
DTSTART;TZID=America/Los_Angeles:{future_date_str}
DTEND;TZID=America/Los_Angeles:{future_date_str}
END:VEVENT
END:VCALENDAR"""

        mock_response = Mock()
        mock_response.text = calendar_text
        mock_response.raise_for_status = Mock()

        # Act
        with patch("requests.get", return_value=mock_response):
            result = await api.get_next_meeting()

        # Assert
        assert isinstance(result, dict)
        assert result["name"] == "No Title"
        assert result["location"] == "No Location"
        assert result["description"] == "No Description"
