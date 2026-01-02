"""Tests for slash_commands/utils.py"""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from slash_commands.utils import handle_cohort_stat_update, is_valid_school_email, slugify


class TestHandleCohortStatUpdate:
    """Test suite for handle_cohort_stat_update function."""

    @pytest.mark.asyncio
    async def test_handle_cohort_stat_update_success(self, bot_context):
        """Test successful cohort stat update."""
        # Arrange
        ctx = MagicMock(spec=discord.Interaction)
        ctx.response = MagicMock()
        ctx.response.send_message = AsyncMock()

        data = ["cohort1", "cohort2"]
        error = None
        title = "Test Update"
        description = "Update successful"

        # Act
        await handle_cohort_stat_update(ctx, data, error, bot_context, title, description)

        # Assert
        ctx.response.send_message.assert_called_once()
        call_args = ctx.response.send_message.call_args
        embed = call_args.kwargs["embed"]
        assert embed.title == title
        assert embed.description == description
        assert embed.color == discord.Color.green()
        assert call_args.kwargs["ephemeral"] == bot_context.ephemeral

    @pytest.mark.asyncio
    async def test_handle_cohort_stat_update_with_error(self, bot_context):
        """Test cohort stat update with error."""
        # Arrange
        ctx = MagicMock(spec=discord.Interaction)
        ctx.response = MagicMock()
        ctx.response.send_message = AsyncMock()

        data = None
        error = {"message": "Something went wrong"}
        title = "Test Update"
        description = "Update successful"

        # Act
        await handle_cohort_stat_update(ctx, data, error, bot_context, title, description)

        # Assert
        ctx.response.send_message.assert_called_once()
        call_args = ctx.response.send_message.call_args
        embed = call_args.kwargs["embed"]
        assert embed.title == "Error"
        assert embed.description == "Something went wrong"
        assert embed.color == discord.Color.red()


class TestIsValidSchoolEmail:
    """Test suite for is_valid_school_email function."""

    def test_valid_uw_email(self):
        """Test valid UW email."""
        # Arrange & Act & Assert
        assert is_valid_school_email("student@uw.edu") is True

    def test_valid_uw_email_with_subdomain(self):
        """Test valid UW email with subdomain."""
        # Arrange & Act & Assert
        assert is_valid_school_email("student@cs.uw.edu") is False

    def test_invalid_email_different_domain(self):
        """Test invalid email with different domain."""
        # Arrange & Act & Assert
        assert is_valid_school_email("student@gmail.com") is False

    def test_invalid_email_no_domain(self):
        """Test invalid email without domain."""
        # Arrange & Act & Assert
        assert is_valid_school_email("student") is False

    def test_empty_email(self):
        """Test empty email."""
        # Arrange & Act & Assert
        assert is_valid_school_email("") is False


class TestSlugify:
    """Test suite for slugify function."""

    def test_slugify_simple_string(self):
        """Test slugifying a simple string."""
        # Arrange & Act
        result = slugify("Hello World")

        # Assert
        assert result == "hello-world"

    def test_slugify_with_special_characters(self):
        """Test slugifying string with special characters."""
        # Arrange & Act
        result = slugify("Hello, World!")

        # Assert
        assert result == "hello-world"

    def test_slugify_with_multiple_spaces(self):
        """Test slugifying string with multiple spaces."""
        # Arrange & Act
        result = slugify("Hello    World")

        # Assert
        assert result == "hello-world"

    def test_slugify_with_hyphens(self):
        """Test slugifying string with existing hyphens."""
        # Arrange & Act
        result = slugify("Hello--World")

        # Assert
        assert result == "hello-world"

    def test_slugify_with_leading_trailing_spaces(self):
        """Test slugifying string with leading/trailing spaces."""
        # Arrange & Act
        result = slugify("  Hello World  ")

        # Assert
        assert result == "hello-world"

    def test_slugify_with_numbers(self):
        """Test slugifying string with numbers."""
        # Arrange & Act
        result = slugify("Cohort 2024")

        # Assert
        assert result == "cohort-2024"

    def test_slugify_with_underscores(self):
        """Test slugifying string with underscores."""
        # Arrange & Act
        result = slugify("Hello_World")

        # Assert
        assert result == "hello_world"

    def test_slugify_empty_string(self):
        """Test slugifying empty string."""
        # Arrange & Act
        result = slugify("")

        # Assert
        assert result == ""
