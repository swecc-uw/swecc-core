import json
import time
from io import BytesIO
from unittest.mock import MagicMock, Mock, patch

import jwt
from custom_auth.permissions import IsAdmin, IsVerified
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from rest_framework_api_key.models import APIKey
from server.settings import JWT_SECRET

from .models import User, validate_social_field
from .notification import verify_school_email_html
from .permissions import IsApiKey
from .serializers import GroupSerializer, UsernameSerializer, UserSerializer


class ValidateSocialFieldTests(TestCase):
    """Test validate_social_field function"""

    def test_validate_social_field_with_valid_data(self):
        # Arrange
        value = {"username": "testuser", "isPrivate": False}

        # Act & Assert - should not raise
        validate_social_field(value)

    def test_validate_social_field_with_none(self):
        # Act & Assert - should not raise
        validate_social_field(None)

    def test_validate_social_field_with_invalid_type(self):
        # Arrange
        value = "not a dict"

        # Act & Assert
        with self.assertRaises(ValidationError) as context:
            validate_social_field(value)
        self.assertIn("must be a dictionary", str(context.exception))

    def test_validate_social_field_with_missing_keys(self):
        # Arrange
        value = {"username": "testuser"}

        # Act & Assert
        with self.assertRaises(ValidationError) as context:
            validate_social_field(value)
        self.assertIn("must contain exactly", str(context.exception))

    def test_validate_social_field_with_extra_keys(self):
        # Arrange
        value = {"username": "testuser", "isPrivate": False, "extra": "key"}

        # Act & Assert
        with self.assertRaises(ValidationError) as context:
            validate_social_field(value)
        self.assertIn("must contain exactly", str(context.exception))

    def test_validate_social_field_with_invalid_username_type(self):
        # Arrange
        value = {"username": 123, "isPrivate": False}

        # Act & Assert
        with self.assertRaises(ValidationError) as context:
            validate_social_field(value)
        self.assertIn("username", str(context.exception))
        self.assertIn("must be a string", str(context.exception))

    def test_validate_social_field_with_invalid_isprivate_type(self):
        # Arrange
        value = {"username": "testuser", "isPrivate": "not a bool"}

        # Act & Assert
        with self.assertRaises(ValidationError) as context:
            validate_social_field(value)
        self.assertIn("isPrivate", str(context.exception))
        self.assertIn("must be a boolean", str(context.exception))


class UserModelTests(TestCase):
    """Test User model"""

    def test_user_creation_with_required_fields(self):
        # Arrange & Act
        user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            discord_username="testdiscord",
            password="testpass123",
        )

        # Assert
        self.assertEqual(user.username, "testuser")
        self.assertEqual(user.email, "test@example.com")
        self.assertEqual(user.discord_username, "testdiscord")
        self.assertTrue(user.check_password("testpass123"))

    def test_user_creation_with_optional_fields(self):
        # Arrange & Act
        user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            discord_username="testdiscord",
            password="testpass123",
            first_name="Test",
            last_name="User",
            major="Computer Science",
            bio="Test bio",
            discord_id=123456789,
        )

        # Assert
        self.assertEqual(user.first_name, "Test")
        self.assertEqual(user.last_name, "User")
        self.assertEqual(user.major, "Computer Science")
        self.assertEqual(user.bio, "Test bio")
        self.assertEqual(user.discord_id, 123456789)

    def test_user_with_valid_social_fields(self):
        # Arrange & Act
        user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            discord_username="testdiscord",
            password="testpass123",
            linkedin={"username": "testlinkedin", "isPrivate": False},
            github={"username": "testgithub", "isPrivate": True},
            leetcode={"username": "testleetcode", "isPrivate": False},
        )

        # Assert
        self.assertEqual(user.linkedin["username"], "testlinkedin")
        self.assertEqual(user.github["isPrivate"], True)
        self.assertEqual(user.leetcode["username"], "testleetcode")

    def test_user_case_insensitive_username_lookup(self):
        # Arrange
        User.objects.create_user(
            username="TestUser",
            email="test@example.com",
            discord_username="testdiscord",
            password="testpass123",
        )

        # Act
        user = User.objects.get_by_natural_key("testuser")

        # Assert
        self.assertEqual(user.username, "TestUser")

    def test_user_school_email_unique_constraint(self):
        # Arrange
        User.objects.create_user(
            username="user1",
            email="user1@example.com",
            discord_username="discord1",
            password="testpass123",
            school_email="school@uw.edu",
        )

        # Act & Assert
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            User.objects.create_user(
                username="user2",
                email="user2@example.com",
                discord_username="discord2",
                password="testpass123",
                school_email="school@uw.edu",
            )


