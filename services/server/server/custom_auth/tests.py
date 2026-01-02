import json
import time
from unittest.mock import MagicMock, patch

import jwt
from django.contrib.auth.models import Group
from django.contrib.auth.tokens import default_token_generator
from django.test import TestCase
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from members.models import User
from rest_framework.test import APIClient, APITestCase
from rest_framework_api_key.models import APIKey
from server.settings import JWT_SECRET

from .permissions import IsAdmin, IsVerified
from .serializers import UserSerializer
from .views import check_existing_user, create_password_reset_creds, validate_user_data


class UserSerializerTests(TestCase):
    """Test UserSerializer"""

    def test_user_serializer_create_with_valid_data(self):
        # Arrange
        data = {"username": "testuser", "password": "testpass123"}

        # Act
        serializer = UserSerializer(data=data)

        # Assert
        self.assertTrue(serializer.is_valid())
        user = serializer.save()
        self.assertEqual(user.username, "testuser")
        self.assertTrue(user.check_password("testpass123"))

    def test_user_serializer_password_write_only(self):
        # Arrange
        user = User.objects.create_user(username="testuser", password="testpass123")

        # Act
        serializer = UserSerializer(user)

        # Assert
        self.assertNotIn("password", serializer.data)

    def test_user_serializer_missing_password(self):
        # Arrange
        data = {"username": "testuser"}

        # Act
        serializer = UserSerializer(data=data)

        # Assert
        self.assertFalse(serializer.is_valid())
        self.assertIn("password", serializer.errors)


class IsVerifiedPermissionTests(TestCase):
    """Test IsVerified permission class"""

    def setUp(self):
        self.permission = IsVerified()
        self.user = User.objects.create_user(
            username="testuser",
            password="testpass123",
            discord_username="testdiscord",
            email="test@example.com",
        )
        self.verified_group = Group.objects.create(name="is_verified")

    def test_is_verified_permission_with_verified_user(self):
        # Arrange
        self.user.groups.add(self.verified_group)
        request = MagicMock()
        request.user = self.user

        # Act
        result = self.permission.has_permission(request, None)

        # Assert
        self.assertTrue(result)

    def test_is_verified_permission_with_unverified_user(self):
        # Arrange
        request = MagicMock()
        request.user = self.user

        # Act
        result = self.permission.has_permission(request, None)

        # Assert
        self.assertFalse(result)

    def test_is_verified_permission_with_unauthenticated_user(self):
        # Arrange
        request = MagicMock()
        request.user = MagicMock()
        request.user.is_authenticated = False

        # Act
        result = self.permission.has_permission(request, None)

        # Assert
        self.assertFalse(result)


class IsAdminPermissionTests(TestCase):
    """Test IsAdmin permission class"""

    def setUp(self):
        self.permission = IsAdmin()
        self.user = User.objects.create_user(
            username="testuser",
            password="testpass123",
            discord_username="testdiscord",
            email="test@example.com",
        )
        self.admin_group = Group.objects.create(name="is_admin")

    def test_is_admin_permission_with_admin_user(self):
        # Arrange
        self.user.groups.add(self.admin_group)
        request = MagicMock()
        request.user = self.user

        # Act
        result = self.permission.has_permission(request, None)

        # Assert
        self.assertTrue(result)

    def test_is_admin_permission_with_non_admin_user(self):
        # Arrange
        request = MagicMock()
        request.user = self.user

        # Act
        result = self.permission.has_permission(request, None)

        # Assert
        self.assertFalse(result)

    def test_is_admin_permission_with_unauthenticated_user(self):
        # Arrange
        request = MagicMock()
        request.user = MagicMock()
        request.user.is_authenticated = False

        # Act
        result = self.permission.has_permission(request, None)

        # Assert
        self.assertFalse(result)


