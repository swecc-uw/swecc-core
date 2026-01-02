"""
Tests for main.py module.

Tests cover:
- FastAPI app initialization
- Lifespan context manager
- All endpoints: /test, /inference/{key}/config, /inference/{key}/complete, /inference/status/{request_id}
- Request/response models
- Error handling
- Async task execution
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from app.config import Settings
from app.llm.context import ContextConfig, ContextManager
from app.llm.message import Message
from app.main import (
    CompleteRequest,
    ConfigRequest,
    app,
    complete_task,
    format_message,
    waiting_requests,
)
from app.polling import PollingRequest, Status
from fastapi import status as APIStatus
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    with patch("app.main.initialize_rabbitmq", new_callable=AsyncMock):
        with patch("app.main.shutdown_rabbitmq", new_callable=AsyncMock):
            with TestClient(app) as test_client:
                yield test_client


@pytest.fixture
def mock_context_manager():
    """Create a mock ContextManager."""
    mock_ctx = MagicMock(spec=ContextManager)
    mock_ctx.context_configs = {}
    mock_ctx.context = {}
    return mock_ctx


@pytest.fixture
def mock_gemini_client():
    """Create a mock Gemini client."""
    mock_client = MagicMock()
    mock_client.prompt_model = AsyncMock(return_value="Test response from Gemini")
    return mock_client


@pytest.fixture(autouse=True)
def clear_waiting_requests():
    """Clear waiting_requests dict before each test."""
    waiting_requests.clear()
    yield
    waiting_requests.clear()


class TestAppInitialization:
    """Test FastAPI app initialization and configuration."""

    def test_app_exists(self):
        """Test that FastAPI app is created."""
        # Arrange & Act & Assert
        assert app is not None

    def test_app_has_cors_middleware(self):
        """Test that CORS middleware is configured."""
        # Arrange & Act
        middleware_types = [type(m) for m in app.user_middleware]

        # Assert
        # CORS middleware should be present
        assert len(app.user_middleware) > 0

    def test_app_title_or_routes_exist(self):
        """Test that app has routes configured."""
        # Arrange & Act
        routes = [route.path for route in app.routes]

        # Assert
        assert "/test" in routes
        assert "/inference/{key}/config" in routes
        assert "/inference/{key}/complete" in routes
        assert "/inference/status/{request_id}" in routes


class TestConfigRequest:
    """Test ConfigRequest model."""

    def test_config_request_creation(self):
        """Test creating ConfigRequest with valid data."""
        # Arrange & Act
        config = ConfigRequest(
            max_context_length=1000,
            context_invalidation_time_seconds=300,
            system_instruction="Test instruction",
        )

        # Assert
        assert config.max_context_length == 1000
        assert config.context_invalidation_time_seconds == 300
        assert config.system_instruction == "Test instruction"

    def test_config_request_model_dump(self):
        """Test ConfigRequest can be dumped to dict."""
        # Arrange
        config = ConfigRequest(
            max_context_length=2000,
            context_invalidation_time_seconds=600,
            system_instruction="System prompt",
        )

        # Act
        data = config.model_dump()

        # Assert
        assert data["max_context_length"] == 2000
        assert data["context_invalidation_time_seconds"] == 600
        assert data["system_instruction"] == "System prompt"


class TestCompleteRequest:
    """Test CompleteRequest model."""

    def test_complete_request_creation_with_defaults(self):
        """Test creating CompleteRequest with default needs_context."""
        # Arrange & Act
        request = CompleteRequest(
            message="Hello",
            metadata={"user": "test"},
        )

        # Assert
        assert request.message == "Hello"
        assert request.metadata == {"user": "test"}
        assert request.needs_context is True

    def test_complete_request_creation_without_context(self):
        """Test creating CompleteRequest with needs_context=False."""
        # Arrange & Act
        request = CompleteRequest(
            message="Hello",
            metadata={"user": "test"},
            needs_context=False,
        )

        # Assert
        assert request.needs_context is False


class TestFormatMessage:
    """Test format_message function."""

    def test_format_message_with_metadata(self):
        """Test formatting message with metadata."""
        # Arrange
        request = CompleteRequest(
            message="Test message",
            metadata={"author": "John", "role": "admin"},
        )

        # Act
        formatted = format_message(request)

        # Assert
        assert "author: John\n" in formatted
        assert "role: admin\n" in formatted
        assert "Message: Test message\n" in formatted

    def test_format_message_with_empty_metadata(self):
        """Test formatting message with empty metadata."""
        # Arrange
        request = CompleteRequest(
            message="Test message",
            metadata={},
        )

        # Act
        formatted = format_message(request)

        # Assert
        assert formatted == "Message: Test message\n"

    def test_format_message_preserves_order(self):
        """Test that format_message includes all metadata fields."""
        # Arrange
        request = CompleteRequest(
            message="Hello world",
            metadata={"field1": "value1", "field2": "value2", "field3": "value3"},
        )

        # Act
        formatted = format_message(request)

        # Assert
        assert "field1: value1\n" in formatted
        assert "field2: value2\n" in formatted
        assert "field3: value3\n" in formatted
        assert formatted.endswith("Message: Hello world\n")


class TestTestEndpoint:
    """Test /test endpoint."""

    @patch("app.main.producers.finish_review", new_callable=AsyncMock)
    def test_test_endpoint_returns_hello_world(self, mock_finish_review, client):
        """Test that /test endpoint returns hello world message."""
        # Arrange & Act
        response = client.get("/test")

        # Assert
        assert response.status_code == 200
        assert response.json() == {"message": "Hello, World!"}

    @patch("app.main.producers.finish_review", new_callable=AsyncMock)
    def test_test_endpoint_calls_finish_review(self, mock_finish_review, client):
        """Test that /test endpoint calls finish_review producer."""
        # Arrange & Act
        response = client.get("/test")

        # Assert
        mock_finish_review.assert_called_once_with(
            {"feedback": "This is a test feedback", "key": "1-1-test.pdf"}
        )


class TestConfigEndpoint:
    """Test /inference/{key}/config endpoint."""

    @patch("app.main.ctx")
    def test_config_endpoint_creates_new_config(self, mock_ctx, client):
        """Test that config endpoint creates new context config."""
        # Arrange
        mock_ctx.context_configs = {}

        # Make add_context_config actually add to the dict
        def add_config_side_effect(key, **kwargs):
            mock_ctx.context_configs[key] = ContextConfig(**kwargs)

        mock_ctx.add_context_config = MagicMock(side_effect=add_config_side_effect)

        config_data = {
            "max_context_length": 1000,
            "context_invalidation_time_seconds": 300,
            "system_instruction": "Test instruction",
        }

        # Act
        response = client.post("/inference/test-key/config", json=config_data)

        # Assert
        assert response.status_code == 200
        mock_ctx.add_context_config.assert_called_once_with("test-key", **config_data)

    @patch("app.main.ctx")
    def test_config_endpoint_does_not_overwrite_existing(self, mock_ctx, client):
        """Test that config endpoint doesn't overwrite existing config."""
        # Arrange
        existing_config = ContextConfig(
            max_context_length=500,
            context_invalidation_time_seconds=100,
            system_instruction="Existing",
        )
        mock_ctx.context_configs = {"test-key": existing_config}
        mock_ctx.add_context_config = MagicMock()

        config_data = {
            "max_context_length": 1000,
            "context_invalidation_time_seconds": 300,
            "system_instruction": "New instruction",
        }

        # Act
        response = client.post("/inference/test-key/config", json=config_data)

        # Assert
        assert response.status_code == 200
        mock_ctx.add_context_config.assert_not_called()
        # FastAPI serializes dataclass to dict, so compare with dict representation
        expected_config = {
            "max_context_length": 500,
            "context_invalidation_time_seconds": 100,
            "system_instruction": "Existing",
        }
        assert response.json()["config"] == expected_config


