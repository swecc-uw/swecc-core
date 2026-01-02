"""
Tests for S3Client utility.
"""

import os
import unittest
from unittest.mock import MagicMock, patch

from aws.s3 import S3Client


class S3ClientTests(unittest.TestCase):
    """Test S3Client singleton and operations"""

    def setUp(self):
        """Reset singleton instance before each test"""
        S3Client.instance = None

    def tearDown(self):
        """Clean up singleton instance after each test"""
        S3Client.instance = None

    @patch.dict(
        os.environ,
        {
            "AWS_ACCESS_KEY_ID": "test_access_key",
            "AWS_SECRET_ACCESS_KEY": "test_secret_key",
        },
    )
    @patch("aws.s3.boto3.client")
    def test_s3_client_initialization_success(self, mock_boto_client):
        """Test successful S3Client initialization with valid credentials"""
        # Arrange
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3

        # Act
        client = S3Client()

        # Assert
        self.assertIsNotNone(client)
        self.assertEqual(client.access_key_id, "test_access_key")
        self.assertEqual(client.secret_access_key, "test_secret_key")
        mock_boto_client.assert_called_once_with(
            "s3",
            aws_access_key_id="test_access_key",
            aws_secret_access_key="test_secret_key",
            region_name="us-west-2",
        )
        self.assertTrue(client._initialized)

    @patch.dict(os.environ, {}, clear=True)
    def test_s3_client_initialization_missing_credentials(self):
        """Test S3Client initialization fails without credentials"""
        # Act & Assert
        with self.assertRaises(ValueError) as context:
            S3Client()
        self.assertIn("AWS credentials not found", str(context.exception))

    @patch.dict(
        os.environ,
        {
            "AWS_ACCESS_KEY_ID": "test_access_key",
            "AWS_SECRET_ACCESS_KEY": "",
        },
    )
    def test_s3_client_initialization_empty_secret_key(self):
        """Test S3Client initialization fails with empty secret key"""
        # Act & Assert
        with self.assertRaises(ValueError) as context:
            S3Client()
        self.assertIn("AWS credentials not found", str(context.exception))

    @patch.dict(
        os.environ,
        {
            "AWS_ACCESS_KEY_ID": "",
            "AWS_SECRET_ACCESS_KEY": "test_secret_key",
        },
    )
    def test_s3_client_initialization_empty_access_key(self):
        """Test S3Client initialization fails with empty access key"""
        # Act & Assert
        with self.assertRaises(ValueError) as context:
            S3Client()
        self.assertIn("AWS credentials not found", str(context.exception))

    @patch.dict(
        os.environ,
        {
            "AWS_ACCESS_KEY_ID": "  test_access_key  ",
            "AWS_SECRET_ACCESS_KEY": "  test_secret_key  ",
        },
    )
    @patch("aws.s3.boto3.client")
    def test_s3_client_strips_whitespace_from_credentials(self, mock_boto_client):
        """Test S3Client strips whitespace from credentials"""
        # Arrange
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3

        # Act
        client = S3Client()

        # Assert
        mock_boto_client.assert_called_once_with(
            "s3",
            aws_access_key_id="test_access_key",
            aws_secret_access_key="test_secret_key",
            region_name="us-west-2",
        )

    @patch.dict(
        os.environ,
        {
            "AWS_ACCESS_KEY_ID": "test_access_key",
            "AWS_SECRET_ACCESS_KEY": "test_secret_key",
        },
    )
    @patch("aws.s3.boto3.client")
    def test_s3_client_singleton_pattern(self, mock_boto_client):
        """Test S3Client follows singleton pattern"""
        # Arrange
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3

        # Act
        client1 = S3Client()
        client2 = S3Client()

        # Assert
        self.assertIs(client1, client2)
        # boto3.client should only be called once due to singleton
        self.assertEqual(mock_boto_client.call_count, 1)

    @patch.dict(
        os.environ,
        {
            "AWS_ACCESS_KEY_ID": "test_access_key",
            "AWS_SECRET_ACCESS_KEY": "test_secret_key",
        },
    )
    @patch("aws.s3.boto3.client")
    def test_get_presigned_url_default_expiration(self, mock_boto_client):
        """Test generating presigned URL with default expiration"""
        # Arrange
        mock_s3 = MagicMock()
        mock_s3.generate_presigned_url.return_value = "https://s3.amazonaws.com/presigned-url"
        mock_boto_client.return_value = mock_s3
        client = S3Client()

        # Act
        url = client.get_presigned_url("test-bucket", "test-key.pdf")

        # Assert
        self.assertEqual(url, "https://s3.amazonaws.com/presigned-url")
        mock_s3.generate_presigned_url.assert_called_once_with(
            ClientMethod="put_object",
            Params={
                "Bucket": "test-bucket",
                "Key": "test-key.pdf",
                "ContentType": "application/pdf",
            },
            ExpiresIn=3600,
        )

    @patch.dict(
        os.environ,
        {
            "AWS_ACCESS_KEY_ID": "test_access_key",
            "AWS_SECRET_ACCESS_KEY": "test_secret_key",
        },
    )
    @patch("aws.s3.boto3.client")
    def test_get_presigned_url_custom_expiration(self, mock_boto_client):
        """Test generating presigned URL with custom expiration"""
        # Arrange
        mock_s3 = MagicMock()
        mock_s3.generate_presigned_url.return_value = "https://s3.amazonaws.com/presigned-url"
        mock_boto_client.return_value = mock_s3
        client = S3Client()

        # Act
        url = client.get_presigned_url("test-bucket", "test-key.pdf", expiration=7200)

        # Assert
        self.assertEqual(url, "https://s3.amazonaws.com/presigned-url")
        mock_s3.generate_presigned_url.assert_called_once_with(
            ClientMethod="put_object",
            Params={
                "Bucket": "test-bucket",
                "Key": "test-key.pdf",
                "ContentType": "application/pdf",
            },
            ExpiresIn=7200,
        )

    @patch.dict(
        os.environ,
        {
            "AWS_ACCESS_KEY_ID": "test_access_key",
            "AWS_SECRET_ACCESS_KEY": "test_secret_key",
        },
    )
    @patch("aws.s3.boto3.client")
    def test_get_presigned_url_with_special_characters(self, mock_boto_client):
        """Test generating presigned URL with special characters in key"""
        # Arrange
        mock_s3 = MagicMock()
        mock_s3.generate_presigned_url.return_value = "https://s3.amazonaws.com/presigned-url"
        mock_boto_client.return_value = mock_s3
        client = S3Client()

        # Act
        url = client.get_presigned_url("test-bucket", "user/123/resume file.pdf")

        # Assert
        self.assertEqual(url, "https://s3.amazonaws.com/presigned-url")
        mock_s3.generate_presigned_url.assert_called_once_with(
            ClientMethod="put_object",
            Params={
                "Bucket": "test-bucket",
                "Key": "user/123/resume file.pdf",
                "ContentType": "application/pdf",
            },
            ExpiresIn=3600,
        )
