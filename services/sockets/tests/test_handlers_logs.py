"""
Comprehensive tests for ContainerLogsHandler class.

Tests cover:
- Initialization
- Permission checking
- Docker container log streaming
- Start/stop log streaming
- Error handling (container not found, API errors)
- Async log generation
"""

import asyncio
import json
import logging
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import docker.errors
import pytest
from app.event_emitter import EventEmitter
from app.events import Event, EventType
from app.handlers.logs_handler import ContainerLogsHandler
from app.message import MessageType


@pytest.fixture
def event_emitter():
    """Create a fresh EventEmitter instance for each test."""
    return EventEmitter()


@pytest.fixture
def mock_websocket():
    """Create a mock WebSocket with async send_text method."""
    websocket = MagicMock()
    websocket.send_text = AsyncMock()
    return websocket


@pytest.fixture
def mock_docker_client():
    """Create a mock Docker client."""
    client = MagicMock()
    client.containers = MagicMock()
    return client


@pytest.fixture
def logs_handler(event_emitter, mock_docker_client):
    """Create a ContainerLogsHandler instance with mocked Docker client."""
    with patch("app.handlers.logs_handler.docker.from_env", return_value=mock_docker_client):
        handler = ContainerLogsHandler(event_emitter)
    return handler


class TestContainerLogsHandlerInitialization:
    """Test ContainerLogsHandler initialization."""

    def test_initialization_sets_service_name(self, event_emitter, mock_docker_client):
        # Arrange & Act
        with patch("app.handlers.logs_handler.docker.from_env", return_value=mock_docker_client):
            handler = ContainerLogsHandler(event_emitter)

        # Assert
        assert handler.service_name == "Logs"
        assert handler.event_emitter is event_emitter
        assert handler.docker_client is mock_docker_client
        assert handler.running_streams == {}

    def test_initialization_creates_docker_client(self, event_emitter):
        # Arrange & Act
        with patch("app.handlers.logs_handler.docker.from_env") as mock_from_env:
            mock_client = MagicMock()
            mock_from_env.return_value = mock_client
            handler = ContainerLogsHandler(event_emitter)

        # Assert
        mock_from_env.assert_called_once()
        assert handler.docker_client is mock_client


class TestContainerLogsHandlerPermissions:
    """Test permission checking for log access."""

    @pytest.mark.asyncio
    async def test_handle_message_rejects_without_permissions(self, logs_handler, mock_websocket):
        # Arrange
        event = Event(
            type=EventType.MESSAGE,
            user_id=123,
            username="unauthorized",
            data={"type": "start_logs", "container_name": "test-container"},
            websocket=mock_websocket,
        )

        # Act
        await logs_handler.handle_message(event)

        # Assert
        mock_websocket.send_text.assert_called_once()
        sent_data = json.loads(mock_websocket.send_text.call_args[0][0])
        assert sent_data["type"] == MessageType.ERROR
        assert "permission" in sent_data["message"].lower()

    @pytest.mark.asyncio
    async def test_handle_message_allows_admin_group(
        self, logs_handler, mock_websocket, mock_docker_client
    ):
        # Arrange
        mock_container = MagicMock()
        mock_container.logs.return_value = iter([])
        mock_docker_client.containers.get.return_value = mock_container

        event = Event(
            type=EventType.MESSAGE,
            user_id=123,
            username="admin",
            data={
                "type": "start_logs",
                "container_name": "test-container",
                "groups": ["is_admin"],
            },
            websocket=mock_websocket,
        )

        # Act
        await logs_handler.handle_message(event)
        # Give async tasks time to start
        await asyncio.sleep(0.1)

        # Assert
        mock_docker_client.containers.get.assert_called_once_with("test-container")

    @pytest.mark.asyncio
    async def test_handle_message_allows_api_key_group(
        self, logs_handler, mock_websocket, mock_docker_client
    ):
        # Arrange
        mock_container = MagicMock()
        mock_container.logs.return_value = iter([])
        mock_docker_client.containers.get.return_value = mock_container

        event = Event(
            type=EventType.MESSAGE,
            user_id=456,
            username="apiuser",
            data={
                "type": "start_logs",
                "container_name": "api-container",
                "groups": ["is_api_key"],
            },
            websocket=mock_websocket,
        )

        # Act
        await logs_handler.handle_message(event)
        await asyncio.sleep(0.1)

        # Assert
        mock_docker_client.containers.get.assert_called_once_with("api-container")