class TestCompleteEndpoint:
    """Test /inference/{key}/complete endpoint."""

    @patch("app.main.asyncio.create_task")
    @patch("app.main.generate_request_id")
    def test_complete_endpoint_returns_request_id(self, mock_gen_id, mock_create_task, client):
        """Test that complete endpoint returns request_id."""
        # Arrange
        mock_gen_id.return_value = "test-request-id-123"

        request_data = {
            "message": "Hello",
            "metadata": {"user": "test"},
        }

        # Act
        response = client.post("/inference/test-key/complete", json=request_data)

        # Assert
        assert response.status_code == APIStatus.HTTP_202_ACCEPTED
        assert response.json() == {"request_id": "test-request-id-123"}

    @patch("app.main.asyncio.create_task")
    @patch("app.main.generate_request_id")
    def test_complete_endpoint_creates_polling_request(self, mock_gen_id, mock_create_task, client):
        """Test that complete endpoint creates polling request."""
        # Arrange
        mock_gen_id.return_value = "test-request-id-456"

        request_data = {
            "message": "Test",
            "metadata": {},
        }

        # Act
        response = client.post("/inference/test-key/complete", json=request_data)

        # Assert
        assert "test-request-id-456" in waiting_requests
        assert waiting_requests["test-request-id-456"].status == Status.PENDING
        assert waiting_requests["test-request-id-456"].result is None
        assert waiting_requests["test-request-id-456"].error is None

    @patch("app.main.asyncio.create_task")
    @patch("app.main.generate_request_id")
    def test_complete_endpoint_creates_async_task(self, mock_gen_id, mock_create_task, client):
        """Test that complete endpoint creates async task."""
        # Arrange
        mock_gen_id.return_value = "test-request-id-789"

        request_data = {
            "message": "Test message",
            "metadata": {"key": "value"},
            "needs_context": False,
        }

        # Act
        response = client.post("/inference/user-key/complete", json=request_data)

        # Assert
        mock_create_task.assert_called_once()


