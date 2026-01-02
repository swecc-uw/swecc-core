"""Tests for task index and orchestration."""

from unittest.mock import MagicMock, patch

import pytest
from tasks.index import start_daily_tasks


class TestStartDailyTasks:
    """Test suite for start_daily_tasks class."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock Discord client."""
        client = MagicMock()
        return client

    @pytest.fixture
    def mock_bot_context(self):
        """Create a mock BotContext."""
        context = MagicMock()
        context.admin_channel = 111111111
        return context

    def test_init(self, mock_client, mock_bot_context):
        """Test initialization of start_daily_tasks."""
        # Arrange & Act
        task_manager = start_daily_tasks(mock_client, mock_bot_context)

        # Assert
        assert task_manager.client == mock_client
        assert task_manager.bot_context == mock_bot_context

    def test_start_tasks_calls_all_task_starters(self, mock_client, mock_bot_context):
        """Test that start_tasks calls all scheduled task starters."""
        # Arrange
        task_manager = start_daily_tasks(mock_client, mock_bot_context)

        with patch("tasks.index.lc_start_scheduled_task") as mock_lc_start, patch(
            "tasks.index.sync_channels_start_scheduled_task"
        ) as mock_sync_start, patch("tasks.index.aoc_start_scheduled_task") as mock_aoc_start:

            # Act
            task_manager.start_tasks()

            # Assert
            mock_lc_start.assert_called_once_with(mock_client, mock_bot_context.admin_channel)
            mock_sync_start.assert_called_once_with(mock_client)
            mock_aoc_start.assert_called_once_with(mock_client)

    def test_start_tasks_order(self, mock_client, mock_bot_context):
        """Test that tasks are started in the correct order."""
        # Arrange
        task_manager = start_daily_tasks(mock_client, mock_bot_context)
        call_order = []

        def track_lc(*args, **kwargs):
            call_order.append("lc")

        def track_sync(*args, **kwargs):
            call_order.append("sync")

        def track_aoc(*args, **kwargs):
            call_order.append("aoc")

        with patch("tasks.index.lc_start_scheduled_task", side_effect=track_lc), patch(
            "tasks.index.sync_channels_start_scheduled_task", side_effect=track_sync
        ), patch("tasks.index.aoc_start_scheduled_task", side_effect=track_aoc):

            # Act
            task_manager.start_tasks()

            # Assert
            assert call_order == ["lc", "sync", "aoc"]

    def test_start_tasks_with_different_admin_channel(self, mock_client):
        """Test start_tasks with different admin channel ID."""
        # Arrange
        context = MagicMock()
        context.admin_channel = 999999999
        task_manager = start_daily_tasks(mock_client, context)

        with patch("tasks.index.lc_start_scheduled_task") as mock_lc_start, patch(
            "tasks.index.sync_channels_start_scheduled_task"
        ), patch("tasks.index.aoc_start_scheduled_task"):

            # Act
            task_manager.start_tasks()

            # Assert
            mock_lc_start.assert_called_once_with(mock_client, 999999999)

    def test_start_tasks_multiple_calls(self, mock_client, mock_bot_context):
        """Test that start_tasks can be called multiple times."""
        # Arrange
        task_manager = start_daily_tasks(mock_client, mock_bot_context)

        with patch("tasks.index.lc_start_scheduled_task") as mock_lc_start, patch(
            "tasks.index.sync_channels_start_scheduled_task"
        ) as mock_sync_start, patch("tasks.index.aoc_start_scheduled_task") as mock_aoc_start:

            # Act
            task_manager.start_tasks()
            task_manager.start_tasks()

            # Assert - each should be called twice
            assert mock_lc_start.call_count == 2
            assert mock_sync_start.call_count == 2
            assert mock_aoc_start.call_count == 2

    def test_start_tasks_handles_lc_task_exception(self, mock_client, mock_bot_context):
        """Test that exception in LC task doesn't prevent other tasks from starting."""
        # Arrange
        task_manager = start_daily_tasks(mock_client, mock_bot_context)

        with patch(
            "tasks.index.lc_start_scheduled_task", side_effect=Exception("LC task error")
        ), patch("tasks.index.sync_channels_start_scheduled_task") as mock_sync_start, patch(
            "tasks.index.aoc_start_scheduled_task"
        ) as mock_aoc_start:

            # Act & Assert
            with pytest.raises(Exception, match="LC task error"):
                task_manager.start_tasks()

            # Other tasks should not be called if LC task fails
            mock_sync_start.assert_not_called()
            mock_aoc_start.assert_not_called()

    def test_start_tasks_handles_sync_task_exception(self, mock_client, mock_bot_context):
        """Test that exception in sync task doesn't prevent AOC task from starting."""
        # Arrange
        task_manager = start_daily_tasks(mock_client, mock_bot_context)

        with patch("tasks.index.lc_start_scheduled_task"), patch(
            "tasks.index.sync_channels_start_scheduled_task",
            side_effect=Exception("Sync task error"),
        ), patch("tasks.index.aoc_start_scheduled_task") as mock_aoc_start:

            # Act & Assert
            with pytest.raises(Exception, match="Sync task error"):
                task_manager.start_tasks()

            # AOC task should not be called if sync task fails
            mock_aoc_start.assert_not_called()

    def test_class_name_convention(self):
        """Test that class follows naming convention (lowercase with underscores)."""
        # Assert
        assert start_daily_tasks.__name__ == "start_daily_tasks"

    def test_start_tasks_method_exists(self, mock_client, mock_bot_context):
        """Test that start_tasks method exists and is callable."""
        # Arrange
        task_manager = start_daily_tasks(mock_client, mock_bot_context)

        # Assert
        assert hasattr(task_manager, "start_tasks")
        assert callable(task_manager.start_tasks)

    def test_instance_attributes(self, mock_client, mock_bot_context):
        """Test that instance has correct attributes."""
        # Arrange & Act
        task_manager = start_daily_tasks(mock_client, mock_bot_context)

        # Assert
        assert hasattr(task_manager, "client")
        assert hasattr(task_manager, "bot_context")
        assert task_manager.client is mock_client
        assert task_manager.bot_context is mock_bot_context

    def test_start_tasks_with_none_admin_channel(self, mock_client):
        """Test start_tasks when admin_channel is None."""
        # Arrange
        context = MagicMock()
        context.admin_channel = None
        task_manager = start_daily_tasks(mock_client, context)

        with patch("tasks.index.lc_start_scheduled_task") as mock_lc_start, patch(
            "tasks.index.sync_channels_start_scheduled_task"
        ), patch("tasks.index.aoc_start_scheduled_task"):

            # Act
            task_manager.start_tasks()

            # Assert
            mock_lc_start.assert_called_once_with(mock_client, None)