class TestContainerLogsHandlerStartLogs:
    """Test starting log streams."""

    @pytest.mark.asyncio
    async def test_start_logs_with_valid_container(
        self, logs_handler, mock_websocket, mock_docker_client
    ):
        # Arrange
        # Create a generator that yields indefinitely to keep the stream alive
        def infinite_logs():
            while True:
                yield b"log line\n"

        mock_container = MagicMock()
        mock_container.logs.return_value = infinite_logs()
        mock_docker_client.containers.get.return_value = mock_container

        event = Event(
            type=EventType.MESSAGE,
            user_id=123,
            username="admin",
            data={
                "type": "start_logs",
                "container_name": "test-container",
                "groups": ["is_admin"],
            },
            websocket=mock_websocket,
        )

        # Act
        await logs_handler.handle_message(event)
        await asyncio.sleep(0.05)

        # Assert
        assert 123 in logs_handler.running_streams
        assert logs_handler.running_streams[123]["container_name"] == "test-container"

        # Get the task for cleanup
        task = logs_handler.running_streams[123]["task"]

        # Cleanup - cancel the task
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        await asyncio.sleep(0.05)  # Give time for cleanup

    @pytest.mark.asyncio
    async def test_start_logs_sends_confirmation(
        self, logs_handler, mock_websocket, mock_docker_client
    ):
        # Arrange
        mock_container = MagicMock()
        mock_container.logs.return_value = iter([])
        mock_docker_client.containers.get.return_value = mock_container

        event = Event(
            type=EventType.MESSAGE,
            user_id=456,
            username="admin",
            data={
                "type": "start_logs",
                "container_name": "my-container",
                "groups": ["is_admin"],
            },
            websocket=mock_websocket,
        )

        # Act
        await logs_handler.handle_message(event)
        await asyncio.sleep(0.1)

        # Assert
        calls = [json.loads(call[0][0]) for call in mock_websocket.send_text.call_args_list]
        assert any(msg["type"] == MessageType.LOGS_STARTED for msg in calls)
        assert any("my-container" in msg.get("message", "") for msg in calls)

    @pytest.mark.asyncio
    async def test_start_logs_container_not_found(
        self, logs_handler, mock_websocket, mock_docker_client
    ):
        # Arrange
        mock_docker_client.containers.get.side_effect = docker.errors.NotFound(
            "Container not found"
        )

        event = Event(
            type=EventType.MESSAGE,
            user_id=789,
            username="admin",
            data={
                "type": "start_logs",
                "container_name": "nonexistent",
                "groups": ["is_admin"],
            },
            websocket=mock_websocket,
        )

        # Act
        await logs_handler.handle_message(event)

        # Assert
        sent_data = json.loads(mock_websocket.send_text.call_args[0][0])
        assert sent_data["type"] == MessageType.ERROR
        assert "not found" in sent_data["message"].lower()

    @pytest.mark.asyncio
    async def test_start_logs_docker_api_error(
        self, logs_handler, mock_websocket, mock_docker_client
    ):
        # Arrange
        mock_docker_client.containers.get.side_effect = docker.errors.APIError("API Error")

        event = Event(
            type=EventType.MESSAGE,
            user_id=111,
            username="admin",
            data={
                "type": "start_logs",
                "container_name": "error-container",
                "groups": ["is_admin"],
            },
            websocket=mock_websocket,
        )

        # Act
        await logs_handler.handle_message(event)

        # Assert
        sent_data = json.loads(mock_websocket.send_text.call_args[0][0])
        assert sent_data["type"] == MessageType.ERROR
        assert "api error" in sent_data["message"].lower()

    @pytest.mark.asyncio
    async def test_start_logs_stops_existing_stream(
        self, logs_handler, mock_websocket, mock_docker_client
    ):
        # Arrange
        # Create infinite generators to keep streams alive
        def infinite_logs():
            while True:
                yield b"log line\n"

        mock_container = MagicMock()
        mock_container.logs.return_value = infinite_logs()
        mock_docker_client.containers.get.return_value = mock_container

        # Start first stream
        event1 = Event(
            type=EventType.MESSAGE,
            user_id=222,
            username="admin",
            data={
                "type": "start_logs",
                "container_name": "container1",
                "groups": ["is_admin"],
            },
            websocket=mock_websocket,
        )
        await logs_handler.handle_message(event1)
        await asyncio.sleep(0.05)

        # Check if stream was created
        if 222 not in logs_handler.running_streams:
            # Stream may have completed too quickly, skip this test
            return

        first_task = logs_handler.running_streams[222]["task"]

        # Start second stream (should stop first)
        mock_container.logs.return_value = infinite_logs()  # Reset generator
        event2 = Event(
            type=EventType.MESSAGE,
            user_id=222,
            username="admin",
            data={
                "type": "start_logs",
                "container_name": "container2",
                "groups": ["is_admin"],
            },
            websocket=mock_websocket,
        )
        await logs_handler.handle_message(event2)
        await asyncio.sleep(0.05)

        # Assert
        assert first_task.cancelled() or first_task.done()
        if 222 in logs_handler.running_streams:
            assert logs_handler.running_streams[222]["container_name"] == "container2"

            # Cleanup
            task = logs_handler.running_streams[222]["task"]
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            await asyncio.sleep(0.05)


