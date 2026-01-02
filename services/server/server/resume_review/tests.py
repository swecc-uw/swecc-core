from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.utils import timezone
from members.models import User
from rest_framework.test import APIClient, APITestCase

from .models import Resume

# ============================================================================
# Base Test Case
# ============================================================================


class AuthenticatedTestCase(APITestCase):
    """Base test case that automatically mocks authentication"""

    def setUp(self):
        super().setUp()
        self.verified_patcher = patch("custom_auth.permissions.IsVerified.has_permission")

        # Start the patcher
        self.mock_verified_perm = self.verified_patcher.start()

        # Set return value
        self.mock_verified_perm.return_value = True

    def tearDown(self):
        super().tearDown()
        # Stop the patcher
        self.verified_patcher.stop()

    def assertResponse(self, response, expected_status):
        """Helper method to assert response status with detailed error message"""
        try:
            self.assertEqual(
                response.status_code,
                expected_status,
                f"Expected status {expected_status}, got {response.status_code}. Response data: {response.data}",
            )
        except AttributeError:
            self.assertEqual(
                response.status_code,
                expected_status,
                f"Expected status {expected_status}, got {response.status_code}. Response content: {response.content}",
            )


# ============================================================================
# Model Tests
# ============================================================================


class ResumeModelTests(TestCase):
    """Test Resume model"""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            discord_username="testdiscord",
            password="testpass123",
        )

    def test_resume_creation_with_required_fields(self):
        # Arrange & Act
        resume = Resume.objects.create(
            member=self.user,
            file_name="test_resume.pdf",
            file_size=100,
            feedback="",
        )

        # Assert
        self.assertEqual(resume.member, self.user)
        self.assertEqual(resume.file_name, "test_resume.pdf")
        self.assertEqual(resume.file_size, 100)
        self.assertEqual(resume.feedback, "")
        self.assertIsNotNone(resume.created_at)
        self.assertIsNotNone(resume.updated_at)

    def test_resume_creation_with_feedback(self):
        # Arrange & Act
        feedback_text = "Great resume! Consider adding more details."
        resume = Resume.objects.create(
            member=self.user,
            file_name="test_resume.pdf",
            file_size=100,
            feedback=feedback_text,
        )

        # Assert
        self.assertEqual(resume.feedback, feedback_text)

    def test_resume_timestamps(self):
        # Arrange & Act
        resume = Resume.objects.create(
            member=self.user,
            file_name="test_resume.pdf",
            file_size=100,
            feedback="",
        )

        # Assert
        self.assertIsNotNone(resume.created_at)
        self.assertIsNotNone(resume.updated_at)
        self.assertLessEqual(resume.created_at, resume.updated_at)

    def test_resume_updated_at_changes_on_save(self):
        # Arrange
        resume = Resume.objects.create(
            member=self.user,
            file_name="test_resume.pdf",
            file_size=100,
            feedback="",
        )
        original_updated_at = resume.updated_at

        # Act - wait a tiny bit and update
        resume.feedback = "Updated feedback"
        resume.save()

        # Assert
        self.assertGreaterEqual(resume.updated_at, original_updated_at)

    def test_resume_cascade_delete_with_user(self):
        # Arrange
        resume = Resume.objects.create(
            member=self.user,
            file_name="test_resume.pdf",
            file_size=100,
            feedback="",
        )
        resume_id = resume.id

        # Act
        self.user.delete()

        # Assert
        self.assertFalse(Resume.objects.filter(id=resume_id).exists())

    def test_multiple_resumes_per_user(self):
        # Arrange & Act
        resume1 = Resume.objects.create(
            member=self.user,
            file_name="resume1.pdf",
            file_size=100,
            feedback="",
        )
        resume2 = Resume.objects.create(
            member=self.user,
            file_name="resume2.pdf",
            file_size=200,
            feedback="",
        )

        # Assert
        user_resumes = Resume.objects.filter(member=self.user)
        self.assertEqual(user_resumes.count(), 2)
        self.assertIn(resume1, user_resumes)
        self.assertIn(resume2, user_resumes)


# ============================================================================
# View Tests - ResumeUploadView
# ============================================================================