class UserSerializerTests(TestCase):
    """Test UserSerializer"""

    def setUp(self):
        self.verified_group = Group.objects.create(name="is_verified")

    def test_user_serializer_excludes_password(self):
        # Arrange
        user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            discord_username="testdiscord",
            password="testpass123",
        )

        # Act
        serializer = UserSerializer(user)

        # Assert
        self.assertNotIn("password", serializer.data)
        self.assertIn("username", serializer.data)
        self.assertIn("email", serializer.data)

    def test_user_serializer_includes_groups(self):
        # Arrange
        user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            discord_username="testdiscord",
            password="testpass123",
        )
        user.groups.add(self.verified_group)

        # Act
        serializer = UserSerializer(user)

        # Assert
        self.assertIn("groups", serializer.data)
        self.assertEqual(len(serializer.data["groups"]), 1)
        self.assertEqual(serializer.data["groups"][0]["name"], "is_verified")


class GroupSerializerTests(TestCase):
    """Test GroupSerializer"""

    def test_group_serializer_with_valid_data(self):
        # Arrange
        group = Group.objects.create(name="test_group")

        # Act
        serializer = GroupSerializer(group)

        # Assert
        self.assertEqual(serializer.data["name"], "test_group")


class UsernameSerializerTests(TestCase):
    """Test UsernameSerializer"""

    def test_username_serializer_only_includes_username(self):
        # Arrange
        user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            discord_username="testdiscord",
            password="testpass123",
        )

        # Act
        serializer = UsernameSerializer(user)

        # Assert
        self.assertEqual(list(serializer.data.keys()), ["username"])
        self.assertEqual(serializer.data["username"], "testuser")


class IsApiKeyPermissionTests(TestCase):
    """Test IsApiKey permission class"""

    def setUp(self):
        self.permission = IsApiKey()
        self.api_key, self.key = APIKey.objects.create_key(name="test-api-key")

    @patch("members.permissions.HasAPIKey")
    def test_is_api_key_permission_with_valid_key(self, mock_has_api_key):
        # Arrange
        mock_has_api_key.return_value.has_permission.return_value = True
        request = MagicMock()

        # Act
        result = self.permission.has_permission(request, None)

        # Assert
        self.assertTrue(result)

    @patch("members.permissions.HasAPIKey")
    def test_is_api_key_permission_with_invalid_key(self, mock_has_api_key):
        # Arrange
        mock_has_api_key.return_value.has_permission.return_value = False
        request = MagicMock()

        # Act & Assert
        from rest_framework.exceptions import PermissionDenied

        with self.assertRaises(PermissionDenied):
            self.permission.has_permission(request, None)


class NotificationTests(TestCase):
    """Test notification helper functions"""

    def test_verify_school_email_html_contains_token(self):
        # Arrange
        token = "test-token-123"

        # Act
        html = verify_school_email_html(token)

        # Assert
        self.assertIn(token, html)
        self.assertIn("Verify Your Email", html)
        self.assertIn("verify-school-email", html)


class AuthenticatedTestCase(TestCase):
    """Base test case that automatically mocks authentication"""

    def setUp(self):
        super().setUp()
        self.api_patcher = patch("members.permissions.IsApiKey.has_permission")
        self.admin_patcher = patch("custom_auth.permissions.IsAdmin.has_permission")
        self.verified_patcher = patch("custom_auth.permissions.IsVerified.has_permission")

        # Start the patchers
        self.mock_api_perm = self.api_patcher.start()
        self.mock_admin_perm = self.admin_patcher.start()
        self.mock_verified_perm = self.verified_patcher.start()

        # Set return values
        self.mock_api_perm.return_value = True
        self.mock_admin_perm.return_value = True
        self.mock_verified_perm.return_value = True

    def tearDown(self):
        super().tearDown()
        # Stop the patchers
        self.api_patcher.stop()
        self.admin_patcher.stop()
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


