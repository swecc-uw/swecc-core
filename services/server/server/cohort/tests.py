from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import Group
from django.test import TestCase
from django.utils import timezone
from engagement.models import CohortStats
from members.models import User
from rest_framework.test import APIClient

from .models import Cohort, CohortStatsData
from .serializers import (
    CohortHydratedPublicSerializer,
    CohortHydratedSerializer,
    CohortNoMembersSerializer,
    CohortSerializer,
)


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


class CohortModelTests(TestCase):
    """Test Cohort model"""

    def setUp(self):
        self.user = User.objects.create(
            username="testuser", discord_username="test#1234", email="test@example.com"
        )

    def test_cohort_creation(self):
        """Test creating a cohort"""
        cohort = Cohort.objects.create(name="Test Cohort", level="beginner")
        self.assertEqual(cohort.name, "Test Cohort")
        self.assertEqual(cohort.level, "beginner")
        self.assertTrue(cohort.is_active)
        self.assertIsNone(cohort.discord_channel_id)
        self.assertIsNone(cohort.discord_role_id)

    def test_cohort_str_representation(self):
        """Test cohort string representation"""
        cohort = Cohort.objects.create(name="Advanced Cohort", level="advanced")
        self.assertEqual(str(cohort), "Advanced Cohort (Advanced)")

    def test_cohort_level_choices(self):
        """Test cohort level choices"""
        for level, _ in Cohort.LEVEL_CHOICES:
            cohort = Cohort.objects.create(name=f"Cohort {level}", level=level)
            self.assertEqual(cohort.level, level)

    def test_cohort_unique_name(self):
        """Test cohort name uniqueness constraint"""
        from django.db import IntegrityError

        Cohort.objects.create(name="Unique Cohort", level="beginner")
        with self.assertRaises(IntegrityError):
            Cohort.objects.create(name="Unique Cohort", level="intermediate")

    def test_cohort_members_relationship(self):
        """Test many-to-many relationship with users"""
        cohort = Cohort.objects.create(name="Member Test Cohort", level="beginner")
        user1 = User.objects.create(
            username="user1", discord_username="user1#1234", email="user1@example.com"
        )
        user2 = User.objects.create(
            username="user2", discord_username="user2#1234", email="user2@example.com"
        )

        cohort.members.add(user1, user2)
        self.assertEqual(cohort.members.count(), 2)
        self.assertIn(user1, cohort.members.all())
        self.assertIn(user2, cohort.members.all())

    def test_cohort_ordering(self):
        """Test cohort ordering by name"""
        Cohort.objects.create(name="Zebra Cohort", level="beginner")
        Cohort.objects.create(name="Alpha Cohort", level="intermediate")
        Cohort.objects.create(name="Beta Cohort", level="advanced")

        cohorts = list(Cohort.objects.all())
        self.assertEqual(cohorts[0].name, "Alpha Cohort")
        self.assertEqual(cohorts[1].name, "Beta Cohort")
        self.assertEqual(cohorts[2].name, "Zebra Cohort")

    def test_cohort_discord_fields(self):
        """Test discord channel and role ID fields"""
        cohort = Cohort.objects.create(
            name="Discord Cohort",
            level="beginner",
            discord_channel_id=123456789,
            discord_role_id=987654321,
        )
        self.assertEqual(cohort.discord_channel_id, 123456789)
        self.assertEqual(cohort.discord_role_id, 987654321)