class ResumeUploadViewTests(AuthenticatedTestCase):
    """Test ResumeUploadView"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            discord_username="testdiscord",
            password="testpass123",
        )
        self.verified_group = Group.objects.create(name="is_verified")
        self.user.groups.add(self.verified_group)
        self.client.force_authenticate(user=self.user)

    @patch("resume_review.views.S3Client")
    def test_upload_resume_success(self, mock_s3_client):
        # Arrange
        mock_s3_instance = MagicMock()
        mock_s3_instance.get_presigned_url.return_value = "https://s3.amazonaws.com/presigned-url"
        mock_s3_client.return_value = mock_s3_instance

        # Act
        response = self.client.post(
            "/resume/upload/",
            {
                "file_name": "test_resume.pdf",
                "file_size": 100,
            },
            format="json",
        )

        # Assert
        self.assertResponse(response, 201)
        self.assertIn("presigned_url", response.data)
        self.assertIn("key", response.data)
        self.assertEqual(response.data["presigned_url"], "https://s3.amazonaws.com/presigned-url")
        self.assertTrue(Resume.objects.filter(member=self.user).exists())

    def test_upload_resume_missing_file_name(self):
        # Act
        response = self.client.post(
            "/resume/upload/",
            {
                "file_size": 100,
            },
            format="json",
        )

        # Assert
        self.assertResponse(response, 400)
        self.assertEqual(response.data["error"], "File name or file size not provided.")

    def test_upload_resume_missing_file_size(self):
        # Act
        response = self.client.post(
            "/resume/upload/",
            {
                "file_name": "test_resume.pdf",
            },
            format="json",
        )

        # Assert
        self.assertResponse(response, 400)
        self.assertEqual(response.data["error"], "File name or file size not provided.")

    def test_upload_resume_file_too_large(self):
        # Act
        response = self.client.post(
            "/resume/upload/",
            {
                "file_name": "test_resume.pdf",
                "file_size": 501,  # MAX_FILE_SIZE is 500
            },
            format="json",
        )

        # Assert
        self.assertResponse(response, 400)
        self.assertEqual(response.data["error"], "File size too large.")

    @patch("resume_review.views.S3Client")
    def test_upload_resume_deletes_oldest_when_max_reached(self, mock_s3_client):
        # Arrange
        mock_s3_instance = MagicMock()
        mock_s3_instance.get_presigned_url.return_value = "https://s3.amazonaws.com/presigned-url"
        mock_s3_client.return_value = mock_s3_instance

        # Create 5 resumes (MAX_RESUME_COUNT)
        for i in range(5):
            Resume.objects.create(
                member=self.user,
                file_name=f"resume_{i}.pdf",
                file_size=100,
                feedback="",
            )

        oldest_resume = Resume.objects.filter(member=self.user).order_by("created_at").first()
        oldest_resume_id = oldest_resume.id

        # Act - upload 6th resume
        response = self.client.post(
            "/resume/upload/",
            {
                "file_name": "new_resume.pdf",
                "file_size": 100,
            },
            format="json",
        )

        # Assert
        self.assertResponse(response, 201)
        self.assertEqual(Resume.objects.filter(member=self.user).count(), 5)
        self.assertFalse(Resume.objects.filter(id=oldest_resume_id).exists())
        self.assertTrue(
            Resume.objects.filter(member=self.user, file_name="new_resume.pdf").exists()
        )

    @patch("resume_review.views.S3Client")
    def test_upload_resume_generates_correct_key(self, mock_s3_client):
        # Arrange
        mock_s3_instance = MagicMock()
        mock_s3_instance.get_presigned_url.return_value = "https://s3.amazonaws.com/presigned-url"
        mock_s3_client.return_value = mock_s3_instance

        # Act
        response = self.client.post(
            "/resume/upload/",
            {
                "file_name": "test_resume.pdf",
                "file_size": 100,
            },
            format="json",
        )

        # Assert
        self.assertResponse(response, 201)
        resume = Resume.objects.filter(member=self.user).first()
        expected_key = f"{self.user.id}-{resume.id}-test_resume.pdf"
        self.assertEqual(response.data["key"], expected_key)


# ============================================================================
# View Tests - ResumeListView
# ============================================================================


class ResumeListViewTests(AuthenticatedTestCase):
    """Test ResumeListView"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            discord_username="testdiscord",
            password="testpass123",
        )
        self.verified_group = Group.objects.create(name="is_verified")
        self.user.groups.add(self.verified_group)
        self.client.force_authenticate(user=self.user)

    def test_list_resumes_empty(self):
        # Act
        response = self.client.get("/resume/")

        # Assert
        self.assertResponse(response, 200)
        self.assertEqual(len(response.data), 0)

    def test_list_resumes_single(self):
        # Arrange
        resume = Resume.objects.create(
            member=self.user,
            file_name="test_resume.pdf",
            file_size=100,
            feedback="Great resume!",
        )

        # Act
        response = self.client.get("/resume/")

        # Assert
        self.assertResponse(response, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], resume.id)
        self.assertEqual(response.data[0]["file_name"], "test_resume.pdf")
        self.assertEqual(response.data[0]["file_size"], 100)
        self.assertEqual(response.data[0]["feedback"], "Great resume!")

    def test_list_resumes_multiple_ordered_by_created_at(self):
        # Arrange
        resume1 = Resume.objects.create(
            member=self.user,
            file_name="resume1.pdf",
            file_size=100,
            feedback="",
        )
        resume2 = Resume.objects.create(
            member=self.user,
            file_name="resume2.pdf",
            file_size=200,
            feedback="",
        )
        resume3 = Resume.objects.create(
            member=self.user,
            file_name="resume3.pdf",
            file_size=300,
            feedback="",
        )

        # Act
        response = self.client.get("/resume/")

        # Assert
        self.assertResponse(response, 200)
        self.assertEqual(len(response.data), 3)
        # Should be ordered by -created_at (newest first)
        self.assertEqual(response.data[0]["id"], resume3.id)
        self.assertEqual(response.data[1]["id"], resume2.id)
        self.assertEqual(response.data[2]["id"], resume1.id)

    def test_list_resumes_only_shows_user_resumes(self):
        # Arrange
        other_user = User.objects.create_user(
            username="otheruser",
            email="other@example.com",
            discord_username="otherdiscord",
            password="testpass123",
        )
        Resume.objects.create(
            member=self.user,
            file_name="my_resume.pdf",
            file_size=100,
            feedback="",
        )
        Resume.objects.create(
            member=other_user,
            file_name="other_resume.pdf",
            file_size=200,
            feedback="",
        )

        # Act
        response = self.client.get("/resume/")

        # Assert
        self.assertResponse(response, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["file_name"], "my_resume.pdf")

    def test_list_resumes_includes_all_fields(self):
        # Arrange
        resume = Resume.objects.create(
            member=self.user,
            file_name="test_resume.pdf",
            file_size=100,
            feedback="Excellent work!",
        )

        # Act
        response = self.client.get("/resume/")

        # Assert
        self.assertResponse(response, 200)
        self.assertEqual(len(response.data), 1)
        resume_data = response.data[0]
        self.assertIn("id", resume_data)
        self.assertIn("file_name", resume_data)
        self.assertIn("file_size", resume_data)
        self.assertIn("created_at", resume_data)
        self.assertIn("feedback", resume_data)