class ValidateUserDataTests(TestCase):
    """Test validate_user_data helper function"""

    def test_validate_user_data_with_all_fields(self):
        # Arrange
        data = {
            "username": "testuser",
            "email": "test@example.com",
            "first_name": "Test",
            "last_name": "User",
            "discord_username": "testdiscord",
            "password": "testpass123",
        }

        # Act
        field_values, error = validate_user_data(data)

        # Assert
        self.assertIsNone(error)
        self.assertIsNotNone(field_values)
        self.assertEqual(field_values["username"], "testuser")
        self.assertEqual(field_values["email"], "test@example.com")

    def test_validate_user_data_without_password(self):
        # Arrange
        data = {
            "username": "testuser",
            "email": "test@example.com",
            "first_name": "Test",
            "last_name": "User",
            "discord_username": "testdiscord",
        }

        # Act
        field_values, error = validate_user_data(data, include_password=False)

        # Assert
        self.assertIsNone(error)
        self.assertIsNotNone(field_values)
        self.assertNotIn("password", field_values)

    def test_validate_user_data_missing_required_fields(self):
        # Arrange
        data = {"username": "testuser"}

        # Act
        field_values, error = validate_user_data(data)

        # Assert
        self.assertIsNone(field_values)
        self.assertIsNotNone(error)
        self.assertIn("email", error)

    def test_validate_user_data_strips_whitespace(self):
        # Arrange
        data = {
            "username": "  testuser  ",
            "email": "  test@example.com  ",
            "first_name": "  Test  ",
            "last_name": "  User  ",
            "discord_username": "  testdiscord  ",
            "password": "  testpass123  ",
        }

        # Act
        field_values, error = validate_user_data(data)

        # Assert
        self.assertIsNone(error)
        self.assertEqual(field_values["username"], "testuser")
        self.assertEqual(field_values["email"], "test@example.com")


class CheckExistingUserTests(TestCase):
    """Test check_existing_user helper function"""

    def setUp(self):
        self.existing_user = User.objects.create_user(
            username="existinguser",
            email="existing@example.com",
            discord_username="existingdiscord",
            password="testpass123",
        )

    def test_check_existing_user_with_duplicate_username(self):
        # Arrange
        field_values = {
            "username": "ExistingUser",  # Case insensitive
            "email": "new@example.com",
            "discord_username": "newdiscord",
        }

        # Act
        error = check_existing_user(field_values)

        # Assert
        self.assertIsNotNone(error)
        self.assertIn("Username already exists", error)

    def test_check_existing_user_with_duplicate_email(self):
        # Arrange
        field_values = {
            "username": "newuser",
            "email": "EXISTING@example.com",  # Case insensitive
            "discord_username": "newdiscord",
        }

        # Act
        error = check_existing_user(field_values)

        # Assert
        self.assertIsNotNone(error)
        self.assertIn("Email", error)
        self.assertIn("already exists", error)

    def test_check_existing_user_with_duplicate_discord_username(self):
        # Arrange
        field_values = {
            "username": "newuser",
            "email": "new@example.com",
            "discord_username": "ExistingDiscord",  # Case insensitive
        }

        # Act
        error = check_existing_user(field_values)

        # Assert
        self.assertIsNotNone(error)
        self.assertIn("Discord username", error)
        self.assertIn("already exists", error)

    def test_check_existing_user_with_unique_data(self):
        # Arrange
        field_values = {
            "username": "newuser",
            "email": "new@example.com",
            "discord_username": "newdiscord",
        }

        # Act
        error = check_existing_user(field_values)

        # Assert
        self.assertIsNone(error)


class CreatePasswordResetCredsTests(TestCase):
    """Test create_password_reset_creds helper function"""

    def test_create_password_reset_creds_generates_valid_token(self):
        # Arrange
        user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            discord_username="testdiscord",
            password="testpass123",
        )

        # Act
        uid, token = create_password_reset_creds(user)

        # Assert
        self.assertIsNotNone(uid)
        self.assertIsNotNone(token)
        self.assertTrue(default_token_generator.check_token(user, token))


class GetCSRFViewTests(APITestCase):
    """Test get_csrf view"""

    def test_get_csrf_returns_token(self):
        # Act
        response = self.client.get("/auth/csrf/")

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertIn("X-CSRFToken", response)
        self.assertIn("detail", response.json())


class LoginViewTests(APITestCase):
    """Test login_view"""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            discord_username="testdiscord",
            password="testpass123",
        )

    def test_login_with_valid_credentials(self):
        # Arrange
        data = {"username": "testuser", "password": "testpass123"}

        # Act
        response = self.client.post(
            "/auth/login/", json.dumps(data), content_type="application/json"
        )

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertIn("Successfully logged in", response.json()["detail"])

    def test_login_with_invalid_password(self):
        # Arrange
        data = {"username": "testuser", "password": "wrongpassword"}

        # Act
        response = self.client.post(
            "/auth/login/", json.dumps(data), content_type="application/json"
        )

        # Assert
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid credentials", response.json()["detail"])

    def test_login_with_missing_username(self):
        # Arrange
        data = {"password": "testpass123"}

        # Act
        response = self.client.post(
            "/auth/login/", json.dumps(data), content_type="application/json"
        )

        # Assert
        self.assertEqual(response.status_code, 400)

    def test_login_with_missing_password(self):
        # Arrange
        data = {"username": "testuser"}

        # Act
        response = self.client.post(
            "/auth/login/", json.dumps(data), content_type="application/json"
        )

        # Assert
        self.assertEqual(response.status_code, 400)

    def test_login_case_insensitive_username(self):
        # Arrange
        data = {"username": "TESTUSER", "password": "testpass123"}

        # Act
        response = self.client.post(
            "/auth/login/", json.dumps(data), content_type="application/json"
        )

        # Assert
        self.assertEqual(response.status_code, 200)