class CohortStatsDataTests(TestCase):
    """Test CohortStatsData dataclass"""

    def test_cohort_stats_data_creation(self):
        """Test creating CohortStatsData"""
        stats = CohortStatsData(
            applications=10,
            online_assessments=5,
            interviews=3,
            offers=1,
            daily_checks=20,
            streak=7,
        )
        self.assertEqual(stats.applications, 10)
        self.assertEqual(stats.online_assessments, 5)
        self.assertEqual(stats.interviews, 3)
        self.assertEqual(stats.offers, 1)
        self.assertEqual(stats.daily_checks, 20)
        self.assertEqual(stats.streak, 7)

    def test_cohort_stats_data_defaults(self):
        """Test CohortStatsData default values"""
        stats = CohortStatsData()
        self.assertEqual(stats.applications, 0)
        self.assertEqual(stats.online_assessments, 0)
        self.assertEqual(stats.interviews, 0)
        self.assertEqual(stats.offers, 0)
        self.assertEqual(stats.daily_checks, 0)
        self.assertEqual(stats.streak, 0)

    def test_cohort_stats_data_to_dict(self):
        """Test converting CohortStatsData to dict"""
        stats = CohortStatsData(
            applications=10,
            online_assessments=5,
            interviews=3,
            offers=1,
            daily_checks=20,
            streak=7,
        )
        result = stats.to_dict()
        expected = {
            "applications": 10,
            "onlineAssessments": 5,
            "interviews": 3,
            "offers": 1,
            "dailyChecks": 20,
            "streak": 7,
        }
        self.assertEqual(result, expected)

    def test_cohort_stats_data_from_db_values(self):
        """Test creating CohortStatsData from database values"""
        db_values = {
            "applications_sum": 10,
            "online_assessments_sum": 5,
            "interviews_sum": 3,
            "offers_sum": 1,
            "daily_checks_sum": 20,
            "streak_max": 7,
        }
        stats = CohortStatsData.from_db_values(db_values)
        self.assertEqual(stats.applications, 10)
        self.assertEqual(stats.online_assessments, 5)
        self.assertEqual(stats.interviews, 3)
        self.assertEqual(stats.offers, 1)
        self.assertEqual(stats.daily_checks, 20)
        self.assertEqual(stats.streak, 7)

    def test_cohort_stats_data_from_db_values_with_none(self):
        """Test creating CohortStatsData from database values with None"""
        db_values = {
            "applications_sum": None,
            "online_assessments_sum": None,
            "interviews_sum": None,
            "offers_sum": None,
            "daily_checks_sum": None,
            "streak_max": None,
        }
        stats = CohortStatsData.from_db_values(db_values)
        self.assertEqual(stats.applications, 0)
        self.assertEqual(stats.online_assessments, 0)
        self.assertEqual(stats.interviews, 0)
        self.assertEqual(stats.offers, 0)
        self.assertEqual(stats.daily_checks, 0)
        self.assertEqual(stats.streak, 0)

    def test_cohort_stats_data_from_db_values_missing_keys(self):
        """Test creating CohortStatsData from database values with missing keys"""
        db_values = {}
        stats = CohortStatsData.from_db_values(db_values)
        self.assertEqual(stats.applications, 0)
        self.assertEqual(stats.online_assessments, 0)
        self.assertEqual(stats.interviews, 0)
        self.assertEqual(stats.offers, 0)
        self.assertEqual(stats.daily_checks, 0)
        self.assertEqual(stats.streak, 0)


class CohortSerializerTests(TestCase):
    """Test Cohort serializers"""

    def setUp(self):
        self.user1 = User.objects.create(
            username="user1", discord_username="user1#1234", email="user1@example.com"
        )
        self.user2 = User.objects.create(
            username="user2", discord_username="user2#1234", email="user2@example.com"
        )
        self.cohort = Cohort.objects.create(name="Test Cohort", level="intermediate")
        self.cohort.members.add(self.user1, self.user2)

    def test_cohort_serializer_fields(self):
        """Test CohortSerializer includes correct fields"""
        serializer = CohortSerializer(self.cohort)
        self.assertIn("id", serializer.data)
        self.assertIn("name", serializer.data)
        self.assertIn("members", serializer.data)
        self.assertIn("level", serializer.data)

    def test_cohort_serializer_validation(self):
        """Test CohortSerializer validation"""
        data = {"name": "New Cohort", "level": "beginner", "members": []}
        serializer = CohortSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_cohort_no_members_serializer(self):
        """Test CohortNoMembersSerializer excludes members"""
        serializer = CohortNoMembersSerializer(self.cohort)
        self.assertIn("id", serializer.data)
        self.assertIn("name", serializer.data)
        self.assertIn("level", serializer.data)
        self.assertNotIn("members", serializer.data)

    def test_cohort_hydrated_serializer(self):
        """Test CohortHydratedSerializer includes hydrated members"""
        serializer = CohortHydratedSerializer(self.cohort)
        self.assertIn("members", serializer.data)
        self.assertEqual(len(serializer.data["members"]), 2)
        self.assertIn("username", serializer.data["members"][0])

    def test_cohort_hydrated_public_serializer(self):
        """Test CohortHydratedPublicSerializer excludes level"""
        serializer = CohortHydratedPublicSerializer(self.cohort)
        self.assertIn("id", serializer.data)
        self.assertIn("name", serializer.data)
        self.assertIn("members", serializer.data)
        self.assertNotIn("level", serializer.data)