class MembersListViewTests(AuthenticatedTestCase):
    """Test MembersList view"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.user1 = User.objects.create_user(
            username="user1",
            email="user1@example.com",
            discord_username="discord1",
            password="testpass123",
        )
        self.user2 = User.objects.create_user(
            username="user2",
            email="user2@example.com",
            discord_username="discord2",
            password="testpass123",
        )

    def test_get_members_list(self):
        # Act
        response = self.client.get("/members/")

        # Assert
        self.assertResponse(response, 200)
        self.assertEqual(len(response.data), 2)


class MemberRetrieveUpdateDestroyViewTests(AuthenticatedTestCase):
    """Test MemberRetrieveUpdateDestroy view"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            discord_username="testdiscord",
            password="testpass123",
        )

    def test_get_member_by_id(self):
        # Act
        response = self.client.get(f"/members/{self.user.id}/")

        # Assert
        self.assertResponse(response, 200)
        self.assertEqual(response.data["username"], "testuser")

    def test_get_nonexistent_member(self):
        # Act
        response = self.client.get("/members/99999/")

        # Assert
        self.assertResponse(response, 404)


class AuthenticatedMemberProfileViewTests(APITestCase):
    """Test AuthenticatedMemberProfile view"""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            discord_username="testdiscord",
            password="testpass123",
        )

    def test_get_authenticated_member_profile(self):
        # Arrange
        self.client.force_authenticate(user=self.user)

        # Act
        response = self.client.get("/members/profile/")

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["username"], "testuser")

    def test_get_authenticated_member_profile_unauthenticated(self):
        # Act
        response = self.client.get("/members/profile/")

        # Assert
        self.assertEqual(response.status_code, 401)

    def test_update_authenticated_member_profile(self):
        # Arrange
        self.client.force_authenticate(user=self.user)
        data = {"bio": "Updated bio", "major": "Computer Science"}

        # Act
        response = self.client.put("/members/profile/", data, format="json")

        # Assert
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.bio, "Updated bio")
        self.assertEqual(self.user.major, "Computer Science")


class UpdateDiscordIDViewTests(AuthenticatedTestCase):
    """Test UpdateDiscordID view"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            discord_username="testdiscord",
            password="testpass123",
        )

    def test_update_discord_id_with_valid_data(self):
        # Arrange
        data = {
            "username": "testuser",
            "discord_username": "testdiscord",
            "discord_id": 123456789,
        }

        # Act
        response = self.client.put("/members/verify-discord/", data, format="json")

        # Assert
        self.assertResponse(response, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.discord_id, 123456789)
        self.assertTrue(self.user.groups.filter(name="is_verified").exists())

    def test_update_discord_id_with_mismatched_discord_username(self):
        # Arrange
        data = {
            "username": "testuser",
            "discord_username": "wrongdiscord",
            "discord_id": 123456789,
        }

        # Act
        response = self.client.put("/members/verify-discord/", data, format="json")

        # Assert
        self.assertResponse(response, 400)
        self.assertIn("Discord username does not match", response.data["detail"])

    def test_update_discord_id_with_missing_fields(self):
        # Arrange
        data = {"username": "testuser"}

        # Act
        response = self.client.put("/members/verify-discord/", data, format="json")

        # Assert
        self.assertResponse(response, 400)

    def test_update_discord_id_with_nonexistent_user(self):
        # Arrange
        data = {
            "username": "nonexistent",
            "discord_username": "testdiscord",
            "discord_id": 123456789,
        }

        # Act
        response = self.client.put("/members/verify-discord/", data, format="json")

        # Assert
        self.assertResponse(response, 404)


class PasswordResetRequestViewTests(AuthenticatedTestCase):
    """Test PasswordResetRequest view"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            discord_username="testdiscord",
            password="testpass123",
            discord_id=123456789,
        )

    def test_password_reset_request_with_valid_discord_id(self):
        # Arrange
        data = {"discord_id": 123456789}

        # Act
        response = self.client.post("/members/reset-password/", data, format="json")

        # Assert
        self.assertResponse(response, 200)
        self.assertIn("uid", response.data)
        self.assertIn("token", response.data)

    def test_password_reset_request_with_invalid_discord_id(self):
        # Arrange
        data = {"discord_id": 999999999}

        # Act
        response = self.client.post("/members/reset-password/", data, format="json")

        # Assert
        self.assertResponse(response, 404)


