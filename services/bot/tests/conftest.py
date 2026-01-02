"""Pytest fixtures for bot service tests."""

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import discord
import pytest
from discord.ext import commands


@pytest.fixture
def mock_env_vars(monkeypatch):
    """Mock environment variables for testing."""
    env_vars = {
        "DISCORD_TOKEN": "test_token_123",
        "SWECC_SERVER": "123456789",
        "ADMIN_CHANNEL": "111111111",
        "TRANSCRIPTS_CHANNEL": "222222222",
        "SWECC_RESUME_CHANNEL": "333333333",
        "READING_GROUP_CHANNEL": "444444444",
        "COHORT_CATEGORY_ID": "555555555",
        "VERIFIED_ROLE_ID": "666666666",
        "OFFICER_ROLE_ID": "777777777",
        "VERIFIED_EMAIL_ROLE_ID": "888888888",
        "PREFIX_COMMAND": "!",
        "SWECC_URL": "https://test.swecc.org",
        "SWECC_API_KEY": "test_api_key",
        "NEW_GRAD_CHANNEL_ID": "999999999",
        "INTERNSHIP_CHANNEL_ID": "101010101",
        "OFF_TOPIC_CHANNEL_ID": "121212121",
        "AI_API_URL": "http://test-ai:8008",
    }
    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)
    return env_vars


@pytest.fixture
def bot_context(mock_env_vars):
    """Create a BotContext instance for testing."""
    from settings.context import BotContext

    return BotContext()


@pytest.fixture
def mock_discord_client():
    """Create a mock Discord bot client."""
    client = MagicMock(spec=commands.Bot)
    client.user = MagicMock(spec=discord.User)
    client.user.name = "TestBot"
    client.user.id = 123456
    client.tree = MagicMock()
    client.tree.sync = AsyncMock(return_value=[])
    client.session = MagicMock()
    return client


@pytest.fixture
def mock_guild():
    """Create a mock Discord guild."""
    guild = MagicMock(spec=discord.Guild)
    guild.id = 123456789
    guild.name = "Test Guild"
    guild.get_channel = MagicMock()
    return guild


@pytest.fixture
def mock_member(mock_guild):
    """Create a mock Discord member."""
    member = MagicMock(spec=discord.Member)
    member.id = 987654321
    member.display_name = "TestUser"
    member.mention = "<@987654321>"
    member.guild = mock_guild
    member.joined_at = datetime.now(timezone.utc) - timedelta(days=1)
    member.send = AsyncMock()
    member.edit = AsyncMock()
    member.ban = AsyncMock()
    member.roles = []
    return member


@pytest.fixture
def mock_message(mock_member, mock_guild):
    """Create a mock Discord message."""
    message = MagicMock(spec=discord.Message)
    message.author = mock_member
    message.guild = mock_guild
    message.content = "Test message"
    message.channel = MagicMock(spec=discord.TextChannel)
    message.channel.id = 111111111
    message.channel.send = AsyncMock()
    message.delete = AsyncMock()
    message.attachments = []
    return message


@pytest.fixture
def mock_channel():
    """Create a mock Discord channel."""
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 222222222
    channel.send = AsyncMock()
    channel.mention = "<#222222222>"
    channel.name = "test-channel"
    return channel


@pytest.fixture
def mock_reaction_payload():
    """Create a mock reaction payload."""
    payload = MagicMock(spec=discord.RawReactionActionEvent)
    payload.user_id = 987654321
    payload.channel_id = 999999999
    payload.message_id = 111222333
    payload.emoji = MagicMock()
    payload.emoji.name = "✅"
    return payload


@pytest.fixture
def mock_swecc_api():
    """Create a mock SweccAPI instance."""
    with patch("APIs.SweccAPI.SweccAPI") as mock:
        api = mock.return_value
        api.process_message_event = AsyncMock()
        api.process_reaction_event = AsyncMock()
        api.set_session = MagicMock()
        yield api


@pytest.fixture
def mock_gemini_api():
    """Create a mock GeminiAPI instance."""
    with patch("APIs.GeminiAPI.GeminiAPI") as mock:
        api = mock.return_value
        api.process_message_event = AsyncMock()
        yield api


@pytest.fixture
def mock_mq_producers():
    """Mock RabbitMQ producers."""
    with patch("mq.producers.publish_message_event", new_callable=AsyncMock) as mock_msg, patch(
        "mq.producers.publish_reaction_add_event", new_callable=AsyncMock
    ) as mock_add, patch(
        "mq.producers.publish_reaction_remove_event", new_callable=AsyncMock
    ) as mock_remove:
        yield {
            "publish_message_event": mock_msg,
            "publish_reaction_add_event": mock_add,
            "publish_reaction_remove_event": mock_remove,
        }


@pytest.fixture
def mock_thread():
    """Create a mock Discord thread."""
    thread = MagicMock(spec=discord.Thread)
    thread.id = 555555555
    thread.guild = MagicMock()
    thread.guild.id = 123456789
    thread.parent_id = 333333333
    thread.parent = MagicMock()
    thread.parent.mention = "<#333333333>"
    thread.parent.name = "resume-channel"
    thread.fetch_message = AsyncMock()
    thread.delete = AsyncMock()
    return thread


@pytest.fixture
def mock_interaction(mock_guild, mock_member):
    """Create a mock Discord interaction."""
    interaction = MagicMock(spec=discord.Interaction)
    interaction.user = mock_member
    interaction.guild = mock_guild
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.response.send_modal = AsyncMock()
    interaction.response.is_done = MagicMock(return_value=False)
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    interaction.client = MagicMock()
    interaction.created_at = datetime.now(timezone.utc)
    return interaction


@pytest.fixture
def mock_role():
    """Create a mock Discord role."""
    role = MagicMock(spec=discord.Role)
    role.id = 666666666
    role.name = "Test Role"
    role.mention = "<@&666666666>"
    return role