class TestStatusEndpoint:
    """Test /inference/status/{request_id} endpoint."""

    def test_status_endpoint_request_not_found(self, client):
        """Test status endpoint returns 404 for unknown request_id."""
        # Arrange & Act
        response = client.get("/inference/status/unknown-request-id")

        # Assert
        assert response.status_code == APIStatus.HTTP_404_NOT_FOUND
        assert response.json() == {"error": "Request ID not found."}

    def test_status_endpoint_pending_status(self, client):
        """Test status endpoint returns pending status."""
        # Arrange
        request_id = "pending-request"
        waiting_requests[request_id] = PollingRequest(
            request_id=request_id,
            status=Status.PENDING,
            result=None,
            error=None,
        )

        # Act
        response = client.get(f"/inference/status/{request_id}")

        # Assert
        assert response.status_code == 200
        assert response.json() == {"status": "pending"}
        assert request_id in waiting_requests  # Should not be deleted

    def test_status_endpoint_in_progress_status(self, client):
        """Test status endpoint returns in_progress status."""
        # Arrange
        request_id = "in-progress-request"
        waiting_requests[request_id] = PollingRequest(
            request_id=request_id,
            status=Status.IN_PROGRESS,
            result=None,
            error=None,
        )

        # Act
        response = client.get(f"/inference/status/{request_id}")

        # Assert
        assert response.status_code == 200
        assert response.json() == {"status": "in_progress"}
        assert request_id in waiting_requests  # Should not be deleted

    def test_status_endpoint_success_status(self, client):
        """Test status endpoint returns success status and deletes request."""
        # Arrange
        request_id = "success-request"
        waiting_requests[request_id] = PollingRequest(
            request_id=request_id,
            status=Status.SUCCESS,
            result="This is the result",
            error=None,
        )

        # Act
        response = client.get(f"/inference/status/{request_id}")

        # Assert
        assert response.status_code == 200
        assert response.json() == {"status": "success", "result": "This is the result"}
        assert request_id not in waiting_requests  # Should be deleted

    def test_status_endpoint_error_status(self, client):
        """Test status endpoint returns error status and deletes request."""
        # Arrange
        request_id = "error-request"
        waiting_requests[request_id] = PollingRequest(
            request_id=request_id,
            status=Status.ERROR,
            result=None,
            error="Something went wrong",
        )

        # Act
        response = client.get(f"/inference/status/{request_id}")

        # Assert
        assert response.status_code == APIStatus.HTTP_500_INTERNAL_SERVER_ERROR
        assert response.json() == {"status": "error", "error": "Something went wrong"}
        assert request_id not in waiting_requests  # Should be deleted


