from datetime import date
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import Group
from django.test import TestCase
from members.models import User
from rest_framework.test import APIClient

from .managers import DirectoryManager
from .serializers import AdminDirectoryMemberSerializer, RegularDirectoryMemberSerializer
from .views import simple_hash


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


class DirectorySerializerTests(TestCase):
    """Test directory serializers"""

    def setUp(self):
        self.user = User.objects.create(
            username="testuser",
            discord_username="test#1234",
            email="test@example.com",
            first_name="Test",
            last_name="User",
            major="Computer Science",
            linkedin={"username": "testuser", "isPrivate": False},
            github={"username": "testuser", "isPrivate": False},
            leetcode={"username": "testuser", "isPrivate": True},
        )

    def test_regular_serializer_fields(self):
        """Test RegularDirectoryMemberSerializer includes correct fields"""
        serializer = RegularDirectoryMemberSerializer(self.user)
        self.assertIn("id", serializer.data)
        self.assertIn("username", serializer.data)
        self.assertIn("email", serializer.data)
        self.assertIn("first_name", serializer.data)
        self.assertIn("last_name", serializer.data)
        self.assertIn("major", serializer.data)

    def test_regular_serializer_public_social_fields(self):
        """Test public social fields are included"""
        serializer = RegularDirectoryMemberSerializer(self.user)
        self.assertIn("linkedin", serializer.data)
        self.assertIn("github", serializer.data)
        self.assertEqual(serializer.data["linkedin"]["username"], "testuser")
        self.assertEqual(serializer.data["github"]["username"], "testuser")

    def test_regular_serializer_private_social_fields(self):
        """Test private social fields are excluded"""
        serializer = RegularDirectoryMemberSerializer(self.user)
        self.assertIsNone(serializer.data.get("leetcode"))

    def test_regular_serializer_removes_empty_fields(self):
        """Test empty fields are removed from serialization"""
        user = User.objects.create(
            username="emptyuser", discord_username="empty#1234", email="empty@example.com"
        )
        serializer = RegularDirectoryMemberSerializer(user)
        self.assertNotIn("major", serializer.data)
        self.assertNotIn("linkedin", serializer.data)

    def test_admin_serializer_includes_all_fields(self):
        """Test AdminDirectoryMemberSerializer includes all fields except password"""
        serializer = AdminDirectoryMemberSerializer(self.user)
        self.assertIn("id", serializer.data)
        self.assertIn("username", serializer.data)
        self.assertIn("email", serializer.data)
        self.assertNotIn("password", serializer.data)

    def test_social_field_with_none(self):
        """Test social field handling when None"""
        user = User.objects.create(
            username="nolinkedin",
            discord_username="nolinkedin#1234",
            email="nolinkedin@example.com",
            linkedin=None,
        )
        serializer = RegularDirectoryMemberSerializer(user)
        self.assertNotIn("linkedin", serializer.data)


class DirectoryManagerTests(TestCase):
    """Test DirectoryManager"""

    def setUp(self):
        self.user1 = User.objects.create(
            username="user1", discord_username="user1#1234", email="user1@example.com"
        )
        self.user2 = User.objects.create(
            username="user2", discord_username="user2#1234", email="user2@example.com"
        )

        # Create mock cache handler
        self.mock_cache = MagicMock()
        self.generate_key = lambda **kwargs: f"user:{kwargs.get('id', 'all')}"
        self.manager = DirectoryManager(self.mock_cache, self.generate_key)

    def test_get_member_from_cache(self):
        """Test getting member from cache"""
        cached_data = {"id": self.user1.id, "username": "user1"}
        self.mock_cache.get.return_value = cached_data

        result = self.manager.get(self.user1.id)
        self.assertEqual(result, cached_data)
        self.mock_cache.get.assert_called_once()
        self.mock_cache.set.assert_called_once()  # refresh_key

    def test_get_member_from_db(self):
        """Test getting member from database when not cached"""
        self.mock_cache.get.return_value = None

        result = self.manager.get(self.user1.id)
        self.assertIn("username", result)
        self.assertEqual(result["username"], "user1")
        self.mock_cache.set.assert_called_once()

    def test_get_all_from_cache(self):
        """Test getting all members from cache"""
        cached_data = [self.user1, self.user2]
        self.mock_cache.get.return_value = cached_data

        result = self.manager.get_all()
        self.assertEqual(result, cached_data)
        self.mock_cache.get.assert_called_once()

    def test_get_all_from_db(self):
        """Test getting all members from database when not cached"""
        self.mock_cache.get.return_value = None

        result = self.manager.get_all()
        self.assertEqual(len(result), 2)
        self.assertIn(self.user1, result)
        self.assertIn(self.user2, result)
        self.mock_cache.set.assert_called_once()

    def test_refresh_key(self):
        """Test refreshing cache key"""
        key = "test_key"
        value = {"test": "data"}
        self.manager.refresh_key(key, value)
        self.mock_cache.set.assert_called_once_with(key, value)


