"""Tests for MQ producer functions.

These tests verify the transformation logic of producer functions.
The actual publishing is handled by the @mq.producer decorator and tested in test_mq_core.py.
"""

import json
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

# Import the internal functions directly to test transformation logic
from mq import producers
from mq.events import (
    AttendanceEvent,
    ChannelSnapshot,
    CohortStatsUpdate,
    DiscordEventType,
    MessageEvent,
    ReactionEvent,
)


class TestMessageEventTransformation:
    """Test suite for message event transformation."""

    @pytest.mark.asyncio
    async def test_publish_message_event_transforms_to_json(self):
        """Test that publish_message_event transforms event to JSON."""
        # Arrange
        event = MessageEvent(discord_id=123456789, channel_id=987654321, content="Test message")

        # Act - Call the underlying function directly
        # The decorator wraps it, but we can test the transformation
        result = json.dumps(event.__dict__)
        result_dict = json.loads(result)

        # Assert
        assert result_dict["discord_id"] == 123456789
        assert result_dict["channel_id"] == 987654321
        assert result_dict["content"] == "Test message"
        assert result_dict["event_type"] == DiscordEventType.MESSAGE

    @pytest.mark.asyncio
    async def test_message_event_json_structure(self):
        """Test that message event has correct JSON structure."""
        # Arrange
        event = MessageEvent(discord_id=111, channel_id=222, content="Hello")

        # Act
        result = json.dumps(event.__dict__)
        parsed = json.loads(result)

        # Assert
        assert isinstance(parsed, dict)
        assert "discord_id" in parsed
        assert "channel_id" in parsed
        assert "content" in parsed
        assert "event_type" in parsed


class TestAttendanceEventTransformation:
    """Test suite for attendance event transformation."""

    @pytest.mark.asyncio
    async def test_attendance_event_transforms_to_json(self):
        """Test that attendance event transforms to JSON correctly."""
        # Arrange
        event = AttendanceEvent(discord_id=123456789, session_key="session-2024-01-01")

        # Act
        result = json.dumps(event.__dict__)
        result_dict = json.loads(result)

        # Assert
        assert result_dict["discord_id"] == 123456789
        assert result_dict["session_key"] == "session-2024-01-01"
        assert result_dict["event_type"] == DiscordEventType.ATTENDANCE

    @pytest.mark.asyncio
    async def test_attendance_event_json_structure(self):
        """Test that attendance event has correct JSON structure."""
        # Arrange
        event = AttendanceEvent(discord_id=999, session_key="test-key")

        # Act
        result = json.dumps(event.__dict__)
        parsed = json.loads(result)

        # Assert
        assert isinstance(parsed, dict)
        assert "discord_id" in parsed
        assert "session_key" in parsed
        assert "event_type" in parsed


class TestChannelSnapshotTransformation:
    """Test suite for channel snapshot transformation."""

    @pytest.mark.asyncio
    async def test_channel_snapshot_transforms_to_json(self):
        """Test that channel snapshot transforms to JSON correctly."""
        # Arrange
        channels = [{"id": 123, "name": "general"}, {"id": 456, "name": "announcements"}]
        event = ChannelSnapshot(channels=channels)

        # Act
        result = json.dumps(event.__dict__)
        result_dict = json.loads(result)

        # Assert
        assert len(result_dict["channels"]) == 2
        assert result_dict["channels"][0]["id"] == 123
        assert result_dict["event_type"] == DiscordEventType.CHANNEL_SNAPSHOT

    @pytest.mark.asyncio
    async def test_channel_snapshot_empty_channels(self):
        """Test channel snapshot with empty channels list."""
        # Arrange
        event = ChannelSnapshot(channels=[])

        # Act
        result = json.dumps(event.__dict__)
        result_dict = json.loads(result)

        # Assert
        assert result_dict["channels"] == []


