"""Tests for MQ consumer functions."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mq.consumers import add_verified_role, loopback
from pika import BasicProperties


class TestLoopbackConsumer:
    """Test suite for loopback consumer."""

    @pytest.mark.asyncio
    async def test_loopback_receives_message(self):
        """Test that loopback consumer receives and logs message."""
        # Arrange
        test_message = b"Test loopback message"
        properties = MagicMock(spec=BasicProperties)

        # Act & Assert - should not raise any exceptions
        with patch("mq.consumers.logging.info") as mock_log:
            await loopback(test_message, properties)
            mock_log.assert_called_once_with(f"Loopback consumer received message: {test_message}")

    @pytest.mark.asyncio
    async def test_loopback_with_empty_message(self):
        """Test loopback consumer with empty message."""
        # Arrange
        test_message = b""
        properties = MagicMock(spec=BasicProperties)

        # Act & Assert
        with patch("mq.consumers.logging.info") as mock_log:
            await loopback(test_message, properties)
            mock_log.assert_called_once()

    @pytest.mark.asyncio
    async def test_loopback_with_json_message(self):
        """Test loopback consumer with JSON message."""
        # Arrange
        test_message = b'{"key": "value", "number": 123}'
        properties = MagicMock(spec=BasicProperties)

        # Act & Assert
        with patch("mq.consumers.logging.info") as mock_log:
            await loopback(test_message, properties)
            mock_log.assert_called_once()


class TestAddVerifiedRoleConsumer:
    """Test suite for add_verified_role consumer."""

    @pytest.mark.asyncio
    async def test_add_verified_role_success(self, bot_context):
        """Test adding verified role to a member successfully."""
        # Arrange
        discord_id = 987654321
        message_body = str(discord_id).encode("utf-8")
        properties = MagicMock(spec=BasicProperties)

        # Mock Discord client and objects
        mock_client = MagicMock()
        mock_guild = MagicMock()
        mock_member = MagicMock()
        mock_role = MagicMock()

        mock_client.get_guild.return_value = mock_guild
        mock_guild.get_member.return_value = mock_member
        mock_guild.get_role.return_value = mock_role
        mock_member.add_roles = AsyncMock()

        # Act
        await add_verified_role(message_body, properties, mock_client, bot_context)

        # Assert
        mock_client.get_guild.assert_called_once_with(bot_context.swecc_server)
        mock_guild.get_member.assert_called_once_with(discord_id)
        mock_guild.get_role.assert_called_once_with(bot_context.verified_email_role_id)
        mock_member.add_roles.assert_called_once_with(mock_role)

    @pytest.mark.asyncio
    async def test_add_verified_role_decodes_message(self, bot_context):
        """Test that consumer properly decodes message to get discord_id."""
        # Arrange
        discord_id = 123456789
        message_body = str(discord_id).encode("utf-8")
        properties = MagicMock(spec=BasicProperties)

        mock_client = MagicMock()
        mock_guild = MagicMock()
        mock_member = MagicMock()
        mock_role = MagicMock()

        mock_client.get_guild.return_value = mock_guild
        mock_guild.get_member.return_value = mock_member
        mock_guild.get_role.return_value = mock_role
        mock_member.add_roles = AsyncMock()

        # Act
        await add_verified_role(message_body, properties, mock_client, bot_context)

        # Assert
        # Verify the discord_id was correctly parsed
        mock_guild.get_member.assert_called_once_with(discord_id)

    @pytest.mark.asyncio
    async def test_add_verified_role_uses_correct_role_id(self, bot_context):
        """Test that consumer uses correct verified email role ID from context."""
        # Arrange
        discord_id = 111222333
        message_body = str(discord_id).encode("utf-8")
        properties = MagicMock(spec=BasicProperties)

        mock_client = MagicMock()
        mock_guild = MagicMock()
        mock_member = MagicMock()
        mock_role = MagicMock()

        mock_client.get_guild.return_value = mock_guild
        mock_guild.get_member.return_value = mock_member
        mock_guild.get_role.return_value = mock_role
        mock_member.add_roles = AsyncMock()

        # Act
        await add_verified_role(message_body, properties, mock_client, bot_context)

        # Assert
        # Verify the correct role ID from bot_context was used
        expected_role_id = bot_context.verified_email_role_id
        mock_guild.get_role.assert_called_once_with(expected_role_id)

    @pytest.mark.asyncio
    async def test_add_verified_role_uses_correct_guild(self, bot_context):
        """Test that consumer uses correct guild from context."""
        # Arrange
        discord_id = 555666777
        message_body = str(discord_id).encode("utf-8")
        properties = MagicMock(spec=BasicProperties)

        mock_client = MagicMock()
        mock_guild = MagicMock()
        mock_member = MagicMock()
        mock_role = MagicMock()

        mock_client.get_guild.return_value = mock_guild
        mock_guild.get_member.return_value = mock_member
        mock_guild.get_role.return_value = mock_role
        mock_member.add_roles = AsyncMock()

        # Act
        await add_verified_role(message_body, properties, mock_client, bot_context)

        # Assert
        # Verify the correct guild ID from bot_context was used
        expected_guild_id = bot_context.swecc_server
        mock_client.get_guild.assert_called_once_with(expected_guild_id)