class RegisterViewTests(APITestCase):
    """Test register_view"""

    def test_register_with_valid_data(self):
        # Arrange
        data = {
            "username": "newuser",
            "email": "new@example.com",
            "first_name": "New",
            "last_name": "User",
            "discord_username": "newdiscord",
            "password": "newpass123",
        }

        # Act
        response = self.client.post(
            "/auth/register/", json.dumps(data), content_type="application/json"
        )

        # Assert
        self.assertEqual(response.status_code, 201)
        self.assertIn("Successfully registered", response.json()["detail"])
        self.assertIn("id", response.json())
        self.assertTrue(User.objects.filter(username="newuser").exists())

    def test_register_with_duplicate_username(self):
        # Arrange
        User.objects.create_user(
            username="existinguser",
            email="existing@example.com",
            discord_username="existingdiscord",
            password="testpass123",
        )
        data = {
            "username": "existinguser",
            "email": "new@example.com",
            "first_name": "New",
            "last_name": "User",
            "discord_username": "newdiscord",
            "password": "newpass123",
        }

        # Act
        response = self.client.post(
            "/auth/register/", json.dumps(data), content_type="application/json"
        )

        # Assert
        self.assertEqual(response.status_code, 400)
        self.assertIn("Username already exists", response.json()["detail"])

    def test_register_with_missing_fields(self):
        # Arrange
        data = {"username": "newuser", "password": "newpass123"}

        # Act
        response = self.client.post(
            "/auth/register/", json.dumps(data), content_type="application/json"
        )

        # Assert
        self.assertEqual(response.status_code, 400)


class LogoutViewTests(APITestCase):
    """Test logout_view"""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            discord_username="testdiscord",
            password="testpass123",
        )

    def test_logout_authenticated_user(self):
        # Arrange
        self.client.force_authenticate(user=self.user)

        # Act
        response = self.client.get("/auth/logout/")

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertIn("Successfully logged out", response.json()["detail"])

    def test_logout_unauthenticated_user(self):
        # Act
        response = self.client.get("/auth/logout/")

        # Assert
        self.assertEqual(response.status_code, 400)
        self.assertIn("not logged in", response.json()["detail"])


class SessionViewTests(APITestCase):
    """Test SessionView"""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            discord_username="testdiscord",
            password="testpass123",
        )

    def test_session_view_authenticated(self):
        # Arrange
        self.client.force_authenticate(user=self.user)

        # Act
        response = self.client.get("/auth/session/")

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["isAuthenticated"])

    def test_session_view_unauthenticated(self):
        # Act
        response = self.client.get("/auth/session/")

        # Assert
        self.assertEqual(response.status_code, 401)


class WhoAmIViewTests(APITestCase):
    """Test WhoAmIView"""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            discord_username="testdiscord",
            password="testpass123",
        )

    def test_whoami_authenticated(self):
        # Arrange
        self.client.force_authenticate(user=self.user)

        # Act
        response = self.client.get("/auth/whoami/")

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["username"], "testuser")

    def test_whoami_unauthenticated(self):
        # Act
        response = self.client.get("/auth/whoami/")

        # Assert
        self.assertEqual(response.status_code, 401)


