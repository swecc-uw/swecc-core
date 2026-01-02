"""
Pytest configuration and shared fixtures for AI service tests.
"""

import os
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

# Set environment variables BEFORE any app imports
# This prevents initialization errors during test collection
os.environ.setdefault("GEMINI_API_KEY", "test_api_key")
os.environ.setdefault("GEMINI_MODEL_NAME", "test-model")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test_access_key")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test_secret_key")
os.environ.setdefault("AWS_BUCKET_NAME", "test-bucket")
os.environ.setdefault("AI_RABBIT_USER", "test_user")
os.environ.setdefault("AI_RABBIT_PASS", "test_pass")
os.environ.setdefault("RABBIT_HOST", "test_host")
os.environ.setdefault("RABBIT_PORT", "5672")
os.environ.setdefault("RABBIT_VHOST", "/")


@pytest.fixture(autouse=True)
def mock_env_for_imports(monkeypatch):
    """Set environment variables before any imports to prevent initialization errors."""
    monkeypatch.setenv("GEMINI_API_KEY", "test_api_key")
    monkeypatch.setenv("GEMINI_MODEL_NAME", "test-model")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test_access_key")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test_secret_key")
    monkeypatch.setenv("AWS_BUCKET_NAME", "test-bucket")


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset singleton instances before each test."""
    from app.aws.s3 import S3Client
    from app.llm.context import ContextManager
    from app.llm.gemini import Gemini
    from app.mq.core.connection_manager import ConnectionManager

    # Reset singletons
    ContextManager._instance = None
    Gemini._instance = None
    S3Client.instance = None
    ConnectionManager.instance = None

    yield

    # Clean up after test
    ContextManager._instance = None
    Gemini._instance = None
    S3Client.instance = None
    ConnectionManager.instance = None


@pytest.fixture
def mock_env_vars(monkeypatch):
    """Set up mock environment variables for testing."""
    monkeypatch.setenv("GEMINI_API_KEY", "test_api_key")
    monkeypatch.setenv("GEMINI_MODEL_NAME", "test-model")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test_access_key")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test_secret_key")
    monkeypatch.setenv("AWS_BUCKET_NAME", "test-bucket")
    monkeypatch.setenv("AI_RABBIT_USER", "test_user")
    monkeypatch.setenv("AI_RABBIT_PASS", "test_pass")
    monkeypatch.setenv("RABBIT_HOST", "test_host")
    monkeypatch.setenv("RABBIT_PORT", "5672")
    monkeypatch.setenv("RABBIT_VHOST", "/")


@pytest.fixture
def sample_message():
    """Create a sample Message instance for testing."""
    from app.llm.message import Message

    return Message(
        message="Test message",
        response="Test response",
        timestamp=datetime(2024, 1, 1, 12, 0, 0),
        metadata={"author": "test_user", "is_authorized": True},
    )


@pytest.fixture
def sample_context_config():
    """Create sample context configuration."""
    return {
        "max_context_length": 1000,
        "context_invalidation_time_seconds": 600,
        "system_instruction": "You are a helpful assistant.",
    }
