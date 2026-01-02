"""Tests for BotContext settings."""

import os
from unittest.mock import AsyncMock, MagicMock

import pytest


class TestBotContext:
    """Test suite for BotContext class."""

    def test_initialization_with_env_vars(self, bot_context, mock_env_vars):
        """Test BotContext initializes correctly with environment variables."""
        # Arrange & Act - done in fixtures

        # Assert
        assert bot_context.token == "test_token_123"
        assert bot_context.swecc_server == 123456789
        assert bot_context.admin_channel == 111111111
        assert bot_context.transcripts_channel == 222222222
        assert bot_context.resume_channel == 333333333
        assert bot_context.reading_group_channel == 444444444
        assert bot_context.cohort_category_id == 555555555
        assert bot_context.verified_role_id == 666666666
        assert bot_context.officer_role_id == 777777777
        assert bot_context.verified_email_role_id == 888888888
        assert bot_context.prefix == "!"

    def test_ephemeral_default(self, bot_context):
        """Test ephemeral is set to True by default."""
        # Arrange & Act - done in fixtures

        # Assert
        assert bot_context.ephemeral is True

    def test_badwords_list_populated(self, bot_context):
        """Test badwords list is properly populated."""
        # Arrange & Act - done in fixtures

        # Assert
        assert isinstance(bot_context.badwords, list)
        assert len(bot_context.badwords) > 0
        assert "ticket" in bot_context.badwords
        assert "free.*macbook" in bot_context.badwords
        assert "@everyone" in bot_context.badwords
        assert r"\$" in bot_context.badwords

    def test_badwords_contains_expected_patterns(self, bot_context):
        """Test badwords list contains expected spam patterns."""
        # Arrange
        expected_patterns = [
            "ticket",
            "free.*macbook",
            "macbook.*free",
            r"\$",
            "seat.*section",
            "help.*offer",
            "lumen field",
            "personal assistant",
            "run(ning)?.*errands",
            "free.*gift.*card",
            "free.*visa",
            "free.*paypal",
            "work.*from.*home",
            "earn.*money.*fast",
            "crypto.*investment",
            "make.*money.*online",
            "air*free",
            "@everyone",
        ]

        # Act & Assert
        for pattern in expected_patterns:
            assert pattern in bot_context.badwords

    def test_do_not_timeout_initialized_as_set(self, bot_context):
        """Test do_not_timeout is initialized as an empty set."""
        # Arrange & Act - done in fixtures

        # Assert
        assert isinstance(bot_context.do_not_timeout, set)
        assert len(bot_context.do_not_timeout) == 0

    @pytest.mark.asyncio
    async def test_log_sends_message_to_transcripts_channel(
        self, bot_context, mock_message, mock_channel
    ):
        """Test log method sends message to transcripts channel."""
        # Arrange
        mock_message.guild.get_channel = MagicMock(return_value=mock_channel)
        log_message = "Test log message"

        # Act
        await bot_context.log(mock_message, log_message)

        # Assert
        mock_message.guild.get_channel.assert_called_once_with(bot_context.transcripts_channel)
        mock_channel.send.assert_called_once_with(log_message)

    @pytest.mark.asyncio
    async def test_log_with_member_context(self, bot_context, mock_member, mock_channel):
        """Test log method works with member context."""
        # Arrange
        mock_member.guild.get_channel = MagicMock(return_value=mock_channel)
        log_message = f"{mock_member.display_name} has joined the server."

        # Act
        await bot_context.log(mock_member, log_message)

        # Assert
        mock_member.guild.get_channel.assert_called_once_with(bot_context.transcripts_channel)
        mock_channel.send.assert_called_once_with(log_message)

    def test_channel_ids_are_integers(self, bot_context):
        """Test all channel IDs are properly converted to integers."""
        # Arrange & Act - done in fixtures

        # Assert
        assert isinstance(bot_context.swecc_server, int)
        assert isinstance(bot_context.admin_channel, int)
        assert isinstance(bot_context.transcripts_channel, int)
        assert isinstance(bot_context.resume_channel, int)
        assert isinstance(bot_context.reading_group_channel, int)
        assert isinstance(bot_context.cohort_category_id, int)

    def test_role_ids_are_integers(self, bot_context):
        """Test all role IDs are properly converted to integers."""
        # Arrange & Act - done in fixtures

        # Assert
        assert isinstance(bot_context.verified_role_id, int)
        assert isinstance(bot_context.officer_role_id, int)
        assert isinstance(bot_context.verified_email_role_id, int)

    def test_prefix_is_string(self, bot_context):
        """Test prefix is a string."""
        # Arrange & Act - done in fixtures

        # Assert
        assert isinstance(bot_context.prefix, str)

    def test_token_is_string(self, bot_context):
        """Test token is a string."""
        # Arrange & Act - done in fixtures

        # Assert
        assert isinstance(bot_context.token, str)
