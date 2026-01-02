import os
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from members.models import User
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from rest_framework_api_key.models import APIKey

from .managers import (
    AttendanceLeaderboardManager,
    CohortStatsLeaderboardManager,
    GitHubLeaderboardManager,
    LeetcodeLeaderboardManager,
)
from .models import GitHubStats, InternshipApplicationStats, LeetcodeStats, NewGradApplicationStats
from .serializers import (
    GitHubStatsSerializer,
    InternshipApplicationStatsSerializer,
    LeetcodeStatsSerializer,
    NewGradApplicationStatsSerializer,
)

# ============================================================================
# Model Tests
# ============================================================================


class LeetcodeStatsModelTest(TestCase):
    """Test LeetcodeStats model"""

    def setUp(self):
        self.user = User.objects.create(
            username="testuser",
            discord_id="123456789",
            discord_username="test_user",
            leetcode={"username": "leetcode_user", "isPrivate": False},
        )

    def test_create_leetcode_stats(self):
        """Test creating LeetcodeStats instance"""
        stats = LeetcodeStats.objects.create(
            user=self.user,
            total_solved=100,
            easy_solved=40,
            medium_solved=50,
            hard_solved=10,
        )
        self.assertEqual(stats.user, self.user)
        self.assertEqual(stats.total_solved, 100)
        self.assertEqual(stats.easy_solved, 40)
        self.assertEqual(stats.medium_solved, 50)
        self.assertEqual(stats.hard_solved, 10)
        self.assertIsNotNone(stats.last_updated)

    def test_leetcode_stats_defaults(self):
        """Test default values for LeetcodeStats"""
        stats = LeetcodeStats.objects.create(user=self.user)
        self.assertEqual(stats.total_solved, 0)
        self.assertEqual(stats.easy_solved, 0)
        self.assertEqual(stats.medium_solved, 0)
        self.assertEqual(stats.hard_solved, 0)

    def test_leetcode_stats_str(self):
        """Test string representation"""
        stats = LeetcodeStats.objects.create(user=self.user)
        self.assertEqual(str(stats), "testuser's Leetcode Stats")

    def test_leetcode_stats_ordering(self):
        """Test ordering by total_solved, hard_solved, medium_solved"""
        user2 = User.objects.create(
            username="user2",
            discord_id="987654321",
            discord_username="user_2",
            leetcode={"username": "leetcode_user2", "isPrivate": False},
        )
        stats1 = LeetcodeStats.objects.create(
            user=self.user, total_solved=100, hard_solved=10, medium_solved=50
        )
        stats2 = LeetcodeStats.objects.create(
            user=user2, total_solved=150, hard_solved=20, medium_solved=60
        )

        all_stats = list(LeetcodeStats.objects.all())
        self.assertEqual(all_stats[0], stats2)
        self.assertEqual(all_stats[1], stats1)

    def test_leetcode_stats_one_to_one_relationship(self):
        """Test one-to-one relationship with User"""
        from django.db import IntegrityError

        LeetcodeStats.objects.create(user=self.user)
        with self.assertRaises(IntegrityError):
            LeetcodeStats.objects.create(user=self.user)


class GitHubStatsModelTest(TestCase):
    """Test GitHubStats model"""

    def setUp(self):
        self.user = User.objects.create(
            username="testuser",
            discord_id="123456789",
            discord_username="test_user",
            github={"username": "github_user", "isPrivate": False},
        )

    def test_create_github_stats(self):
        """Test creating GitHubStats instance"""
        stats = GitHubStats.objects.create(
            user=self.user, total_prs=50, total_commits=200, followers=30
        )
        self.assertEqual(stats.user, self.user)
        self.assertEqual(stats.total_prs, 50)
        self.assertEqual(stats.total_commits, 200)
        self.assertEqual(stats.followers, 30)
        self.assertIsNotNone(stats.last_updated)

    def test_github_stats_defaults(self):
        """Test default values for GitHubStats"""
        stats = GitHubStats.objects.create(user=self.user)
        self.assertEqual(stats.total_prs, 0)
        self.assertEqual(stats.total_commits, 0)
        self.assertEqual(stats.followers, 0)

    def test_github_stats_str(self):
        """Test string representation"""
        stats = GitHubStats.objects.create(user=self.user)
        self.assertEqual(str(stats), "testuser's GitHub Stats")

    def test_github_stats_ordering(self):
        """Test ordering by total_commits, total_prs"""
        user2 = User.objects.create(
            username="user2",
            discord_id="987654321",
            discord_username="user_2",
            github={"username": "github_user2", "isPrivate": False},
        )
        stats1 = GitHubStats.objects.create(user=self.user, total_commits=100, total_prs=10)
        stats2 = GitHubStats.objects.create(user=user2, total_commits=200, total_prs=20)

        all_stats = list(GitHubStats.objects.all())
        self.assertEqual(all_stats[0], stats2)
        self.assertEqual(all_stats[1], stats1)


