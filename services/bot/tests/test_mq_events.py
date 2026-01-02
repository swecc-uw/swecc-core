"""Tests for MQ event models."""

import json

import pytest
from mq.events import (
    AttendanceEvent,
    ChannelSnapshot,
    CohortStatsUpdate,
    DiscordEventType,
    MessageEvent,
    ReactionEvent,
)


class TestDiscordEventType:
    """Test suite for DiscordEventType enum."""

    def test_event_type_values(self):
        """Test that all event types have correct string values."""
        # Arrange & Act & Assert
        assert DiscordEventType.MESSAGE == "message"
        assert DiscordEventType.ATTENDANCE == "attendance"
        assert DiscordEventType.CHANNEL_SNAPSHOT == "channel_snapshot"
        assert DiscordEventType.COHORT_STATS_UPDATE == "cohort_stats_update"
        assert DiscordEventType.REACTION_ADD == "reaction_add"
        assert DiscordEventType.REACTION_REMOVE == "reaction_remove"

    def test_event_type_is_string_enum(self):
        """Test that DiscordEventType is a string enum."""
        # Arrange & Act & Assert
        assert isinstance(DiscordEventType.MESSAGE, str)
        assert isinstance(DiscordEventType.ATTENDANCE, str)


class TestMessageEvent:
    """Test suite for MessageEvent dataclass."""

    def test_message_event_creation(self):
        """Test creating a MessageEvent with required fields."""
        # Arrange & Act
        event = MessageEvent(discord_id=123456789, channel_id=987654321, content="Hello, world!")

        # Assert
        assert event.discord_id == 123456789
        assert event.channel_id == 987654321
        assert event.content == "Hello, world!"
        assert event.event_type == DiscordEventType.MESSAGE

    def test_message_event_default_event_type(self):
        """Test that MessageEvent has correct default event_type."""
        # Arrange & Act
        event = MessageEvent(discord_id=1, channel_id=2, content="test")

        # Assert
        assert event.event_type == DiscordEventType.MESSAGE

    def test_message_event_serialization(self):
        """Test that MessageEvent can be serialized to dict."""
        # Arrange
        event = MessageEvent(discord_id=111, channel_id=222, content="test message")

        # Act
        event_dict = event.__dict__

        # Assert
        assert event_dict["discord_id"] == 111
        assert event_dict["channel_id"] == 222
        assert event_dict["content"] == "test message"
        assert event_dict["event_type"] == DiscordEventType.MESSAGE


class TestAttendanceEvent:
    """Test suite for AttendanceEvent dataclass."""

    def test_attendance_event_creation(self):
        """Test creating an AttendanceEvent."""
        # Arrange & Act
        event = AttendanceEvent(discord_id=123456789, session_key="session-2024-01-01")

        # Assert
        assert event.discord_id == 123456789
        assert event.session_key == "session-2024-01-01"
        assert event.event_type == DiscordEventType.ATTENDANCE

    def test_attendance_event_default_event_type(self):
        """Test that AttendanceEvent has correct default event_type."""
        # Arrange & Act
        event = AttendanceEvent(discord_id=1, session_key="key")

        # Assert
        assert event.event_type == DiscordEventType.ATTENDANCE


class TestChannelSnapshot:
    """Test suite for ChannelSnapshot dataclass."""

    def test_channel_snapshot_creation(self):
        """Test creating a ChannelSnapshot."""
        # Arrange
        channels = [{"id": 123, "name": "general"}, {"id": 456, "name": "announcements"}]

        # Act
        event = ChannelSnapshot(channels=channels)

        # Assert
        assert len(event.channels) == 2
        assert event.channels[0]["id"] == 123
        assert event.channels[1]["name"] == "announcements"
        assert event.event_type == DiscordEventType.CHANNEL_SNAPSHOT

    def test_channel_snapshot_empty_channels(self):
        """Test creating a ChannelSnapshot with empty channels list."""
        # Arrange & Act
        event = ChannelSnapshot(channels=[])

        # Assert
        assert event.channels == []
        assert event.event_type == DiscordEventType.CHANNEL_SNAPSHOT


class TestCohortStatsUpdate:
    """Test suite for CohortStatsUpdate dataclass."""

    def test_cohort_stats_update_creation(self):
        """Test creating a CohortStatsUpdate with all fields."""
        # Arrange & Act
        event = CohortStatsUpdate(
            discord_id=123456789, stat_url="https://leetcode.com/user123", cohort_name="Winter 2024"
        )

        # Assert
        assert event.discord_id == 123456789
        assert event.stat_url == "https://leetcode.com/user123"
        assert event.cohort_name == "Winter 2024"
        assert event.event_type == DiscordEventType.COHORT_STATS_UPDATE

    def test_cohort_stats_update_without_cohort_name(self):
        """Test creating a CohortStatsUpdate without cohort_name."""
        # Arrange & Act
        event = CohortStatsUpdate(discord_id=987654321, stat_url="https://example.com/stats")

        # Assert
        assert event.discord_id == 987654321
        assert event.stat_url == "https://example.com/stats"
        assert event.cohort_name is None
        assert event.event_type == DiscordEventType.COHORT_STATS_UPDATE


class TestReactionEvent:
    """Test suite for ReactionEvent dataclass."""

    def test_reaction_event_creation_add(self):
        """Test creating a ReactionEvent for reaction add."""
        # Arrange & Act
        event = ReactionEvent(
            discord_id=123456789,
            channel_id=987654321,
            message_id=111222333,
            emoji="✅",
            event_type=DiscordEventType.REACTION_ADD,
        )

        # Assert
        assert event.discord_id == 123456789
        assert event.channel_id == 987654321
        assert event.message_id == 111222333
        assert event.emoji == "✅"
        assert event.event_type == DiscordEventType.REACTION_ADD

    def test_reaction_event_creation_remove(self):
        """Test creating a ReactionEvent for reaction remove."""
        # Arrange & Act
        event = ReactionEvent(
            discord_id=555555555,
            channel_id=666666666,
            message_id=777777777,
            emoji="❌",
            event_type=DiscordEventType.REACTION_REMOVE,
        )

        # Assert
        assert event.discord_id == 555555555
        assert event.channel_id == 666666666
        assert event.message_id == 777777777
        assert event.emoji == "❌"
        assert event.event_type == DiscordEventType.REACTION_REMOVE

    def test_reaction_event_custom_emoji(self):
        """Test creating a ReactionEvent with custom emoji."""
        # Arrange & Act
        event = ReactionEvent(
            discord_id=1,
            channel_id=2,
            message_id=3,
            emoji="custom_emoji:123456",
            event_type=DiscordEventType.REACTION_ADD,
        )

        # Assert
        assert event.emoji == "custom_emoji:123456"