# ============================================================================
# View Tests - DevPublishToReview
# ============================================================================


class DevPublishToReviewTests(AuthenticatedTestCase):
    """Test DevPublishToReview view"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            discord_username="testdiscord",
            password="testpass123",
        )
        self.verified_group = Group.objects.create(name="is_verified")
        self.user.groups.add(self.verified_group)
        self.client.force_authenticate(user=self.user)

    @override_settings(DJANGO_DEBUG=True)
    @patch("resume_review.views.dev_publish_to_review_resume")
    def test_publish_to_review_success(self, mock_publish):
        # Arrange
        file_key = f"{self.user.id}-1-test_resume.pdf"

        # Act
        response = self.client.post(
            "/resume/publish-to-review/",
            {"key": file_key},
            format="json",
        )

        # Assert
        self.assertResponse(response, 200)
        self.assertEqual(response.data["success"], True)
        mock_publish.assert_called_once_with(file_key)

    @override_settings(DJANGO_DEBUG=True)
    def test_publish_to_review_missing_key(self):
        # Act
        response = self.client.post(
            "/resume/publish-to-review/",
            {},
            format="json",
        )

        # Assert
        self.assertResponse(response, 400)
        self.assertEqual(response.data["error"], "File key not provided.")

    @override_settings(DJANGO_DEBUG=True)
    def test_publish_to_review_invalid_key_wrong_user(self):
        # Arrange
        other_user_id = 999
        file_key = f"{other_user_id}-1-test_resume.pdf"

        # Act
        response = self.client.post(
            "/resume/publish-to-review/",
            {"key": file_key},
            format="json",
        )

        # Assert
        self.assertResponse(response, 400)
        self.assertEqual(response.data["error"], "Invalid file key.")

    @override_settings(DJANGO_DEBUG=True)
    @patch("resume_review.views.dev_publish_to_review_resume")
    def test_publish_to_review_valid_key_format(self, mock_publish):
        # Arrange
        file_key = f"{self.user.id}-123-my_resume.pdf"

        # Act
        response = self.client.post(
            "/resume/publish-to-review/",
            {"key": file_key},
            format="json",
        )

        # Assert
        self.assertResponse(response, 200)
        mock_publish.assert_called_once_with(file_key)