class InternshipApplicationStatsModelTest(TestCase):
    """Test InternshipApplicationStats model"""

    def setUp(self):
        self.user = User.objects.create(
            username="testuser", discord_id="123456789", discord_username="test_user"
        )

    def test_create_internship_stats(self):
        """Test creating InternshipApplicationStats instance"""
        stats = InternshipApplicationStats.objects.create(user=self.user, applied=25)
        self.assertEqual(stats.user, self.user)
        self.assertEqual(stats.applied, 25)
        self.assertIsNotNone(stats.last_updated)

    def test_internship_stats_defaults(self):
        """Test default values"""
        stats = InternshipApplicationStats.objects.create(user=self.user)
        self.assertEqual(stats.applied, 0)

    def test_internship_stats_str(self):
        """Test string representation"""
        stats = InternshipApplicationStats.objects.create(user=self.user)
        self.assertEqual(str(stats), "testuser's Internship Application Stats")

    def test_internship_stats_ordering(self):
        """Test ordering by applied"""
        user2 = User.objects.create(
            username="user2", discord_id="987654321", discord_username="user_2"
        )
        stats1 = InternshipApplicationStats.objects.create(user=self.user, applied=10)
        stats2 = InternshipApplicationStats.objects.create(user=user2, applied=20)

        all_stats = list(InternshipApplicationStats.objects.all())
        self.assertEqual(all_stats[0], stats2)
        self.assertEqual(all_stats[1], stats1)


class NewGradApplicationStatsModelTest(TestCase):
    """Test NewGradApplicationStats model"""

    def setUp(self):
        self.user = User.objects.create(
            username="testuser", discord_id="123456789", discord_username="test_user"
        )

    def test_create_newgrad_stats(self):
        """Test creating NewGradApplicationStats instance"""
        stats = NewGradApplicationStats.objects.create(user=self.user, applied=15)
        self.assertEqual(stats.user, self.user)
        self.assertEqual(stats.applied, 15)
        self.assertIsNotNone(stats.last_updated)

    def test_newgrad_stats_defaults(self):
        """Test default values"""
        stats = NewGradApplicationStats.objects.create(user=self.user)
        self.assertEqual(stats.applied, 0)

    def test_newgrad_stats_str(self):
        """Test string representation"""
        stats = NewGradApplicationStats.objects.create(user=self.user)
        self.assertEqual(str(stats), "testuser's New Grad Application Stats")

    def test_newgrad_stats_ordering(self):
        """Test ordering by applied"""
        user2 = User.objects.create(
            username="user2", discord_id="987654321", discord_username="user_2"
        )
        stats1 = NewGradApplicationStats.objects.create(user=self.user, applied=5)
        stats2 = NewGradApplicationStats.objects.create(user=user2, applied=10)

        all_stats = list(NewGradApplicationStats.objects.all())
        self.assertEqual(all_stats[0], stats2)
        self.assertEqual(all_stats[1], stats1)


# ============================================================================
# Serializer Tests
# ============================================================================


class LeetcodeStatsSerializerTest(TestCase):
    """Test LeetcodeStatsSerializer"""

    def setUp(self):
        self.user = User.objects.create(
            username="testuser",
            discord_id="123456789",
            discord_username="test_user",
            leetcode={"username": "leetcode_user", "isPrivate": False},
        )
        self.stats = LeetcodeStats.objects.create(
            user=self.user,
            total_solved=100,
            easy_solved=40,
            medium_solved=50,
            hard_solved=10,
        )

    def test_serializer_fields(self):
        """Test serializer contains expected fields"""
        serializer = LeetcodeStatsSerializer(self.stats)
        data = serializer.data
        self.assertIn("user", data)
        self.assertIn("total_solved", data)
        self.assertIn("easy_solved", data)
        self.assertIn("medium_solved", data)
        self.assertIn("hard_solved", data)
        self.assertIn("last_updated", data)

    def test_serializer_user_field(self):
        """Test user field returns username from leetcode"""
        serializer = LeetcodeStatsSerializer(self.stats)
        data = serializer.data
        self.assertEqual(data["user"]["username"], "leetcode_user")

    def test_serializer_values(self):
        """Test serializer returns correct values"""
        serializer = LeetcodeStatsSerializer(self.stats)
        data = serializer.data
        self.assertEqual(data["total_solved"], 100)
        self.assertEqual(data["easy_solved"], 40)
        self.assertEqual(data["medium_solved"], 50)
        self.assertEqual(data["hard_solved"], 10)