class CohortListCreateViewTests(AuthenticatedTestCase):
    """Test CohortListCreateView"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.admin_group = Group.objects.get_or_create(name="is_admin")[0]
        self.user = User.objects.create(
            username="testuser", discord_username="test#1234", email="test@example.com"
        )
        self.admin_user = User.objects.create(
            username="adminuser", discord_username="admin#1234", email="admin@example.com"
        )
        self.admin_user.groups.add(self.admin_group)

    def test_list_cohorts_as_admin(self):
        """Test listing cohorts as admin"""
        Cohort.objects.create(name="Cohort 1", level="beginner")
        Cohort.objects.create(name="Cohort 2", level="intermediate")

        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get("/cohort/")
        self.assertResponse(response, 200)
        self.assertEqual(len(response.data), 2)

    def test_list_cohorts_as_regular_user(self):
        """Test listing cohorts as regular user"""
        Cohort.objects.create(name="Cohort 1", level="beginner")

        self.client.force_authenticate(user=self.user)
        response = self.client.get("/cohort/")
        self.assertResponse(response, 200)

    def test_create_cohort(self):
        """Test creating a cohort"""
        self.client.force_authenticate(user=self.admin_user)
        data = {"name": "New Cohort", "level": "advanced", "members": []}
        response = self.client.post("/cohort/", data)
        self.assertResponse(response, 201)
        self.assertTrue(Cohort.objects.filter(name="New Cohort").exists())

    def test_create_cohort_with_members(self):
        """Test creating a cohort with members"""
        self.client.force_authenticate(user=self.admin_user)
        data = {"name": "Member Cohort", "level": "beginner", "members": [self.user.id]}
        response = self.client.post("/cohort/", data)
        self.assertResponse(response, 201)

        cohort = Cohort.objects.get(name="Member Cohort")
        self.assertEqual(cohort.members.count(), 1)
        self.assertTrue(CohortStats.objects.filter(cohort=cohort, member=self.user).exists())

    def test_create_duplicate_cohort(self):
        """Test creating a cohort with duplicate name"""
        Cohort.objects.create(name="Duplicate Cohort", level="beginner")
        self.client.force_authenticate(user=self.admin_user)
        data = {"name": "Duplicate Cohort", "level": "intermediate", "members": []}
        response = self.client.post("/cohort/", data)
        self.assertResponse(response, 400)


class CohortRetrieveUpdateDestroyViewTests(AuthenticatedTestCase):
    """Test CohortRetrieveUpdateDestroyView"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.admin_group = Group.objects.get_or_create(name="is_admin")[0]
        self.admin_user = User.objects.create(
            username="adminuser", discord_username="admin#1234", email="admin@example.com"
        )
        self.admin_user.groups.add(self.admin_group)
        self.cohort = Cohort.objects.create(name="Test Cohort", level="beginner")
        self.user = User.objects.create(
            username="testuser", discord_username="test#1234", email="test@example.com"
        )

    def test_retrieve_cohort(self):
        """Test retrieving a cohort"""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(f"/cohort/{self.cohort.id}/")
        self.assertResponse(response, 200)
        self.assertEqual(response.data["name"], "Test Cohort")

    def test_update_cohort(self):
        """Test updating a cohort"""
        self.client.force_authenticate(user=self.admin_user)
        data = {"name": "Updated Cohort", "level": "advanced", "members": []}
        response = self.client.put(f"/cohort/{self.cohort.id}/", data)
        self.assertResponse(response, 200)

        self.cohort.refresh_from_db()
        self.assertEqual(self.cohort.name, "Updated Cohort")
        self.assertEqual(self.cohort.level, "advanced")

    def test_update_cohort_with_members(self):
        """Test updating a cohort with members"""
        self.client.force_authenticate(user=self.admin_user)
        data = {"name": "Test Cohort", "level": "beginner", "members": [self.user.id]}
        response = self.client.put(f"/cohort/{self.cohort.id}/", data)
        self.assertResponse(response, 200)

        self.assertTrue(CohortStats.objects.filter(cohort=self.cohort, member=self.user).exists())

    def test_delete_cohort(self):
        """Test deleting a cohort"""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.delete(f"/cohort/{self.cohort.id}/")
        self.assertResponse(response, 204)
        self.assertFalse(Cohort.objects.filter(id=self.cohort.id).exists())