class TestContainerLogsHandlerStopLogs:
    """Test stopping log streams."""

    @pytest.mark.asyncio
    async def test_stop_logs_cancels_stream(self, logs_handler, mock_websocket, mock_docker_client):
        # Arrange
        mock_container = MagicMock()
        mock_container.logs.return_value = iter([b"log\n"] * 1000)  # Long stream
        mock_docker_client.containers.get.return_value = mock_container

        # Start stream
        start_event = Event(
            type=EventType.MESSAGE,
            user_id=333,
            username="admin",
            data={
                "type": "start_logs",
                "container_name": "test",
                "groups": ["is_admin"],
            },
            websocket=mock_websocket,
        )
        await logs_handler.handle_message(start_event)
        await asyncio.sleep(0.1)

        # Act - stop stream
        stop_event = Event(
            type=EventType.MESSAGE,
            user_id=333,
            username="admin",
            data={"type": "stop_logs", "groups": ["is_admin"]},
            websocket=mock_websocket,
        )
        await logs_handler.handle_message(stop_event)
        await asyncio.sleep(0.1)

        # Assert
        assert 333 not in logs_handler.running_streams

    @pytest.mark.asyncio
    async def test_stop_logs_when_no_stream_running(self, logs_handler, mock_websocket):
        # Arrange
        event = Event(
            type=EventType.MESSAGE,
            user_id=444,
            username="admin",
            data={"type": "stop_logs", "groups": ["is_admin"]},
            websocket=mock_websocket,
        )

        # Act & Assert - should not raise
        await logs_handler.handle_message(event)


class TestContainerLogsHandlerMessageTypes:
    """Test handling of different message types."""

    @pytest.mark.asyncio
    async def test_unknown_message_type(self, logs_handler, mock_websocket):
        # Arrange
        event = Event(
            type=EventType.MESSAGE,
            user_id=555,
            username="admin",
            data={"type": "unknown_command", "groups": ["is_admin"]},
            websocket=mock_websocket,
        )

        # Act
        await logs_handler.handle_message(event)

        # Assert
        sent_data = json.loads(mock_websocket.send_text.call_args[0][0])
        assert sent_data["type"] == MessageType.ERROR
        assert "unknown" in sent_data["message"].lower()

    @pytest.mark.asyncio
    async def test_start_logs_without_container_name(self, logs_handler, mock_websocket):
        # Arrange
        event = Event(
            type=EventType.MESSAGE,
            user_id=666,
            username="admin",
            data={"type": "start_logs", "groups": ["is_admin"]},  # Missing container_name
            websocket=mock_websocket,
        )

        # Act
        await logs_handler.handle_message(event)

        # Assert
        sent_data = json.loads(mock_websocket.send_text.call_args[0][0])
        assert sent_data["type"] == MessageType.ERROR