class GitHubStatsSerializerTest(TestCase):
    """Test GitHubStatsSerializer"""

    def setUp(self):
        self.user = User.objects.create(
            username="testuser",
            discord_id="123456789",
            discord_username="test_user",
            github={"username": "github_user", "isPrivate": False},
        )
        self.stats = GitHubStats.objects.create(
            user=self.user, total_prs=50, total_commits=200, followers=30
        )

    def test_serializer_fields(self):
        """Test serializer contains expected fields"""
        serializer = GitHubStatsSerializer(self.stats)
        data = serializer.data
        self.assertIn("user", data)
        self.assertIn("total_prs", data)
        self.assertIn("total_commits", data)
        self.assertIn("followers", data)
        self.assertIn("last_updated", data)

    def test_serializer_user_field(self):
        """Test user field returns username from github"""
        serializer = GitHubStatsSerializer(self.stats)
        data = serializer.data
        self.assertEqual(data["user"]["username"], "github_user")


class InternshipApplicationStatsSerializerTest(TestCase):
    """Test InternshipApplicationStatsSerializer"""

    def setUp(self):
        self.user = User.objects.create(
            username="testuser", discord_id="123456789", discord_username="test_user"
        )
        self.stats = InternshipApplicationStats.objects.create(user=self.user, applied=25)

    def test_serializer_fields(self):
        """Test serializer contains expected fields"""
        serializer = InternshipApplicationStatsSerializer(self.stats)
        data = serializer.data
        self.assertIn("user", data)
        self.assertIn("applied", data)
        self.assertIn("last_updated", data)

    def test_serializer_user_field(self):
        """Test user field returns username"""
        serializer = InternshipApplicationStatsSerializer(self.stats)
        data = serializer.data
        self.assertEqual(data["user"]["username"], "testuser")


class NewGradApplicationStatsSerializerTest(TestCase):
    """Test NewGradApplicationStatsSerializer"""

    def setUp(self):
        self.user = User.objects.create(
            username="testuser", discord_id="123456789", discord_username="test_user"
        )
        self.stats = NewGradApplicationStats.objects.create(user=self.user, applied=15)

    def test_serializer_fields(self):
        """Test serializer contains expected fields"""
        serializer = NewGradApplicationStatsSerializer(self.stats)
        data = serializer.data
        self.assertIn("user", data)
        self.assertIn("applied", data)
        self.assertIn("last_updated", data)

    def test_serializer_user_field(self):
        """Test user field returns username"""
        serializer = NewGradApplicationStatsSerializer(self.stats)
        data = serializer.data
        self.assertEqual(data["user"]["username"], "testuser")


# ============================================================================
# Manager Tests
# ============================================================================