class TestCompleteTask:
    """Test complete_task async function."""

    @pytest.mark.asyncio
    @patch("app.main.ctx")
    @patch("app.main.client")
    async def test_complete_task_success_with_context(self, mock_client, mock_ctx):
        """Test complete_task successfully processes request with context."""
        # Arrange
        request_id = "task-request-1"
        key = "test-key"
        message = CompleteRequest(
            message="Hello",
            metadata={"user": "test"},
            needs_context=True,
        )

        waiting_requests[request_id] = PollingRequest(
            request_id=request_id,
            status=Status.PENDING,
            result=None,
            error=None,
        )

        mock_ctx.contextualize_prompt = MagicMock(return_value="contextualized prompt")
        mock_ctx.context_configs = {
            key: ContextConfig(
                max_context_length=1000,
                context_invalidation_time_seconds=300,
                system_instruction="Test instruction",
            )
        }
        mock_ctx.add_message_to_context = MagicMock()
        mock_client.prompt_model = AsyncMock(return_value="AI response")

        # Act
        await complete_task(request_id, key, message)

        # Assert
        assert waiting_requests[request_id].status == Status.SUCCESS
        assert waiting_requests[request_id].result == "AI response"
        assert waiting_requests[request_id].error is None
        mock_ctx.contextualize_prompt.assert_called_once()
        mock_client.prompt_model.assert_called_once()
        mock_ctx.add_message_to_context.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.main.ctx")
    @patch("app.main.client")
    async def test_complete_task_success_without_context(self, mock_client, mock_ctx):
        """Test complete_task successfully processes request without context."""
        # Arrange
        request_id = "task-request-2"
        key = "test-key"
        message = CompleteRequest(
            message="Hello",
            metadata={"user": "test"},
            needs_context=False,
        )

        waiting_requests[request_id] = PollingRequest(
            request_id=request_id,
            status=Status.PENDING,
            result=None,
            error=None,
        )

        mock_ctx.context_configs = {
            key: ContextConfig(
                max_context_length=1000,
                context_invalidation_time_seconds=300,
                system_instruction="Test instruction",
            )
        }
        mock_ctx.add_message_to_context = MagicMock()
        mock_client.prompt_model = AsyncMock(return_value="AI response")

        # Act
        await complete_task(request_id, key, message)

        # Assert
        assert waiting_requests[request_id].status == Status.SUCCESS
        assert waiting_requests[request_id].result == "AI response"
        mock_ctx.contextualize_prompt.assert_not_called()
        mock_client.prompt_model.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.main.ctx")
    @patch("app.main.client")
    async def test_complete_task_handles_value_error(self, mock_client, mock_ctx):
        """Test complete_task handles ValueError gracefully."""
        # Arrange
        request_id = "task-request-error"
        key = "test-key"
        message = CompleteRequest(
            message="Hello",
            metadata={},
            needs_context=False,
        )

        waiting_requests[request_id] = PollingRequest(
            request_id=request_id,
            status=Status.PENDING,
            result=None,
            error=None,
        )

        mock_ctx.context_configs = {
            key: ContextConfig(
                max_context_length=1000,
                context_invalidation_time_seconds=300,
                system_instruction="Test",
            )
        }
        mock_client.prompt_model = AsyncMock(side_effect=ValueError("Invalid input"))

        # Act
        await complete_task(request_id, key, message)

        # Assert
        assert waiting_requests[request_id].status == Status.ERROR
        assert waiting_requests[request_id].error == "Invalid input"
        assert waiting_requests[request_id].result is None

    @pytest.mark.asyncio
    @patch("app.main.ctx")
    @patch("app.main.client")
    async def test_complete_task_handles_generic_exception(self, mock_client, mock_ctx):
        """Test complete_task handles generic exceptions gracefully."""
        # Arrange
        request_id = "task-request-exception"
        key = "test-key"
        message = CompleteRequest(
            message="Hello",
            metadata={},
            needs_context=False,
        )

        waiting_requests[request_id] = PollingRequest(
            request_id=request_id,
            status=Status.PENDING,
            result=None,
            error=None,
        )

        mock_ctx.context_configs = {
            key: ContextConfig(
                max_context_length=1000,
                context_invalidation_time_seconds=300,
                system_instruction="Test",
            )
        }
        mock_client.prompt_model = AsyncMock(side_effect=Exception("Unexpected error"))

        # Act
        await complete_task(request_id, key, message)

        # Assert
        assert waiting_requests[request_id].status == Status.ERROR
        assert waiting_requests[request_id].error == "Unexpected error"
        assert waiting_requests[request_id].result is None

    @pytest.mark.asyncio
    @patch("app.main.ctx")
    @patch("app.main.client")
    async def test_complete_task_updates_status_to_in_progress(self, mock_client, mock_ctx):
        """Test complete_task updates status to IN_PROGRESS immediately."""
        # Arrange
        request_id = "task-request-status"
        key = "test-key"
        message = CompleteRequest(
            message="Hello",
            metadata={},
            needs_context=False,
        )

        waiting_requests[request_id] = PollingRequest(
            request_id=request_id,
            status=Status.PENDING,
            result=None,
            error=None,
        )

        mock_ctx.context_configs = {
            key: ContextConfig(
                max_context_length=1000,
                context_invalidation_time_seconds=300,
                system_instruction="Test",
            )
        }
        mock_ctx.add_message_to_context = MagicMock()

        # Create a mock that checks status when called
        async def check_status_on_call(*args, **kwargs):
            assert waiting_requests[request_id].status == Status.IN_PROGRESS
            return "response"

        mock_client.prompt_model = AsyncMock(side_effect=check_status_on_call)

        # Act
        await complete_task(request_id, key, message)

        # Assert
        # Status should be SUCCESS after completion
        assert waiting_requests[request_id].status == Status.SUCCESS


class TestLifespan:
    """Test lifespan context manager."""

    @pytest.mark.asyncio
    @patch("app.main.shutdown_rabbitmq", new_callable=AsyncMock)
    @patch("app.main.initialize_rabbitmq", new_callable=AsyncMock)
    async def test_lifespan_initializes_rabbitmq(self, mock_init, mock_shutdown):
        """Test that lifespan initializes RabbitMQ on startup."""
        # Arrange
        from app.main import lifespan

        # Act
        async with lifespan(app):
            # Assert - initialization should be called
            mock_init.assert_called_once()

        # Assert - shutdown should be called after context exit
        mock_shutdown.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.main.shutdown_rabbitmq", new_callable=AsyncMock)
    @patch("app.main.initialize_rabbitmq", new_callable=AsyncMock)
    async def test_lifespan_shuts_down_rabbitmq(self, mock_init, mock_shutdown):
        """Test that lifespan shuts down RabbitMQ on exit."""
        # Arrange
        from app.main import lifespan

        # Act
        async with lifespan(app):
            pass

        # Assert
        mock_shutdown.assert_called_once()