class AdminListViewTests(AuthenticatedTestCase):
    """Test AdminList view"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.admin_group = Group.objects.create(name="is_admin")
        self.admin_user = User.objects.create_user(
            username="admin",
            email="admin@example.com",
            discord_username="admindiscord",
            password="testpass123",
        )
        self.admin_user.groups.add(self.admin_group)
        self.regular_user = User.objects.create_user(
            username="regular",
            email="regular@example.com",
            discord_username="regulardiscord",
            password="testpass123",
        )

    def test_admin_list_returns_only_admins(self):
        # Act
        response = self.client.get("/members/admin/")

        # Assert
        self.assertResponse(response, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["username"], "admin")


class UpdateDiscordUsernameViewTests(APITestCase):
    """Test UpdateDiscordUsername view"""

    def setUp(self):
        self.verified_group = Group.objects.create(name="is_verified")
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            discord_username="olddiscord",
            password="testpass123",
        )

    @patch("custom_auth.permissions.IsVerified.has_permission")
    def test_update_discord_username_unverified_user(self, mock_verified):
        # Arrange
        mock_verified.return_value = False
        self.client.force_authenticate(user=self.user)
        data = {"new_discord_username": "newdiscord"}

        # Act
        response = self.client.post("/members/update-discord-username", data, format="json")

        # Assert
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.discord_username, "newdiscord")

    @patch("custom_auth.permissions.IsVerified.has_permission")
    def test_update_discord_username_verified_user_denied(self, mock_verified):
        # Arrange
        mock_verified.return_value = True
        self.user.groups.add(self.verified_group)
        self.client.force_authenticate(user=self.user)
        data = {"new_discord_username": "newdiscord"}

        # Act
        response = self.client.post("/members/update-discord-username", data, format="json")

        # Assert - Should be denied because user is verified
        self.assertEqual(response.status_code, 403)


class VerifySchoolEmailRequestViewTests(AuthenticatedTestCase):
    """Test VerifySchoolEmailRequest view"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            discord_username="testdiscord",
            password="testpass123",
            discord_id=123456789,
        )

    @patch("members.views.send_email")
    def test_verify_school_email_request_with_discord_id(self, mock_send_email):
        # Arrange
        data = {"discord_id": 123456789, "school_email": "test@uw.edu"}

        # Act
        response = self.client.post("/members/verify-school-email/", data, format="json")

        # Assert
        self.assertResponse(response, 200)
        self.assertIn("token", response.data)
        mock_send_email.assert_called_once()

    @patch("members.views.send_email")
    def test_verify_school_email_request_with_user_id(self, mock_send_email):
        # Arrange
        data = {"user_id": self.user.id, "school_email": "test@uw.edu"}

        # Act
        response = self.client.post("/members/verify-school-email/", data, format="json")

        # Assert
        self.assertResponse(response, 200)
        self.assertIn("token", response.data)
        mock_send_email.assert_called_once()

    def test_verify_school_email_request_missing_identifiers(self):
        # Arrange
        data = {"school_email": "test@uw.edu"}

        # Act
        response = self.client.post("/members/verify-school-email/", data, format="json")

        # Assert
        self.assertResponse(response, 400)
        self.assertIn("Discord ID or user ID is required", response.data["detail"])

    def test_verify_school_email_request_missing_email(self):
        # Arrange
        data = {"discord_id": 123456789}

        # Act
        response = self.client.post("/members/verify-school-email/", data, format="json")

        # Assert
        self.assertResponse(response, 400)
        self.assertIn("School email is required", response.data["detail"])

    @patch("members.views.send_email")
    def test_verify_school_email_request_duplicate_email(self, mock_send_email):
        # Arrange
        User.objects.create_user(
            username="otheruser",
            email="other@example.com",
            discord_username="otherdiscord",
            password="testpass123",
            school_email="test@uw.edu",
        )
        data = {"discord_id": 123456789, "school_email": "test@uw.edu"}

        # Act
        response = self.client.post("/members/verify-school-email/", data, format="json")

        # Assert
        self.assertResponse(response, 400)
        self.assertIn("Email already in use", response.data["detail"])