class CohortStatsViewTests(AuthenticatedTestCase):
    """Test CohortStatsView"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.user = User.objects.create(
            username="testuser",
            discord_username="test#1234",
            email="test@example.com",
            discord_id="123456789",
        )
        self.cohort1 = Cohort.objects.create(name="Cohort 1", level="beginner")
        self.cohort2 = Cohort.objects.create(name="Cohort 2", level="intermediate")
        self.cohort1.members.add(self.user)

        self.stats1 = CohortStats.objects.create(
            cohort=self.cohort1,
            member=self.user,
            applications=10,
            onlineAssessments=5,
            interviews=3,
            offers=1,
            dailyChecks=20,
            streak=7,
        )

    def test_get_stats_by_cohort_id(self):
        """Test getting stats by cohort ID"""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(f"/cohort/stats/?cohort_id={self.cohort1.id}")
        self.assertResponse(response, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["cohort"]["id"], self.cohort1.id)

    def test_get_stats_by_member_id(self):
        """Test getting stats by member ID"""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(f"/cohort/stats/?member_id={self.user.id}")
        self.assertResponse(response, 200)
        self.assertEqual(len(response.data), 1)

    def test_get_stats_by_discord_id(self):
        """Test getting stats by discord ID"""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(f"/cohort/stats/?discord_id={self.user.discord_id}")
        self.assertResponse(response, 200)
        self.assertEqual(len(response.data), 1)

    def test_get_stats_multiple_params_error(self):
        """Test error when multiple params provided"""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(
            f"/cohort/stats/?cohort_id={self.cohort1.id}&member_id={self.user.id}"
        )
        self.assertResponse(response, 400)

    def test_get_stats_invalid_discord_id(self):
        """Test error with invalid discord ID"""
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/cohort/stats/?discord_id=999999999")
        self.assertResponse(response, 400)

    def test_get_all_stats(self):
        """Test getting all stats"""
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/cohort/stats/")
        self.assertResponse(response, 200)


class CohortRemoveMemberViewTests(AuthenticatedTestCase):
    """Test CohortRemoveMemberView"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.admin_group = Group.objects.get_or_create(name="is_admin")[0]
        self.admin_user = User.objects.create(
            username="adminuser", discord_username="admin#1234", email="admin@example.com"
        )
        self.admin_user.groups.add(self.admin_group)
        self.user = User.objects.create(
            username="testuser", discord_username="test#1234", email="test@example.com"
        )
        self.cohort = Cohort.objects.create(name="Test Cohort", level="beginner")
        self.cohort.members.add(self.user)
        self.stats = CohortStats.objects.create(cohort=self.cohort, member=self.user)

    def test_remove_member_from_cohort(self):
        """Test removing a member from a cohort"""
        self.client.force_authenticate(user=self.admin_user)
        data = {"member_id": self.user.id, "cohort_id": self.cohort.id}
        response = self.client.post("/cohort/remove/", data)
        self.assertResponse(response, 200)

        self.assertFalse(self.cohort.members.filter(id=self.user.id).exists())
        self.assertFalse(CohortStats.objects.filter(cohort=self.cohort, member=self.user).exists())

    def test_remove_member_invalid_member_id(self):
        """Test removing with invalid member ID"""
        self.client.force_authenticate(user=self.admin_user)
        data = {"member_id": 99999, "cohort_id": self.cohort.id}
        response = self.client.post("/cohort/remove/", data)
        self.assertResponse(response, 404)

    def test_remove_member_invalid_cohort_id(self):
        """Test removing with invalid cohort ID"""
        self.client.force_authenticate(user=self.admin_user)
        data = {"member_id": self.user.id, "cohort_id": 99999}
        response = self.client.post("/cohort/remove/", data)
        self.assertResponse(response, 404)


