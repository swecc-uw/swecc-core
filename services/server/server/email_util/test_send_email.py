"""
Tests for email sending utilities.
"""

import os
import unittest
from unittest.mock import MagicMock, patch

from email_util.send_email import send_email


class SendEmailTests(unittest.TestCase):
    """Test send_email function"""

    @patch("email_util.send_email.DJANGO_DEBUG", True)
    @patch("email_util.send_email.logger")
    def test_send_email_debug_mode_logs_only(self, mock_logger):
        """Test send_email in debug mode only logs without sending"""
        # Act
        result = send_email(
            from_email="from@example.com",
            to_email="to@example.com",
            subject="Test Subject",
            html_content="<p>Test content</p>",
        )

        # Assert
        self.assertIsNone(result)
        mock_logger.info.assert_called_once()
        self.assertIn("to@example.com", mock_logger.info.call_args[0][0])
        self.assertIn("Test Subject", mock_logger.info.call_args[0][0])

    @patch("email_util.send_email.DJANGO_DEBUG", True)
    @patch("email_util.send_email.SENDGRID_API_KEY", "test_key")
    @patch("email_util.send_email.SendGridAPIClient")
    @patch("email_util.send_email.logger")
    def test_send_email_debug_mode_with_force_send(self, mock_logger, mock_sendgrid_client):
        """Test send_email in debug mode with force_send=True"""
        # Arrange
        mock_sg_instance = MagicMock()
        mock_response = MagicMock()
        mock_sg_instance.send.return_value = mock_response
        mock_sendgrid_client.return_value = mock_sg_instance

        # Act
        result = send_email(
            from_email="from@example.com",
            to_email="to@example.com",
            subject="Test Subject",
            html_content="<p>Test content</p>",
            force_send=True,
        )

        # Assert
        self.assertEqual(result, mock_response)
        mock_sg_instance.send.assert_called_once()
        mock_logger.info.assert_not_called()

    @patch("email_util.send_email.DJANGO_DEBUG", False)
    @patch("email_util.send_email.SENDGRID_API_KEY", "test_api_key")
    @patch("email_util.send_email.SendGridAPIClient")
    def test_send_email_production_mode(self, mock_sendgrid_client):
        """Test send_email in production mode sends email"""
        # Arrange
        mock_sg_instance = MagicMock()
        mock_response = MagicMock()
        mock_sg_instance.send.return_value = mock_response
        mock_sendgrid_client.return_value = mock_sg_instance

        # Act
        result = send_email(
            from_email="from@example.com",
            to_email="to@example.com",
            subject="Test Subject",
            html_content="<p>Test content</p>",
        )

        # Assert
        self.assertEqual(result, mock_response)
        mock_sendgrid_client.assert_called_once_with("test_api_key")
        mock_sg_instance.send.assert_called_once()

    @patch("email_util.send_email.DJANGO_DEBUG", False)
    @patch("email_util.send_email.SENDGRID_API_KEY", "test_api_key")
    @patch("email_util.send_email.SendGridAPIClient")
    @patch("email_util.send_email.Mail")
    def test_send_email_creates_correct_mail_object(self, mock_mail, mock_sendgrid_client):
        """Test send_email creates Mail object with correct parameters"""
        # Arrange
        mock_sg_instance = MagicMock()
        mock_sendgrid_client.return_value = mock_sg_instance
        mock_mail_instance = MagicMock()
        mock_mail.return_value = mock_mail_instance

        # Act
        send_email(
            from_email="sender@example.com",
            to_email="recipient@example.com",
            subject="Important Email",
            html_content="<h1>Hello World</h1>",
        )

        # Assert
        mock_mail.assert_called_once_with(
            from_email="sender@example.com",
            to_emails="recipient@example.com",
            subject="Important Email",
            html_content="<h1>Hello World</h1>",
        )
        mock_sg_instance.send.assert_called_once_with(mock_mail_instance)

    @patch("email_util.send_email.DJANGO_DEBUG", False)
    @patch("email_util.send_email.SENDGRID_API_KEY", "test_api_key")
    @patch("email_util.send_email.SendGridAPIClient")
    def test_send_email_with_multiple_recipients(self, mock_sendgrid_client):
        """Test send_email with multiple recipients"""
        # Arrange
        mock_sg_instance = MagicMock()
        mock_response = MagicMock()
        mock_sg_instance.send.return_value = mock_response
        mock_sendgrid_client.return_value = mock_sg_instance

        # Act
        result = send_email(
            from_email="from@example.com",
            to_email=["to1@example.com", "to2@example.com"],
            subject="Test Subject",
            html_content="<p>Test content</p>",
        )

        # Assert
        self.assertEqual(result, mock_response)
        mock_sg_instance.send.assert_called_once()

    @patch("email_util.send_email.DJANGO_DEBUG", False)
    @patch("email_util.send_email.SENDGRID_API_KEY", "test_api_key")
    @patch("email_util.send_email.SendGridAPIClient")
    def test_send_email_with_html_content(self, mock_sendgrid_client):
        """Test send_email with rich HTML content"""
        # Arrange
        mock_sg_instance = MagicMock()
        mock_response = MagicMock()
        mock_sg_instance.send.return_value = mock_response
        mock_sendgrid_client.return_value = mock_sg_instance

        html_content = """
        <html>
            <body>
                <h1>Welcome!</h1>
                <p>This is a <strong>test</strong> email.</p>
            </body>
        </html>
        """

        # Act
        result = send_email(
            from_email="from@example.com",
            to_email="to@example.com",
            subject="HTML Email",
            html_content=html_content,
        )

        # Assert
        self.assertEqual(result, mock_response)
        mock_sg_instance.send.assert_called_once()

    @patch("email_util.send_email.DJANGO_DEBUG", True)
    @patch("email_util.send_email.logger")
    def test_send_email_debug_mode_different_subjects(self, mock_logger):
        """Test send_email logs different subjects correctly"""
        # Act
        send_email("from@example.com", "to@example.com", "Subject 1", "<p>Content 1</p>")
        send_email("from@example.com", "to@example.com", "Subject 2", "<p>Content 2</p>")

        # Assert
        self.assertEqual(mock_logger.info.call_count, 2)