class ConfirmVerifySchoolEmailViewTests(APITestCase):
    """Test ConfirmVerifySchoolEmail view"""

    def setUp(self):
        self.verified_group = Group.objects.create(name="is_verified")
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            discord_username="testdiscord",
            password="testpass123",
            discord_id=123456789,
        )
        self.user.groups.add(self.verified_group)

    @patch("members.views.publish_verified_email")
    def test_confirm_verify_school_email_with_valid_token(self, mock_publish):
        # Arrange
        self.client.force_authenticate(user=self.user)
        payload = {
            "user_id": self.user.id,
            "username": self.user.username,
            "exp": int(time.time()) + 3600,
            "email": "test@uw.edu",
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")

        # Act
        response = self.client.post(f"/members/verify-school-email/{token}/")

        # Assert
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.school_email, "test@uw.edu")
        mock_publish.assert_called_once_with(self.user.discord_id)

    def test_confirm_verify_school_email_with_expired_token(self):
        # Arrange
        self.client.force_authenticate(user=self.user)
        payload = {
            "user_id": self.user.id,
            "username": self.user.username,
            "exp": int(time.time()) - 3600,  # Expired
            "email": "test@uw.edu",
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")

        # Act
        response = self.client.post(f"/members/verify-school-email/{token}/")

        # Assert
        self.assertEqual(response.status_code, 400)
        self.assertIn("Token has expired", response.data["detail"])

    def test_confirm_verify_school_email_with_invalid_token(self):
        # Arrange
        self.client.force_authenticate(user=self.user)
        token = "invalid-token"

        # Act
        response = self.client.post(f"/members/verify-school-email/{token}/")

        # Assert
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid token", response.data["detail"])

    def test_confirm_verify_school_email_user_mismatch(self):
        # Arrange
        other_user = User.objects.create_user(
            username="otheruser",
            email="other@example.com",
            discord_username="otherdiscord",
            password="testpass123",
        )
        other_user.groups.add(self.verified_group)
        self.client.force_authenticate(user=self.user)
        payload = {
            "user_id": other_user.id,  # Different user
            "username": other_user.username,
            "exp": int(time.time()) + 3600,
            "email": "test@uw.edu",
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")

        # Act
        response = self.client.post(f"/members/verify-school-email/{token}/")

        # Assert
        self.assertEqual(response.status_code, 403)
        self.assertIn("User does not match token", response.data["detail"])

    @patch("members.views.publish_verified_email")
    def test_confirm_verify_school_email_duplicate_email(self, mock_publish):
        # Arrange
        User.objects.create_user(
            username="otheruser",
            email="other@example.com",
            discord_username="otherdiscord",
            password="testpass123",
            school_email="test@uw.edu",
        )
        self.client.force_authenticate(user=self.user)
        payload = {
            "user_id": self.user.id,
            "username": self.user.username,
            "exp": int(time.time()) + 3600,
            "email": "test@uw.edu",
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")

        # Act
        response = self.client.post(f"/members/verify-school-email/{token}/")

        # Assert
        self.assertEqual(response.status_code, 400)
        self.assertIn("Email already in use", response.data["detail"])


class ProfilePictureUploadViewTests(APITestCase):
    """Test ProfilePictureUploadView"""

    def setUp(self):
        self.verified_group = Group.objects.create(name="is_verified")
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            discord_username="testdiscord",
            password="testpass123",
        )
        self.user.groups.add(self.verified_group)

    def test_profile_picture_upload_no_file(self):
        # Arrange
        self.client.force_authenticate(user=self.user)

        # Act
        response = self.client.post("/members/profile/picture/upload/")

        # Assert
        self.assertEqual(response.status_code, 400)
        self.assertIn("No file was uploaded", response.json()["error"])

    @patch("members.views.create_client")
    def test_profile_picture_upload_invalid_file_type(self, mock_supabase):
        # Arrange
        self.client.force_authenticate(user=self.user)
        file = BytesIO(b"fake file content")
        file.name = "test.txt"
        file.content_type = "text/plain"

        # Act
        response = self.client.post(
            "/members/profile/picture/upload/", {"profile_picture": file}, format="multipart"
        )

        # Assert
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid file type", response.json()["error"])

    @patch("members.views.create_client")
    def test_profile_picture_upload_file_too_large(self, mock_supabase):
        # Arrange
        self.client.force_authenticate(user=self.user)
        # Create a file larger than 5MB
        large_file = BytesIO(b"x" * (6 * 1024 * 1024))
        large_file.name = "test.jpg"
        large_file.content_type = "image/jpeg"

        # Act
        response = self.client.post(
            "/members/profile/picture/upload/", {"profile_picture": large_file}, format="multipart"
        )

        # Assert
        self.assertEqual(response.status_code, 400)
        self.assertIn("File too large", response.json()["error"])

    @patch("members.views.create_client")
    def test_profile_picture_upload_success(self, mock_supabase):
        # Arrange
        self.client.force_authenticate(user=self.user)
        mock_storage = Mock()
        mock_supabase.return_value.storage.from_.return_value = mock_storage
        mock_storage.get_public_url.return_value = "https://example.com/profile.jpg"

        file = BytesIO(b"fake image content")
        file.name = "test.jpg"
        file.content_type = "image/jpeg"

        # Act
        response = self.client.post(
            "/members/profile/picture/upload/", {"profile_picture": file}, format="multipart"
        )

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertIn("url", response.json())
        self.user.refresh_from_db()
        self.assertEqual(self.user.profile_picture_url, "https://example.com/profile.jpg")