class CohortTransferViewTests(AuthenticatedTestCase):
    """Test CohortTransferView"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.admin_group = Group.objects.get_or_create(name="is_admin")[0]
        self.admin_user = User.objects.create(
            username="adminuser", discord_username="admin#1234", email="admin@example.com"
        )
        self.admin_user.groups.add(self.admin_group)
        self.user = User.objects.create(
            username="testuser", discord_username="test#1234", email="test@example.com"
        )
        self.from_cohort = Cohort.objects.create(name="From Cohort", level="beginner")
        self.to_cohort = Cohort.objects.create(name="To Cohort", level="intermediate")
        self.from_cohort.members.add(self.user)
        self.stats = CohortStats.objects.create(cohort=self.from_cohort, member=self.user)

    def test_transfer_member_between_cohorts(self):
        """Test transferring a member between cohorts"""
        self.client.force_authenticate(user=self.admin_user)
        data = {
            "member_id": self.user.id,
            "from_cohort_id": self.from_cohort.id,
            "to_cohort_id": self.to_cohort.id,
        }
        response = self.client.post("/cohort/transfer/", data)
        self.assertResponse(response, 200)

        self.assertFalse(self.from_cohort.members.filter(id=self.user.id).exists())
        self.assertTrue(self.to_cohort.members.filter(id=self.user.id).exists())

        self.stats.refresh_from_db()
        self.assertEqual(self.stats.cohort, self.to_cohort)

    def test_transfer_member_invalid_member_id(self):
        """Test transfer with invalid member ID"""
        self.client.force_authenticate(user=self.admin_user)
        data = {
            "member_id": 99999,
            "from_cohort_id": self.from_cohort.id,
            "to_cohort_id": self.to_cohort.id,
        }
        response = self.client.post("/cohort/transfer/", data)
        self.assertResponse(response, 404)

    def test_transfer_member_invalid_from_cohort(self):
        """Test transfer with invalid from_cohort_id"""
        self.client.force_authenticate(user=self.admin_user)
        data = {
            "member_id": self.user.id,
            "from_cohort_id": 99999,
            "to_cohort_id": self.to_cohort.id,
        }
        response = self.client.post("/cohort/transfer/", data)
        self.assertResponse(response, 404)

    def test_transfer_member_invalid_to_cohort(self):
        """Test transfer with invalid to_cohort_id"""
        self.client.force_authenticate(user=self.admin_user)
        data = {
            "member_id": self.user.id,
            "from_cohort_id": self.from_cohort.id,
            "to_cohort_id": 99999,
        }
        response = self.client.post("/cohort/transfer/", data)
        self.assertResponse(response, 404)


class CohortDashboardViewTests(AuthenticatedTestCase):
    """Test CohortDashboardView"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.user = User.objects.create(
            username="testuser", discord_username="test#1234", email="test@example.com"
        )
        self.cohort = Cohort.objects.create(name="Test Cohort", level="beginner", is_active=True)
        self.cohort.members.add(self.user)
        self.stats = CohortStats.objects.create(
            cohort=self.cohort,
            member=self.user,
            applications=10,
            onlineAssessments=5,
            interviews=3,
            offers=1,
            dailyChecks=20,
            streak=7,
        )

    @patch("cohort.views.connection")
    def test_get_dashboard(self, mock_connection):
        """Test getting dashboard data"""
        mock_cursor = MagicMock()
        mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

        # Mock the query results
        mock_cursor.description = [
            ("type",),
            ("cohort_id",),
            ("name",),
            ("level",),
            ("applications",),
            ("onlineAssessments",),
            ("interviews",),
            ("offers",),
            ("dailyChecks",),
            ("streak",),
            ("applications_sum",),
            ("applications_max",),
            ("applications_avg",),
            ("online_assessments_sum",),
            ("online_assessments_max",),
            ("online_assessments_avg",),
            ("interviews_sum",),
            ("interviews_max",),
            ("interviews_avg",),
            ("offers_sum",),
            ("offers_max",),
            ("offers_avg",),
            ("daily_checks_sum",),
            ("daily_checks_max",),
            ("daily_checks_avg",),
            ("streak_sum",),
            ("streak_max",),
            ("streak_avg",),
        ]

        mock_cursor.fetchall.return_value = [
            (
                "user_cohorts",
                self.cohort.id,
                "Test Cohort",
                "beginner",
                10,
                5,
                3,
                1,
                20,
                7,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
            ),
            (
                "aggregate_stats",
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                10,
                10,
                10.0,
                5,
                5,
                5.0,
                3,
                3,
                3.0,
                1,
                1,
                1.0,
                20,
                20,
                20.0,
                7,
                7,
                7.0,
            ),
        ]

        self.client.force_authenticate(user=self.user)
        response = self.client.get("/cohort/dashboard/")
        self.assertResponse(response, 200)

        self.assertIn("your_cohorts", response.data)
        self.assertIn("cohorts_aggregated_stats_total", response.data)
        self.assertIn("cohorts_aggregated_stats_max", response.data)
        self.assertIn("cohorts_aggregated_stats_avg", response.data)