class LeetcodeLeaderboardManagerTest(TestCase):
    """Test LeetcodeLeaderboardManager"""

    def setUp(self):
        self.user1 = User.objects.create(
            username="user1",
            discord_id="111111111",
            discord_username="user_1",
            leetcode={"username": "lc_user1", "isPrivate": False},
        )
        self.user2 = User.objects.create(
            username="user2",
            discord_id="222222222",
            discord_username="user_2",
            leetcode={"username": "lc_user2", "isPrivate": False},
        )
        LeetcodeStats.objects.create(
            user=self.user1, total_solved=100, easy_solved=40, medium_solved=50, hard_solved=10
        )
        LeetcodeStats.objects.create(
            user=self.user2, total_solved=150, easy_solved=50, medium_solved=70, hard_solved=30
        )

    def test_get_all_from_db(self):
        """Test get_all_from_db returns all stats"""
        mock_cache = MagicMock()
        manager = LeetcodeLeaderboardManager(mock_cache, lambda: "test_key")

        data = manager.get_all_from_db()
        self.assertEqual(len(data), 2)
        self.assertIn("total_solved", data[0])
        self.assertIn("user", data[0])

    def test_get_all_with_cache_miss(self):
        """Test get_all when cache is empty"""
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        manager = LeetcodeLeaderboardManager(mock_cache, lambda: "test_key")

        data = manager.get_all()
        mock_cache.get.assert_called_once_with("test_key")
        mock_cache.set.assert_called_once()
        self.assertEqual(len(data), 2)

    def test_get_all_with_cache_hit(self):
        """Test get_all when cache has data"""
        cached_data = [{"total_solved": 100}]
        mock_cache = MagicMock()
        mock_cache.get.return_value = cached_data
        manager = LeetcodeLeaderboardManager(mock_cache, lambda: "test_key")

        data = manager.get_all()
        mock_cache.get.assert_called_once_with("test_key")
        mock_cache.set.assert_not_called()
        self.assertEqual(data, cached_data)


class GitHubLeaderboardManagerTest(TestCase):
    """Test GitHubLeaderboardManager"""

    def setUp(self):
        self.user1 = User.objects.create(
            username="user1",
            discord_id="111111111",
            discord_username="user_1",
            github={"username": "gh_user1", "isPrivate": False},
        )
        GitHubStats.objects.create(user=self.user1, total_prs=50, total_commits=200, followers=30)

    def test_get_all_from_db(self):
        """Test get_all_from_db returns all stats"""
        mock_cache = MagicMock()
        manager = GitHubLeaderboardManager(mock_cache, lambda: "test_key")

        data = manager.get_all_from_db()
        self.assertEqual(len(data), 1)
        self.assertIn("total_prs", data[0])
        self.assertIn("total_commits", data[0])
        self.assertIn("followers", data[0])
        self.assertIn("user", data[0])

    def test_refresh_key(self):
        """Test refresh_key updates cache"""
        mock_cache = MagicMock()
        manager = GitHubLeaderboardManager(mock_cache, lambda: "test_key")

        test_data = [{"total_prs": 100}]
        manager.refresh_key("test_key", test_data)
        mock_cache.set.assert_called_once_with("test_key", test_data)


# ============================================================================
# View Tests
# ============================================================================


class LeetcodeLeaderboardViewTest(APITestCase):
    """Test LeetcodeLeaderboardView"""

    def setUp(self):
        self.client = APIClient()
        self.url = reverse("leetcode-leaderboard")
        self.user1 = User.objects.create(
            username="user1",
            discord_id="111111111",
            discord_username="user_1",
            leetcode={"username": "lc_user1", "isPrivate": False},
        )
        self.user2 = User.objects.create(
            username="user2",
            discord_id="222222222",
            discord_username="user_2",
            leetcode={"username": "lc_user2", "isPrivate": False},
        )
        LeetcodeStats.objects.create(
            user=self.user1, total_solved=100, easy_solved=40, medium_solved=50, hard_solved=10
        )
        LeetcodeStats.objects.create(
            user=self.user2, total_solved=150, easy_solved=50, medium_solved=70, hard_solved=30
        )

    def test_get_leetcode_leaderboard_default_ordering(self):
        """Test GET leaderboard with default ordering (total)"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("results", response.json())
        results = response.json()["results"]
        self.assertEqual(len(results), 2)
        # Should be ordered by total_solved descending
        self.assertEqual(results[0]["total_solved"], 150)
        self.assertEqual(results[1]["total_solved"], 100)

    def test_get_leetcode_leaderboard_order_by_hard(self):
        """Test GET leaderboard ordered by hard problems"""
        response = self.client.get(self.url, {"order_by": "hard"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.json()["results"]
        self.assertEqual(results[0]["hard_solved"], 30)
        self.assertEqual(results[1]["hard_solved"], 10)

    def test_get_leetcode_leaderboard_order_by_medium(self):
        """Test GET leaderboard ordered by medium problems"""
        response = self.client.get(self.url, {"order_by": "medium"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.json()["results"]
        self.assertEqual(results[0]["medium_solved"], 70)

    def test_get_leetcode_leaderboard_order_by_easy(self):
        """Test GET leaderboard ordered by easy problems"""
        response = self.client.get(self.url, {"order_by": "easy"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.json()["results"]
        self.assertEqual(results[0]["easy_solved"], 50)

    def test_get_leetcode_leaderboard_invalid_order_by(self):
        """Test GET leaderboard with invalid order_by parameter"""
        response = self.client.get(self.url, {"order_by": "invalid"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_get_leetcode_leaderboard_with_time_filter(self):
        """Test GET leaderboard with time filter"""
        # Update one user's stats to be recent
        stats = LeetcodeStats.objects.get(user=self.user1)
        stats.last_updated = timezone.now()
        stats.save()

        # Update another to be old
        stats2 = LeetcodeStats.objects.get(user=self.user2)
        stats2.last_updated = timezone.now() - timedelta(hours=48)
        stats2.save()

        response = self.client.get(self.url, {"updated_within": "24"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.json()["results"]
        self.assertEqual(len(results), 1)

    def test_get_leetcode_leaderboard_invalid_time_filter(self):
        """Test GET leaderboard with invalid time filter"""
        response = self.client.get(self.url, {"updated_within": "invalid"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_leetcode_leaderboard_completion_rate(self):
        """Test completion rate calculation"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.json()["results"]
        # Each result should have completion_rate
        for result in results:
            self.assertIn("completion_rate", result)