class PasswordResetConfirmViewTests(APITestCase):
    """Test password_reset_confirm view"""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            discord_username="testdiscord",
            password="oldpass123",
        )

    def test_password_reset_confirm_with_valid_token(self):
        # Arrange
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        data = {"new_password": "newpass123"}

        # Act
        response = self.client.post(
            f"/auth/password-reset-confirm/{uid}/{token}/",
            json.dumps(data),
            content_type="application/json",
        )

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertIn("successfully", response.json()["detail"])
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("newpass123"))

    def test_password_reset_confirm_with_invalid_token(self):
        # Arrange
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = "invalid-token"
        data = {"new_password": "newpass123"}

        # Act
        response = self.client.post(
            f"/auth/password-reset-confirm/{uid}/{token}/",
            json.dumps(data),
            content_type="application/json",
        )

        # Assert
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid token", response.json()["detail"])

    def test_password_reset_confirm_with_invalid_uid(self):
        # Arrange
        uid = "invalid-uid"
        token = default_token_generator.make_token(self.user)
        data = {"new_password": "newpass123"}

        # Act
        response = self.client.post(
            f"/auth/password-reset-confirm/{uid}/{token}/",
            json.dumps(data),
            content_type="application/json",
        )

        # Assert
        self.assertEqual(response.status_code, 400)


class CreateTokenViewTests(APITestCase):
    """Test CreateTokenView"""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            discord_username="testdiscord",
            password="testpass123",
        )
        self.verified_group = Group.objects.create(name="is_verified")
        self.user.groups.add(self.verified_group)

    @patch("custom_auth.views.IsApiKey")
    def test_create_token_authenticated_user(self, mock_is_api_key):
        # Arrange
        mock_is_api_key.return_value.has_permission.return_value = False
        self.client.force_authenticate(user=self.user)

        # Act
        response = self.client.get("/auth/jwt/")

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertIn("token", response.json())

        # Verify token content
        token = response.json()["token"]
        decoded = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        self.assertEqual(decoded["user_id"], self.user.id)
        self.assertEqual(decoded["username"], "testuser")
        self.assertIn("is_authenticated", decoded["groups"])
        self.assertIn("is_verified", decoded["groups"])

    def test_create_token_unauthenticated_user(self):
        # Act
        response = self.client.get("/auth/jwt/")

        # Assert
        self.assertEqual(response.status_code, 401)


class RegisterWithApiKeyViewTests(APITestCase):
    """Test RegisterWithApiKeyView"""

    def setUp(self):
        self.api_key, self.key = APIKey.objects.create_key(name="test-api-key")
        self.client.credentials(HTTP_AUTHORIZATION=f"Api-Key {self.key}")

    def test_register_with_api_key_valid_data(self):
        # Arrange
        data = {
            "username": "newuser",
            "email": "new@example.com",
            "first_name": "New",
            "last_name": "User",
            "discord_username": "newdiscord",
        }

        # Act
        response = self.client.post(
            "/auth/register/ssflow/", json.dumps(data), content_type="application/json"
        )

        # Assert
        self.assertEqual(response.status_code, 201)
        self.assertIn("Successfully registered", response.json()["detail"])
        self.assertIn("id", response.json())
        self.assertIn("reset_password_url", response.json())
        self.assertTrue(User.objects.filter(username="newuser").exists())

    def test_register_with_api_key_duplicate_username(self):
        # Arrange
        User.objects.create_user(
            username="existinguser",
            email="existing@example.com",
            discord_username="existingdiscord",
            password="testpass123",
        )
        data = {
            "username": "existinguser",
            "email": "new@example.com",
            "first_name": "New",
            "last_name": "User",
            "discord_username": "newdiscord",
        }

        # Act
        response = self.client.post(
            "/auth/register/ssflow/", json.dumps(data), content_type="application/json"
        )

        # Assert
        self.assertEqual(response.status_code, 400)
        self.assertIn("Username already exists", response.json()["detail"])

    def test_register_with_api_key_missing_fields(self):
        # Arrange
        data = {"username": "newuser"}

        # Act
        response = self.client.post(
            "/auth/register/ssflow/", json.dumps(data), content_type="application/json"
        )

        # Assert
        self.assertEqual(response.status_code, 400)

    def test_register_with_api_key_without_api_key(self):
        # Arrange
        self.client.credentials()  # Remove API key
        data = {
            "username": "newuser",
            "email": "new@example.com",
            "first_name": "New",
            "last_name": "User",
            "discord_username": "newdiscord",
        }

        # Act
        response = self.client.post(
            "/auth/register/ssflow/", json.dumps(data), content_type="application/json"
        )

        # Assert
        self.assertEqual(response.status_code, 403)


class CreateUserViewTests(APITestCase):
    """Test CreateUserView"""

    def test_create_user_with_valid_data(self):
        # Arrange
        data = {"username": "newuser", "password": "newpass123"}

        # Act
        response = self.client.post(
            "/auth/register/", json.dumps(data), content_type="application/json"
        )

        # Assert - This should fail because we need all required fields
        self.assertEqual(response.status_code, 400)
