"""
Tests for S3Client class in app.aws.s3 module.
"""

import os
from unittest.mock import MagicMock, patch

import pytest
from app.aws.s3 import S3Client


class TestS3Client:
    """Test S3Client singleton class."""

    def test_singleton_pattern(self, mock_env_vars):
        """Test S3Client follows singleton pattern."""
        # Arrange
        with patch("app.aws.s3.boto3.client"):
            # Act
            client1 = S3Client()
            client2 = S3Client()

            # Assert
            assert client1 is client2

    def test_initialization_success(self, mock_env_vars):
        """Test successful S3Client initialization with valid credentials."""
        # Arrange
        with patch("app.aws.s3.boto3.client") as mock_boto_client:
            mock_s3 = MagicMock()
            mock_boto_client.return_value = mock_s3

            # Act
            client = S3Client()

            # Assert
            assert client.access_key_id == "test_access_key"
            assert client.secret_access_key == "test_secret_key"
            assert client.bucket_name == "test-bucket"
            assert client._initialized is True
            mock_boto_client.assert_called_once_with(
                "s3",
                aws_access_key_id="test_access_key",
                aws_secret_access_key="test_secret_key",
            )

    def test_initialization_missing_access_key(self, monkeypatch):
        """Test S3Client initialization fails without access key."""
        # Arrange
        monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test_secret")
        monkeypatch.setenv("AWS_BUCKET_NAME", "test-bucket")

        # Act & Assert
        with pytest.raises(ValueError, match="AWS credentials not found"):
            S3Client()

    def test_initialization_missing_secret_key(self, monkeypatch):
        """Test S3Client initialization fails without secret key."""
        # Arrange
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test_access")
        monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
        monkeypatch.setenv("AWS_BUCKET_NAME", "test-bucket")

        # Act & Assert
        with pytest.raises(ValueError, match="AWS credentials not found"):
            S3Client()

    def test_initialization_empty_access_key(self, monkeypatch):
        """Test S3Client initialization fails with empty access key."""
        # Arrange
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test_secret")
        monkeypatch.setenv("AWS_BUCKET_NAME", "test-bucket")

        # Act & Assert
        with pytest.raises(ValueError, match="AWS credentials not found"):
            S3Client()

    def test_initialization_empty_secret_key(self, monkeypatch):
        """Test S3Client initialization fails with empty secret key."""
        # Arrange
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test_access")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "")
        monkeypatch.setenv("AWS_BUCKET_NAME", "test-bucket")

        # Act & Assert
        with pytest.raises(ValueError, match="AWS credentials not found"):
            S3Client()

    def test_initialization_missing_bucket_name(self, monkeypatch):
        """Test S3Client initialization fails without bucket name."""
        # Arrange
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test_access")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test_secret")
        monkeypatch.delenv("AWS_BUCKET_NAME", raising=False)

        # Act & Assert
        with patch("app.aws.s3.boto3.client"):
            with pytest.raises(ValueError, match="AWS bucket name not found"):
                S3Client()

    def test_initialization_empty_bucket_name(self, monkeypatch):
        """Test S3Client initialization fails with empty bucket name."""
        # Arrange
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test_access")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test_secret")
        monkeypatch.setenv("AWS_BUCKET_NAME", "")

        # Act & Assert
        with patch("app.aws.s3.boto3.client"):
            with pytest.raises(ValueError, match="AWS bucket name not found"):
                S3Client()

    def test_retrieve_object_success(self, mock_env_vars):
        """Test successful object retrieval from S3."""
        # Arrange
        with patch("app.aws.s3.boto3.client") as mock_boto_client:
            mock_s3 = MagicMock()
            mock_body = MagicMock()
            mock_body.read.return_value = b"file content"
            mock_s3.get_object.return_value = {"Body": mock_body}
            mock_boto_client.return_value = mock_s3

            client = S3Client()

            # Act
            result = client.retrieve_object("test-key.pdf")

            # Assert
            assert result == b"file content"
            mock_s3.get_object.assert_called_once_with(Bucket="test-bucket", Key="test-key.pdf")

    def test_retrieve_object_with_path(self, mock_env_vars):
        """Test retrieving object with path in key."""
        # Arrange
        with patch("app.aws.s3.boto3.client") as mock_boto_client:
            mock_s3 = MagicMock()
            mock_body = MagicMock()
            mock_body.read.return_value = b"nested file content"
            mock_s3.get_object.return_value = {"Body": mock_body}
            mock_boto_client.return_value = mock_s3

            client = S3Client()

            # Act
            result = client.retrieve_object("user/123/resume.pdf")

            # Assert
            assert result == b"nested file content"
            mock_s3.get_object.assert_called_once_with(
                Bucket="test-bucket", Key="user/123/resume.pdf"
            )

    def test_retrieve_object_error_handling(self, mock_env_vars):
        """Test retrieve_object handles S3 errors."""
        # Arrange
        with patch("app.aws.s3.boto3.client") as mock_boto_client:
            mock_s3 = MagicMock()
            mock_s3.get_object.side_effect = Exception("S3 Error: Object not found")
            mock_boto_client.return_value = mock_s3

            client = S3Client()

            # Act & Assert
            with pytest.raises(Exception, match="S3 Error"):
                client.retrieve_object("nonexistent-key.pdf")

    def test_retrieve_object_empty_file(self, mock_env_vars):
        """Test retrieving an empty file from S3."""
        # Arrange
        with patch("app.aws.s3.boto3.client") as mock_boto_client:
            mock_s3 = MagicMock()
            mock_body = MagicMock()
            mock_body.read.return_value = b""
            mock_s3.get_object.return_value = {"Body": mock_body}
            mock_boto_client.return_value = mock_s3

            client = S3Client()

            # Act
            result = client.retrieve_object("empty-file.txt")

            # Assert
            assert result == b""

    def test_retrieve_object_large_file(self, mock_env_vars):
        """Test retrieving a large file from S3."""
        # Arrange
        with patch("app.aws.s3.boto3.client") as mock_boto_client:
            mock_s3 = MagicMock()
            mock_body = MagicMock()
            large_content = b"x" * 10000  # 10KB
            mock_body.read.return_value = large_content
            mock_s3.get_object.return_value = {"Body": mock_body}
            mock_boto_client.return_value = mock_s3

            client = S3Client()

            # Act
            result = client.retrieve_object("large-file.bin")

            # Assert
            assert result == large_content
            assert len(result) == 10000

    def test_singleton_initialization_only_once(self, mock_env_vars):
        """Test that boto3 client is only initialized once for singleton."""
        # Arrange
        with patch("app.aws.s3.boto3.client") as mock_boto_client:
            mock_s3 = MagicMock()
            mock_boto_client.return_value = mock_s3

            # Act
            client1 = S3Client()
            client2 = S3Client()
            client3 = S3Client()

            # Assert
            assert client1 is client2 is client3
            # boto3.client should only be called once
            assert mock_boto_client.call_count == 1

    def test_retrieve_object_special_characters_in_key(self, mock_env_vars):
        """Test retrieving object with special characters in key."""
        # Arrange
        with patch("app.aws.s3.boto3.client") as mock_boto_client:
            mock_s3 = MagicMock()
            mock_body = MagicMock()
            mock_body.read.return_value = b"content"
            mock_s3.get_object.return_value = {"Body": mock_body}
            mock_boto_client.return_value = mock_s3

            client = S3Client()

            # Act
            result = client.retrieve_object("user/test@example.com/resume (1).pdf")

            # Assert
            assert result == b"content"
            mock_s3.get_object.assert_called_once_with(
                Bucket="test-bucket", Key="user/test@example.com/resume (1).pdf"
            )

    def test_multiple_retrieve_operations(self, mock_env_vars):
        """Test multiple retrieve operations use the same client."""
        # Arrange
        with patch("app.aws.s3.boto3.client") as mock_boto_client:
            mock_s3 = MagicMock()
            mock_body1 = MagicMock()
            mock_body1.read.return_value = b"content1"
            mock_body2 = MagicMock()
            mock_body2.read.return_value = b"content2"

            mock_s3.get_object.side_effect = [
                {"Body": mock_body1},
                {"Body": mock_body2},
            ]
            mock_boto_client.return_value = mock_s3

            client = S3Client()

            # Act
            result1 = client.retrieve_object("file1.pdf")
            result2 = client.retrieve_object("file2.pdf")

            # Assert
            assert result1 == b"content1"
            assert result2 == b"content2"
            assert mock_s3.get_object.call_count == 2

    def test_bucket_name_from_environment(self, monkeypatch):
        """Test that bucket name is correctly read from environment."""
        # Arrange
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test_key")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test_secret")
        monkeypatch.setenv("AWS_BUCKET_NAME", "my-custom-bucket")

        # Act
        with patch("app.aws.s3.boto3.client"):
            client = S3Client()

            # Assert
            assert client.bucket_name == "my-custom-bucket"

    def test_credentials_from_environment(self, monkeypatch):
        """Test that credentials are correctly read from environment."""
        # Arrange
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "custom_access_key")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "custom_secret_key")
        monkeypatch.setenv("AWS_BUCKET_NAME", "test-bucket")

        # Act
        with patch("app.aws.s3.boto3.client") as mock_boto_client:
            client = S3Client()

            # Assert
            assert client.access_key_id == "custom_access_key"
            assert client.secret_access_key == "custom_secret_key"
            mock_boto_client.assert_called_once_with(
                "s3",
                aws_access_key_id="custom_access_key",
                aws_secret_access_key="custom_secret_key",
            )