class SimpleHashTests(TestCase):
    """Test simple_hash function"""

    def test_simple_hash_consistency(self):
        """Test hash function produces consistent results"""
        input_str = "test_string"
        hash1 = simple_hash(input_str)
        hash2 = simple_hash(input_str)
        self.assertEqual(hash1, hash2)

    def test_simple_hash_different_inputs(self):
        """Test hash function produces different results for different inputs"""
        hash1 = simple_hash("string1")
        hash2 = simple_hash("string2")
        self.assertNotEqual(hash1, hash2)

    def test_simple_hash_returns_int(self):
        """Test hash function returns integer"""
        result = simple_hash("test")
        self.assertIsInstance(result, int)

    def test_simple_hash_empty_string(self):
        """Test hash function with empty string"""
        result = simple_hash("")
        self.assertIsInstance(result, int)


class MemberDirectorySearchViewTests(AuthenticatedTestCase):
    """Test MemberDirectorySearchView"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.verified_group = Group.objects.get_or_create(name="is_verified")[0]
        self.user = User.objects.create(
            username="testuser",
            discord_username="test#1234",
            email="test@example.com",
            first_name="Test",
            last_name="User",
        )
        self.user.groups.add(self.verified_group)

        # Create test users
        self.user1 = User.objects.create(
            username="alice",
            discord_username="alice#1234",
            email="alice@example.com",
            first_name="Alice",
            last_name="Smith",
        )
        self.user2 = User.objects.create(
            username="bob",
            discord_username="bob#1234",
            email="bob@example.com",
            first_name="Bob",
            last_name="Jones",
        )

    @patch("directory.views.DirectoryManager.get_all")
    def test_search_without_query(self, mock_get_all):
        """Test search without query parameter"""
        mock_get_all.return_value = [self.user1, self.user2]

        self.client.force_authenticate(user=self.user)
        response = self.client.get("/directory/search/")
        self.assertResponse(response, 200)
        self.assertIn("results", response.data)

    @patch("directory.views.DirectoryManager.get_all")
    def test_search_with_query(self, mock_get_all):
        """Test search with query parameter"""
        mock_get_all.return_value = [self.user1, self.user2]

        self.client.force_authenticate(user=self.user)
        response = self.client.get("/directory/search/?q=alice")
        self.assertResponse(response, 200)

    @patch("directory.views.DirectoryManager.get_all")
    def test_search_pagination(self, mock_get_all):
        """Test search with pagination"""
        users = [
            User.objects.create(
                username=f"user{i}",
                discord_username=f"user{i}#1234",
                email=f"user{i}@example.com",
            )
            for i in range(25)
        ]
        mock_get_all.return_value = users

        self.client.force_authenticate(user=self.user)
        response = self.client.get("/directory/search/?page=1")
        self.assertResponse(response, 200)
        self.assertIn("results", response.data)
        self.assertIn("count", response.data)

    @patch("directory.views.DirectoryManager.get_all")
    def test_search_multiple_terms(self, mock_get_all):
        """Test search with multiple terms"""
        mock_get_all.return_value = [self.user1, self.user2]

        self.client.force_authenticate(user=self.user)
        response = self.client.get("/directory/search/?q=alice bob")
        self.assertResponse(response, 200)


class MemberDirectoryViewTests(AuthenticatedTestCase):
    """Test MemberDirectoryView"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.verified_group = Group.objects.get_or_create(name="is_verified")[0]
        self.user = User.objects.create(
            username="testuser",
            discord_username="test#1234",
            email="test@example.com",
            first_name="Test",
            last_name="User",
        )
        self.user.groups.add(self.verified_group)

        self.target_user = User.objects.create(
            username="targetuser",
            discord_username="target#1234",
            email="target@example.com",
            first_name="Target",
            last_name="User",
        )

    @patch("directory.views.DirectoryManager.get")
    def test_get_member_by_id(self, mock_get):
        """Test getting member by ID"""
        mock_get.return_value = {"id": self.target_user.id, "username": "targetuser"}

        self.client.force_authenticate(user=self.user)
        response = self.client.get(f"/directory/{self.target_user.id}/")
        self.assertResponse(response, 200)
        self.assertEqual(response.data["username"], "targetuser")

    @patch("directory.views.DirectoryManager.get")
    def test_get_nonexistent_member(self, mock_get):
        """Test getting nonexistent member"""
        mock_get.side_effect = User.DoesNotExist()

        self.client.force_authenticate(user=self.user)
        response = self.client.get("/directory/99999/")
        self.assertResponse(response, 404)