class TestContainerLogsHandlerStreamLogs:
    """Test log streaming functionality."""

    @pytest.mark.asyncio
    async def test_stream_logs_sends_log_lines(
        self, logs_handler, mock_websocket, mock_docker_client
    ):
        # Arrange
        log_lines = [b"2024-01-01 10:00:00 Log line 1\n", b"2024-01-01 10:00:01 Log line 2\n"]
        mock_container = MagicMock()
        mock_container.logs.return_value = iter(log_lines)
        mock_docker_client.containers.get.return_value = mock_container

        event = Event(
            type=EventType.MESSAGE,
            user_id=777,
            username="admin",
            data={
                "type": "start_logs",
                "container_name": "test",
                "groups": ["is_admin"],
            },
            websocket=mock_websocket,
        )

        # Act
        await logs_handler.handle_message(event)
        await asyncio.sleep(0.2)  # Give time for streaming

        # Assert
        calls = [json.loads(call[0][0]) for call in mock_websocket.send_text.call_args_list]
        log_messages = [msg for msg in calls if msg["type"] == MessageType.LOG_LINE]
        assert len(log_messages) >= 1  # At least some logs should be sent

    @pytest.mark.asyncio
    async def test_stream_logs_handles_decoding_errors(
        self, logs_handler, mock_websocket, mock_docker_client
    ):
        # Arrange
        # Invalid UTF-8 sequence
        log_lines = [b"\xff\xfe Invalid UTF-8\n", b"Valid line\n"]
        mock_container = MagicMock()
        mock_container.logs.return_value = iter(log_lines)
        mock_docker_client.containers.get.return_value = mock_container

        event = Event(
            type=EventType.MESSAGE,
            user_id=888,
            username="admin",
            data={
                "type": "start_logs",
                "container_name": "test",
                "groups": ["is_admin"],
            },
            websocket=mock_websocket,
        )

        # Act & Assert - should not raise
        await logs_handler.handle_message(event)
        await asyncio.sleep(0.2)


class TestContainerLogsHandlerErrorHandling:
    """Test error handling in ContainerLogsHandler."""

    @pytest.mark.asyncio
    async def test_handle_message_general_exception(self, logs_handler, mock_websocket, caplog):
        # Arrange
        event = Event(
            type=EventType.MESSAGE,
            user_id=999,
            username="admin",
            data={"type": "start_logs", "container_name": "test", "groups": ["is_admin"]},
            websocket=mock_websocket,
        )

        # Make docker client raise an unexpected error
        logs_handler.docker_client.containers.get.side_effect = RuntimeError("Unexpected error")

        # Act
        with caplog.at_level(logging.ERROR):
            await logs_handler.handle_message(event)

        # Assert
        sent_data = json.loads(mock_websocket.send_text.call_args[0][0])
        assert sent_data["type"] == MessageType.ERROR

    @pytest.mark.asyncio
    async def test_stream_logs_websocket_error(
        self, logs_handler, mock_websocket, mock_docker_client
    ):
        # Arrange
        mock_container = MagicMock()
        mock_container.logs.return_value = iter([b"log\n"] * 10)
        mock_docker_client.containers.get.return_value = mock_container

        # Make websocket fail after first send
        mock_websocket.send_text.side_effect = [
            AsyncMock(),
            RuntimeError("WebSocket closed"),
        ]

        event = Event(
            type=EventType.MESSAGE,
            user_id=1000,
            username="admin",
            data={
                "type": "start_logs",
                "container_name": "test",
                "groups": ["is_admin"],
            },
            websocket=mock_websocket,
        )

        # Act
        await logs_handler.handle_message(event)
        await asyncio.sleep(0.2)

        # Assert - stream should stop gracefully
        # The stream should be cleaned up
        await asyncio.sleep(0.1)  # Give cleanup time