class LinkCohortsWithDiscordViewTests(AuthenticatedTestCase):
    """Test LinkCohortsWithDiscordView"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.admin_group = Group.objects.get_or_create(name="is_admin")[0]
        self.admin_user = User.objects.create(
            username="adminuser", discord_username="admin#1234", email="admin@example.com"
        )
        self.admin_user.groups.add(self.admin_group)
        self.user = User.objects.create(
            username="testuser",
            discord_username="test#1234",
            email="test@example.com",
            discord_id="123456789",
        )
        self.cohort = Cohort.objects.create(name="Test Cohort", level="beginner")
        self.cohort.members.add(self.user)

    def test_get_discord_links(self):
        """Test getting discord links"""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get("/cohort/sync/discord/")
        self.assertResponse(response, 200)
        self.assertEqual(len(response.data), 1)
        self.assertIn("discord_member_ids", response.data[0])

    def test_link_cohorts_with_discord(self):
        """Test linking cohorts with discord"""
        self.client.force_authenticate(user=self.admin_user)
        data = [
            {
                "id": self.cohort.id,
                "discord_channel_id": 111111111,
                "discord_role_id": 222222222,
            }
        ]
        response = self.client.post("/cohort/sync/discord/", data, format="json")
        self.assertResponse(response, 200)

        self.cohort.refresh_from_db()
        self.assertEqual(self.cohort.discord_channel_id, 111111111)
        self.assertEqual(self.cohort.discord_role_id, 222222222)

    def test_link_cohorts_invalid_data_format(self):
        """Test linking with invalid data format"""
        self.client.force_authenticate(user=self.admin_user)
        data = "invalid"
        response = self.client.post("/cohort/sync/discord/", data, format="json")
        self.assertResponse(response, 400)

    def test_link_cohorts_missing_fields(self):
        """Test linking with missing fields"""
        self.client.force_authenticate(user=self.admin_user)
        data = [{"id": self.cohort.id}]
        response = self.client.post("/cohort/sync/discord/", data, format="json")
        self.assertResponse(response, 400)

    def test_link_cohorts_invalid_cohort_id(self):
        """Test linking with invalid cohort ID"""
        self.client.force_authenticate(user=self.admin_user)
        data = [
            {
                "id": 99999,
                "discord_channel_id": 111111111,
                "discord_role_id": 222222222,
            }
        ]
        response = self.client.post("/cohort/sync/discord/", data, format="json")
        self.assertResponse(response, 404)

    def test_delete_discord_mappings(self):
        """Test deleting all discord mappings"""
        self.cohort.discord_channel_id = 111111111
        self.cohort.discord_role_id = 222222222
        self.cohort.save()

        self.client.force_authenticate(user=self.admin_user)
        response = self.client.delete("/cohort/sync/discord/")
        self.assertResponse(response, 200)

        self.cohort.refresh_from_db()
        self.assertIsNone(self.cohort.discord_channel_id)
        self.assertIsNone(self.cohort.discord_role_id)