class RecommendedMembersViewTests(AuthenticatedTestCase):
    """Test RecommendedMembersView"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.verified_group = Group.objects.get_or_create(name="is_verified")[0]
        self.user = User.objects.create(
            username="testuser",
            discord_username="test#1234",
            email="test@example.com",
            first_name="Test",
            last_name="User",
        )
        self.user.groups.add(self.verified_group)

        # Create test users
        self.users = [
            User.objects.create(
                username=f"user{i}",
                discord_username=f"user{i}#1234",
                email=f"user{i}@example.com",
            )
            for i in range(10)
        ]

    @patch("directory.views.DirectoryManager.get_all")
    def test_get_recommended_members(self, mock_get_all):
        """Test getting recommended members"""
        mock_get_all.return_value = [self.user] + self.users

        self.client.force_authenticate(user=self.user)
        response = self.client.get("/directory/recommended/")
        self.assertResponse(response, 200)
        self.assertLessEqual(len(response.data), 5)

    @patch("directory.views.DirectoryManager.get_all")
    def test_recommended_members_excludes_current_user(self, mock_get_all):
        """Test recommended members excludes current user"""
        mock_get_all.return_value = [self.user] + self.users

        self.client.force_authenticate(user=self.user)
        response = self.client.get("/directory/recommended/")
        self.assertResponse(response, 200)

        # Verify current user is not in recommendations
        usernames = [member["username"] for member in response.data]
        self.assertNotIn(self.user.username, usernames)

    @patch("directory.views.DirectoryManager.get_all")
    def test_recommended_members_consistency(self, mock_get_all):
        """Test recommended members are consistent for same day"""
        mock_get_all.return_value = [self.user] + self.users

        self.client.force_authenticate(user=self.user)
        response1 = self.client.get("/directory/recommended/")
        response2 = self.client.get("/directory/recommended/")

        self.assertResponse(response1, 200)
        self.assertResponse(response2, 200)

        # Same day should return same recommendations
        usernames1 = [member["username"] for member in response1.data]
        usernames2 = [member["username"] for member in response2.data]
        self.assertEqual(usernames1, usernames2)

    @patch("directory.views.DirectoryManager.get_all")
    def test_recommended_members_empty_list(self, mock_get_all):
        """Test recommended members with only current user"""
        mock_get_all.return_value = [self.user]

        self.client.force_authenticate(user=self.user)
        response = self.client.get("/directory/recommended/")
        self.assertResponse(response, 200)
        self.assertEqual(len(response.data), 0)

    @patch("directory.views.DirectoryManager.get_all")
    def test_recommended_members_error_handling(self, mock_get_all):
        """Test error handling in recommended members"""
        mock_get_all.side_effect = Exception("Test error")

        self.client.force_authenticate(user=self.user)
        response = self.client.get("/directory/recommended/")
        self.assertResponse(response, 500)
