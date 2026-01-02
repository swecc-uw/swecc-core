"""
Tests for config.py module.

Tests cover:
- Settings class default values
- Settings configuration from environment variables
- CORS origins configuration
"""

import os
from unittest.mock import patch

import pytest
from app.config import Settings, settings


class TestSettings:
    """Test Settings configuration class."""

    def test_settings_default_host(self):
        """Test that Settings has correct default host."""
        # Arrange & Act
        config = Settings()

        # Assert
        assert config.host == "0.0.0.0"

    def test_settings_default_port(self):
        """Test that Settings has correct default port."""
        # Arrange & Act
        config = Settings()

        # Assert
        assert config.port == 8004

    def test_settings_default_cors_origins(self):
        """Test that Settings has correct default CORS origins."""
        # Arrange & Act
        config = Settings()

        # Assert
        assert isinstance(config.cors_origins, list)
        assert len(config.cors_origins) == 4
        assert "http://localhost:8000" in config.cors_origins
        assert "http://localhost:80" in config.cors_origins
        assert "http://localhost:3000" in config.cors_origins
        assert "http://api.swecc.org" in config.cors_origins

    def test_settings_custom_host(self):
        """Test creating Settings with custom host."""
        # Arrange & Act
        config = Settings(host="127.0.0.1")

        # Assert
        assert config.host == "127.0.0.1"

    def test_settings_custom_port(self):
        """Test creating Settings with custom port."""
        # Arrange & Act
        config = Settings(port=9000)

        # Assert
        assert config.port == 9000

    def test_settings_custom_cors_origins(self):
        """Test creating Settings with custom CORS origins."""
        # Arrange
        custom_origins = ["http://example.com", "http://test.com"]

        # Act
        config = Settings(cors_origins=custom_origins)

        # Assert
        assert config.cors_origins == custom_origins

    def test_settings_all_custom_values(self):
        """Test creating Settings with all custom values."""
        # Arrange
        custom_host = "192.168.1.1"
        custom_port = 5000
        custom_origins = ["http://custom.com"]

        # Act
        config = Settings(
            host=custom_host,
            port=custom_port,
            cors_origins=custom_origins,
        )

        # Assert
        assert config.host == custom_host
        assert config.port == custom_port
        assert config.cors_origins == custom_origins

    def test_settings_is_pydantic_model(self):
        """Test that Settings is a Pydantic BaseModel."""
        # Arrange & Act
        config = Settings()

        # Assert
        assert hasattr(config, "model_dump")
        assert hasattr(config, "model_validate")

    def test_settings_model_dump(self):
        """Test that Settings can be dumped to dict."""
        # Arrange
        config = Settings()

        # Act
        data = config.model_dump()

        # Assert
        assert isinstance(data, dict)
        assert "host" in data
        assert "port" in data
        assert "cors_origins" in data
        assert data["host"] == "0.0.0.0"
        assert data["port"] == 8004


class TestSettingsInstance:
    """Test the global settings instance."""

    def test_settings_instance_exists(self):
        """Test that global settings instance exists."""
        # Arrange & Act & Assert
        assert settings is not None

    def test_settings_instance_is_settings_type(self):
        """Test that global settings instance is of type Settings."""
        # Arrange & Act & Assert
        assert isinstance(settings, Settings)

    def test_settings_instance_has_default_values(self):
        """Test that global settings instance has default values."""
        # Arrange & Act & Assert
        assert settings.host == "0.0.0.0"
        assert settings.port == 8004
        assert len(settings.cors_origins) == 4

    def test_settings_cors_origins_contains_localhost(self):
        """Test that settings CORS origins include localhost variants."""
        # Arrange & Act
        origins = settings.cors_origins

        # Assert
        localhost_origins = [o for o in origins if "localhost" in o]
        assert len(localhost_origins) >= 3

    def test_settings_cors_origins_contains_api_domain(self):
        """Test that settings CORS origins include api.swecc.org."""
        # Arrange & Act
        origins = settings.cors_origins

        # Assert
        assert "http://api.swecc.org" in origins
