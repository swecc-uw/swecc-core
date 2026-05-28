"""Tests for slash_commands/auth.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from slash_commands import auth as auth_module


@pytest.mark.asyncio
async def test_verify_command_sends_modal_without_adding_role(bot_context, mock_interaction, mock_role):
    """Verify command should open modal before any role mutation."""
    bot_context.verified_role_id = mock_role.id
    bot_context.log = AsyncMock()
    mock_interaction.guild.get_role.return_value = mock_role
    mock_interaction.user.roles = []
    mock_interaction.user.add_roles = AsyncMock()

    auth_module.bot_context = bot_context

    await auth_module.auth(mock_interaction)

    mock_interaction.response.send_modal.assert_called_once()
    mock_interaction.user.add_roles.assert_not_called()


@pytest.mark.asyncio
async def test_verify_modal_defers_then_follows_up_success(bot_context, mock_interaction, mock_role):
    """Verify modal should defer quickly and reply via followup on success."""
    bot_context.verified_role_id = mock_role.id
    bot_context.log = AsyncMock()
    mock_interaction.guild.get_role.return_value = mock_role
    mock_interaction.user.add_roles = AsyncMock()

    modal = auth_module.VerifyModal(bot_context)
    modal.code._value = "website-user"

    with patch.object(auth_module.swecc, "auth", return_value=200):
        await modal.on_submit(mock_interaction)

    mock_interaction.response.defer.assert_called_once_with(ephemeral=True)
    mock_interaction.followup.send.assert_called_once_with(
        "Authentication successful!", ephemeral=True
    )
    mock_interaction.user.add_roles.assert_called_once_with(mock_role)


@pytest.mark.asyncio
async def test_reset_password_logs_actionable_failure(bot_context, mock_interaction):
    """Reset password should surface user-safe error and actionable log details."""
    bot_context.log = AsyncMock()
    auth_module.bot_context = bot_context

    with patch.object(
        auth_module.swecc,
        "reset_password",
        new=AsyncMock(side_effect=RuntimeError("status 404: Not found.")),
    ):
        await auth_module.reset_password(mock_interaction)

    mock_interaction.response.send_message.assert_called_once_with(
        "Unable to create a password reset link right now. Please try again in a minute.",
        ephemeral=True,
    )
    logged_message = bot_context.log.await_args.args[1]
    assert "Password reset failed" in logged_message
    assert "discord_id=" in logged_message