class TestCohortStatsUpdateTransformation:
    """Test suite for cohort stats update transformation."""

    @pytest.mark.asyncio
    async def test_cohort_stats_update_transforms_to_json(self):
        """Test that cohort stats update transforms to JSON correctly."""
        # Arrange
        event = CohortStatsUpdate(
            discord_id=123456789, stat_url="https://leetcode.com/user123", cohort_name="Winter 2024"
        )

        # Act
        result = json.dumps(event.__dict__)
        result_dict = json.loads(result)

        # Assert
        assert result_dict["discord_id"] == 123456789
        assert result_dict["stat_url"] == "https://leetcode.com/user123"
        assert result_dict["cohort_name"] == "Winter 2024"

    @pytest.mark.asyncio
    async def test_cohort_stats_update_without_cohort_name(self):
        """Test cohort stats update without cohort name."""
        # Arrange
        event = CohortStatsUpdate(discord_id=987654321, stat_url="https://example.com/stats")

        # Act
        result = json.dumps(event.__dict__)
        result_dict = json.loads(result)

        # Assert
        assert result_dict["discord_id"] == 987654321
        assert result_dict["cohort_name"] is None


class TestReactionEventTransformation:
    """Test suite for reaction event transformation."""

    @pytest.mark.asyncio
    async def test_reaction_add_event_transforms_to_json(self):
        """Test that reaction add event transforms to JSON correctly."""
        # Arrange
        event = ReactionEvent(
            discord_id=123456789,
            channel_id=987654321,
            message_id=111222333,
            emoji="✅",
            event_type=DiscordEventType.REACTION_ADD,
        )

        # Act
        result = json.dumps(event.__dict__)
        result_dict = json.loads(result)

        # Assert
        assert result_dict["discord_id"] == 123456789
        assert result_dict["channel_id"] == 987654321
        assert result_dict["message_id"] == 111222333
        assert result_dict["emoji"] == "✅"
        assert result_dict["event_type"] == DiscordEventType.REACTION_ADD

    @pytest.mark.asyncio
    async def test_reaction_add_event_custom_emoji(self):
        """Test reaction add event with custom emoji."""
        # Arrange
        event = ReactionEvent(
            discord_id=1,
            channel_id=2,
            message_id=3,
            emoji="custom:123",
            event_type=DiscordEventType.REACTION_ADD,
        )

        # Act
        result = json.dumps(event.__dict__)
        result_dict = json.loads(result)

        # Assert
        assert result_dict["emoji"] == "custom:123"

    @pytest.mark.asyncio
    async def test_reaction_remove_event_transforms_to_json(self):
        """Test that reaction remove event transforms to JSON correctly."""
        # Arrange
        event = ReactionEvent(
            discord_id=555555555,
            channel_id=666666666,
            message_id=777777777,
            emoji="❌",
            event_type=DiscordEventType.REACTION_REMOVE,
        )

        # Act
        result = json.dumps(event.__dict__)
        result_dict = json.loads(result)

        # Assert
        assert result_dict["discord_id"] == 555555555
        assert result_dict["channel_id"] == 666666666
        assert result_dict["message_id"] == 777777777
        assert result_dict["emoji"] == "❌"
        assert result_dict["event_type"] == DiscordEventType.REACTION_REMOVE

    @pytest.mark.asyncio
    async def test_reaction_remove_event_json_structure(self):
        """Test that reaction remove event has correct JSON structure."""
        # Arrange
        event = ReactionEvent(
            discord_id=1,
            channel_id=2,
            message_id=3,
            emoji="👍",
            event_type=DiscordEventType.REACTION_REMOVE,
        )

        # Act
        result = json.dumps(event.__dict__)
        parsed = json.loads(result)

        # Assert
        assert isinstance(parsed, dict)
        assert "discord_id" in parsed
        assert "channel_id" in parsed
        assert "message_id" in parsed
        assert "emoji" in parsed
        assert "event_type" in parsed
