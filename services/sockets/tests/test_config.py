"""Tests for configuration module."""

import os
from unittest.mock import patch

import pytest
from app.config import Settings, settings


class TestSettings:
    """Test Settings configuration class."""

    def test_default_settings(self):
        """Test that default settings are loaded correctly."""
        # Arrange & Act
        test_settings = Settings()

        # Assert
        assert test_settings.jwt_algorithm == "HS256"
        assert test_settings.host == "0.0.0.0"
        assert test_settings.port == 8004
        assert isinstance(test_settings.cors_origins, list)
        assert len(test_settings.cors_origins) > 0

    def test_jwt_settings(self):
        """Test JWT-related settings."""
        # Arrange & Act
        test_settings = Settings()

        # Assert
        assert test_settings.jwt_secret_key is not None
        assert test_settings.jwt_algorithm == "HS256"

    def test_database_settings(self):
        """Test database configuration settings."""
        # Arrange & Act
        test_settings = Settings()

        # Assert
        assert test_settings.db_host is not None
        assert test_settings.db_port == 5432
        assert test_settings.db_name is not None
        assert test_settings.db_user is not None
        assert test_settings.db_password is not None

    def test_redis_settings(self):
        """Test Redis configuration settings."""
        # Arrange & Act
        test_settings = Settings()

        # Assert
        assert test_settings.redis_host is not None
        assert test_settings.redis_port == 6379

    def test_cors_origins_contains_expected_urls(self):
        """Test that CORS origins contain expected URLs."""
        # Arrange & Act
        test_settings = Settings()

        # Assert
        assert "http://localhost:8000" in test_settings.cors_origins
        assert "http://localhost:3000" in test_settings.cors_origins

    @patch.dict(os.environ, {"JWT_SECRET": "test_secret"})
    def test_jwt_secret_from_env(self):
        """Test that JWT secret can be loaded from environment."""
        # Arrange & Act
        test_settings = Settings()

        # Assert
        assert test_settings.jwt_secret_key == "test_secret"

    @patch.dict(os.environ, {"DB_HOST": "custom_host", "DB_PORT": "5433"})
    def test_database_settings_from_env(self):
        """Test that database settings can be loaded from environment."""
        # Arrange & Act
        test_settings = Settings()

        # Assert
        assert test_settings.db_host == "custom_host"
        assert test_settings.db_port == 5433

    @patch.dict(os.environ, {"REDIS_HOST": "custom_redis", "REDIS_PORT": "6380"})
    def test_redis_settings_from_env(self):
        """Test that Redis settings can be loaded from environment."""
        # Arrange & Act
        test_settings = Settings()

        # Assert
        assert test_settings.redis_host == "custom_redis"
        assert test_settings.redis_port == 6380

    def test_settings_singleton_exists(self):
        """Test that settings singleton is available."""
        # Arrange & Act & Assert
        assert settings is not None
        assert isinstance(settings, Settings)

    def test_settings_immutability(self):
        """Test that Settings is a Pydantic model with proper validation."""
        # Arrange
        test_settings = Settings()

        # Act & Assert
        # Pydantic models are not truly immutable but validate on assignment
        with pytest.raises((ValueError, TypeError)):
            test_settings.port = "invalid"  # Should fail type validation