class GitHubLeaderboardViewTest(APITestCase):
    """Test GitHubLeaderboardView"""

    def setUp(self):
        self.client = APIClient()
        self.url = reverse("github-leaderboard")
        self.user1 = User.objects.create(
            username="user1",
            discord_id="111111111",
            discord_username="user_1",
            github={"username": "gh_user1", "isPrivate": False},
        )
        self.user2 = User.objects.create(
            username="user2",
            discord_id="222222222",
            discord_username="user_2",
            github={"username": "gh_user2", "isPrivate": False},
        )
        GitHubStats.objects.create(user=self.user1, total_prs=50, total_commits=200, followers=30)
        GitHubStats.objects.create(user=self.user2, total_prs=100, total_commits=400, followers=60)

    def test_get_github_leaderboard_default_ordering(self):
        """Test GET leaderboard with default ordering (commits)"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.json()["results"]
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["total_commits"], 400)

    def test_get_github_leaderboard_order_by_prs(self):
        """Test GET leaderboard ordered by PRs"""
        response = self.client.get(self.url, {"order_by": "prs"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.json()["results"]
        self.assertEqual(results[0]["total_prs"], 100)

    def test_get_github_leaderboard_order_by_followers(self):
        """Test GET leaderboard ordered by followers"""
        response = self.client.get(self.url, {"order_by": "followers"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.json()["results"]
        self.assertEqual(results[0]["followers"], 60)

    def test_get_github_leaderboard_invalid_order_by(self):
        """Test GET leaderboard with invalid order_by parameter"""
        response = self.client.get(self.url, {"order_by": "invalid"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class InternshipApplicationLeaderboardViewTest(APITestCase):
    """Test InternshipApplicationLeaderboardView"""

    def setUp(self):
        self.client = APIClient()
        self.url = reverse("internship-leaderboard")
        self.user1 = User.objects.create(
            username="user1", discord_id="111111111", discord_username="user_1"
        )
        self.user2 = User.objects.create(
            username="user2", discord_id="222222222", discord_username="user_2"
        )
        InternshipApplicationStats.objects.create(user=self.user1, applied=25)
        InternshipApplicationStats.objects.create(user=self.user2, applied=50)

    def test_get_internship_leaderboard_default_ordering(self):
        """Test GET leaderboard with default ordering (applied)"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
        self.assertEqual(response.data[0]["applied"], 50)

    def test_get_internship_leaderboard_order_by_recent(self):
        """Test GET leaderboard ordered by recent"""
        response = self.client.get(self.url, {"order_by": "recent"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_get_internship_leaderboard_invalid_order_by(self):
        """Test GET leaderboard with invalid order_by parameter"""
        response = self.client.get(self.url, {"order_by": "invalid"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_get_internship_leaderboard_with_time_filter(self):
        """Test GET leaderboard with time filter"""
        stats = InternshipApplicationStats.objects.get(user=self.user1)
        stats.last_updated = timezone.now() - timedelta(hours=48)
        stats.save()

        response = self.client.get(self.url, {"updated_within": "24"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)


class NewGradApplicationLeaderboardViewTest(APITestCase):
    """Test NewGradApplicationLeaderboardView"""

    def setUp(self):
        self.client = APIClient()
        self.url = reverse("newgrad-leaderboard")
        self.user1 = User.objects.create(
            username="user1", discord_id="111111111", discord_username="user_1"
        )
        self.user2 = User.objects.create(
            username="user2", discord_id="222222222", discord_username="user_2"
        )
        NewGradApplicationStats.objects.create(user=self.user1, applied=15)
        NewGradApplicationStats.objects.create(user=self.user2, applied=30)

    def test_get_newgrad_leaderboard_default_ordering(self):
        """Test GET leaderboard with default ordering (applied)"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
        self.assertEqual(response.data[0]["applied"], 30)

    def test_get_newgrad_leaderboard_order_by_recent(self):
        """Test GET leaderboard ordered by recent"""
        response = self.client.get(self.url, {"order_by": "recent"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_get_newgrad_leaderboard_invalid_order_by(self):
        """Test GET leaderboard with invalid order_by parameter"""
        response = self.client.get(self.url, {"order_by": "invalid"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


@override_settings(INTERNSHIP_CHANNEL_ID=123456789, NEW_GRAD_CHANNEL_ID=987654321)
class InjestReactionEventViewTest(APITestCase):
    """Test InjestReactionEventView"""

    def setUp(self):
        self.client = APIClient()
        self.url = reverse("process-events")
        # Create API key for authentication
        api_key, key = APIKey.objects.create_key(name="test-bot")
        self.client.credentials(HTTP_AUTHORIZATION=f"Api-Key {key}")

        self.user = User.objects.create(
            username="testuser", discord_id="123456789", discord_username="test_user"
        )

    def test_post_internship_application_increment(self):
        """Test POST to increment internship applications"""
        response = self.client.post(self.url, {"discord_id": "123456789", "channel_id": 123456789})
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

        stats = InternshipApplicationStats.objects.get(user=self.user)
        self.assertEqual(stats.applied, 1)

    def test_post_newgrad_application_increment(self):
        """Test POST to increment new grad applications"""
        response = self.client.post(self.url, {"discord_id": "123456789", "channel_id": 987654321})
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

        stats = NewGradApplicationStats.objects.get(user=self.user)
        self.assertEqual(stats.applied, 1)

    def test_post_multiple_increments(self):
        """Test POST multiple times increments correctly"""
        self.client.post(self.url, {"discord_id": "123456789", "channel_id": 123456789})
        self.client.post(self.url, {"discord_id": "123456789", "channel_id": 123456789})

        stats = InternshipApplicationStats.objects.get(user=self.user)
        self.assertEqual(stats.applied, 2)

    def test_delete_internship_application_decrement(self):
        """Test DELETE to decrement internship applications"""
        # First create a stat
        InternshipApplicationStats.objects.create(user=self.user, applied=5)

        response = self.client.delete(
            self.url, {"discord_id": "123456789", "channel_id": 123456789}
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        stats = InternshipApplicationStats.objects.get(user=self.user)
        self.assertEqual(stats.applied, 4)

    def test_delete_application_at_zero(self):
        """Test DELETE when applied is already 0"""
        InternshipApplicationStats.objects.create(user=self.user, applied=0)

        response = self.client.delete(
            self.url, {"discord_id": "123456789", "channel_id": 123456789}
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        stats = InternshipApplicationStats.objects.get(user=self.user)
        self.assertEqual(stats.applied, 0)

    def test_post_invalid_channel_id(self):
        """Test POST with invalid channel_id"""
        response = self.client.post(self.url, {"discord_id": "123456789", "channel_id": 999999999})
        self.assertEqual(response.status_code, status.HTTP_304_NOT_MODIFIED)

    def test_post_user_not_found(self):
        """Test POST with non-existent user"""
        response = self.client.post(self.url, {"discord_id": "999999999", "channel_id": 123456789})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_user_not_found(self):
        """Test DELETE with non-existent user"""
        response = self.client.delete(
            self.url, {"discord_id": "999999999", "channel_id": 123456789}
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_post_without_authentication(self):
        """Test POST without API key authentication"""
        client = APIClient()  # No credentials
        response = client.post(self.url, {"discord_id": "123456789", "channel_id": 123456789})
        # Should fail authentication
        self.assertIn(
            response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]
        )
