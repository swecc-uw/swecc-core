from datetime import timedelta
from unittest.mock import MagicMock, patch

from cohort.models import Cohort
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from leaderboard.models import GitHubStats, LeetcodeStats
from members.models import User
from rest_framework.test import APIClient, APITestCase

from .buffer import Message, MessageBuffer
from .models import AttendanceSession, AttendanceSessionStats, CohortStats, DiscordMessageStats
from .serializers import (
    AttendanceSessionSerializer,
    AttendanceStatsSerializer,
    AttendeeSerializer,
    CohortStatsLeaderboardSerializer,
    CohortStatsSerializer,
    MemberSerializer,
)


class AuthenticatedTestCase(TestCase):
    """Base test case that automatically mocks authentication"""

    def setUp(self):
        super().setUp()
        self.api_patcher = patch("members.permissions.IsApiKey.has_permission")
        self.admin_patcher = patch("custom_auth.permissions.IsAdmin.has_permission")

        # Start the patchers
        self.mock_api_perm = self.api_patcher.start()
        self.mock_admin_perm = self.admin_patcher.start()

        # Set return values
        self.mock_api_perm.return_value = True
        self.mock_admin_perm.return_value = True

    def tearDown(self):
        super().tearDown()
        # Stop the patchers
        self.api_patcher.stop()
        self.admin_patcher.stop()

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


class AttendanceAPITests(AuthenticatedTestCase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        # Create test user
        self.user = User.objects.create(discord_id="123456789", discord_username="test_user")
        self.user2 = User.objects.create(
            username="2", discord_id="987654321", discord_username="test_user2"
        )
        # Create test session
        self.session = AttendanceSession.objects.create(
            title="Test Session",
            key="test-key",
            expires=(timezone.now() + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
        )
        self.expired_session = AttendanceSession.objects.create(
            title="Expired Session",
            key="expired-key",
            expires=(timezone.now() - timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
        )

    def test_create_session(self):
        response = self.client.post(
            "/engagement/attendance/session",
            {
                "title": "New Session",
                "key": "new-key",
                "expires": (timezone.now() + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
            },
        )
        self.assertResponse(response, 201)
        self.assertTrue(
            AttendanceSession.objects.filter(title="New Session").exists(),
            "Session was not created in database",
        )

    def test_create_duplicate_active_session(self):
        response = self.client.post(
            "/engagement/attendance/session",
            {
                "title": "New Session",
                "key": "test-key",
                "expires": (timezone.now() + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
            },
        )
        self.assertResponse(response, 400)

    def test_create_duplicate_expired_session(self):
        response = self.client.post(
            "/engagement/attendance/session",
            {
                "title": "New Session",
                "key": "expired-key",
                "expires": (timezone.now() - timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
            },
        )
        self.assertResponse(response, 201)

    def test_get_all_sessions(self):
        response = self.client.get("/engagement/attendance/")
        self.assertResponse(response, 200)
        self.assertEqual(
            len(response.data),
            2,
            f"Expected 2 sessions, got {len(response.data)}. Data: {response.data}",
        )

    def test_get_member_sessions(self):
        self.session.attendees.add(self.user)
        response = self.client.get(f"/engagement/attendance/member/{self.user.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)

    def test_get_session_attendees(self):
        self.session.attendees.add(self.user)
        response = self.client.get(f"/engagement/attendance/session/{self.session.session_id}/")
        self.assertResponse(response, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], self.user.id)

    def test_attend_session(self):
        response = self.client.post(
            "/engagement/attendance/attend",
            {"session_key": "test-key", "discord_id": "123456789"},
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(self.session.attendees.filter(id=self.user.id).exists())

    def test_attend_expired_session(self):
        response = self.client.post(
            "/engagement/attendance/attend",
            {"session_key": "expired-key", "discord_id": "123456789"},
        )
        self.assertResponse(response, 400)
        self.assertEqual(
            response.data["error"],
            "Session has expired",
            f"Unexpected error message: {response.data}",
        )

    def test_attend_nonexistent_session(self):
        response = self.client.post(
            "/engagement/attendance/attend",
            {"session_key": "nonexistent-key", "discord_id": "123456789"},
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["error"], "Session not found")

    def test_attend_nonexistent_member(self):
        response = self.client.post(
            "/engagement/attendance/attend",
            {"session_key": "test-key", "discord_id": "999999999"},
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["error"], "Member not found")

    def test_get_user_with_multiple_attendance(self):
        self.session.attendees.add(self.user, self.user2)
        response = self.client.get(f"/engagement/attendance/member/{self.user.id}/")


# ============================================================================
# Model Tests
# ============================================================================


class AttendanceSessionModelTests(TestCase):
    """Test AttendanceSession model"""

    def setUp(self):
        self.user = User.objects.create(discord_id="123456789", discord_username="test_user")

    def test_attendance_session_creation(self):
        """Test creating an attendance session"""
        session = AttendanceSession.objects.create(
            title="Test Session",
            key="test-key",
            expires=timezone.now() + timedelta(hours=1),
        )
        self.assertEqual(session.title, "Test Session")
        self.assertEqual(session.key, "test-key")
        self.assertTrue(session.is_active())

    def test_attendance_session_str_representation(self):
        """Test string representation"""
        session = AttendanceSession.objects.create(
            title="Test Session",
            key="test-key",
            expires=timezone.now() + timedelta(hours=1),
        )
        self.assertIn("Test Session", str(session))
        self.assertIn("test-key", str(session))

    def test_is_active_returns_true_for_future_expiry(self):
        """Test is_active returns True for future expiry"""
        session = AttendanceSession.objects.create(
            title="Active Session",
            key="active-key",
            expires=timezone.now() + timedelta(hours=1),
        )
        self.assertTrue(session.is_active())

    def test_is_active_returns_false_for_past_expiry(self):
        """Test is_active returns False for past expiry"""
        session = AttendanceSession.objects.create(
            title="Expired Session",
            key="expired-key",
            expires=timezone.now() - timedelta(hours=1),
        )
        self.assertFalse(session.is_active())

    def test_duplicate_active_session_key_raises_validation_error(self):
        """Test that duplicate active session keys raise ValidationError"""
        AttendanceSession.objects.create(
            title="Session 1",
            key="duplicate-key",
            expires=timezone.now() + timedelta(hours=1),
        )
        with self.assertRaises(ValidationError):
            AttendanceSession.objects.create(
                title="Session 2",
                key="duplicate-key",
                expires=timezone.now() + timedelta(hours=2),
            )

    def test_duplicate_expired_session_key_allowed(self):
        """Test that duplicate expired session keys are allowed"""
        AttendanceSession.objects.create(
            title="Session 1",
            key="expired-key",
            expires=timezone.now() - timedelta(hours=2),
        )
        session2 = AttendanceSession.objects.create(
            title="Session 2",
            key="expired-key",
            expires=timezone.now() - timedelta(hours=1),
        )
        self.assertIsNotNone(session2.session_id)

    def test_attendees_many_to_many_relationship(self):
        """Test adding attendees to session"""
        session = AttendanceSession.objects.create(
            title="Test Session",
            key="test-key",
            expires=timezone.now() + timedelta(hours=1),
        )
        session.attendees.add(self.user)
        self.assertEqual(session.attendees.count(), 1)
        self.assertIn(self.user, session.attendees.all())

    def test_timezone_conversion_to_utc(self):
        """Test that expires is converted to UTC"""
        naive_time = timezone.now().replace(tzinfo=None) + timedelta(hours=1)
        aware_time = timezone.make_aware(naive_time)
        session = AttendanceSession.objects.create(
            title="Test Session",
            key="test-key",
            expires=aware_time,
        )
        self.assertEqual(session.expires.tzinfo, timezone.utc)


class DiscordMessageStatsModelTests(TestCase):
    """Test DiscordMessageStats model"""

    def setUp(self):
        self.user = User.objects.create(discord_id="123456789", discord_username="test_user")

    def test_discord_message_stats_creation(self):
        """Test creating discord message stats"""
        stats = DiscordMessageStats.objects.create(
            member=self.user,
            channel_id="987654321",
            message_count=10,
        )
        self.assertEqual(stats.member, self.user)
        self.assertEqual(stats.channel_id, "987654321")
        self.assertEqual(stats.message_count, 10)

    def test_discord_message_stats_str_representation(self):
        """Test string representation"""
        stats = DiscordMessageStats.objects.create(
            member=self.user,
            channel_id="987654321",
            message_count=10,
        )
        self.assertIn(str(self.user.id), str(stats))
        self.assertIn("987654321", str(stats))

    def test_unique_together_constraint(self):
        """Test unique_together constraint on member and channel_id"""
        from django.db import IntegrityError

        DiscordMessageStats.objects.create(
            member=self.user,
            channel_id="987654321",
            message_count=10,
        )
        with self.assertRaises(IntegrityError):
            DiscordMessageStats.objects.create(
                member=self.user,
                channel_id="987654321",
                message_count=20,
            )

    def test_default_message_count(self):
        """Test default message count is 0"""
        stats = DiscordMessageStats.objects.create(
            member=self.user,
            channel_id="987654321",
        )
        self.assertEqual(stats.message_count, 0)


class AttendanceSessionStatsModelTests(TestCase):
    """Test AttendanceSessionStats model"""

    def setUp(self):
        self.user = User.objects.create(discord_id="123456789", discord_username="test_user")

    def test_attendance_session_stats_creation(self):
        """Test creating attendance session stats"""
        stats = AttendanceSessionStats.objects.create(
            member=self.user,
            sessions_attended=5,
        )
        self.assertEqual(stats.member, self.user)
        self.assertEqual(stats.sessions_attended, 5)

    def test_attendance_session_stats_str_representation(self):
        """Test string representation"""
        stats = AttendanceSessionStats.objects.create(
            member=self.user,
            sessions_attended=5,
        )
        self.assertIn(self.user.username, str(stats))
        self.assertIn("5", str(stats))

    def test_default_sessions_attended(self):
        """Test default sessions_attended is 0"""
        stats = AttendanceSessionStats.objects.create(member=self.user)
        self.assertEqual(stats.sessions_attended, 0)

    def test_last_updated_auto_set(self):
        """Test last_updated is automatically set"""
        stats = AttendanceSessionStats.objects.create(member=self.user)
        self.assertIsNotNone(stats.last_updated)
        self.assertLessEqual(
            (timezone.now() - stats.last_updated).total_seconds(),
            1,
        )


class CohortStatsModelTests(TestCase):
    """Test CohortStats model"""

    def setUp(self):
        self.user = User.objects.create(discord_id="123456789", discord_username="test_user")
        self.cohort = Cohort.objects.create(name="Test Cohort", level="beginner")

    def test_cohort_stats_creation(self):
        """Test creating cohort stats"""
        stats = CohortStats.objects.create(
            member=self.user,
            cohort=self.cohort,
            applications=10,
            onlineAssessments=5,
            interviews=3,
            offers=1,
            dailyChecks=20,
            streak=5,
        )
        self.assertEqual(stats.member, self.user)
        self.assertEqual(stats.cohort, self.cohort)
        self.assertEqual(stats.applications, 10)
        self.assertEqual(stats.onlineAssessments, 5)
        self.assertEqual(stats.interviews, 3)
        self.assertEqual(stats.offers, 1)
        self.assertEqual(stats.dailyChecks, 20)
        self.assertEqual(stats.streak, 5)

    def test_cohort_stats_default_values(self):
        """Test default values for cohort stats"""
        stats = CohortStats.objects.create(
            member=self.user,
            cohort=self.cohort,
        )
        self.assertEqual(stats.applications, 0)
        self.assertEqual(stats.onlineAssessments, 0)
        self.assertEqual(stats.interviews, 0)
        self.assertEqual(stats.offers, 0)
        self.assertEqual(stats.dailyChecks, 0)
        self.assertEqual(stats.streak, 0)

    def test_last_updated_auto_now(self):
        """Test last_updated is automatically updated"""
        stats = CohortStats.objects.create(
            member=self.user,
            cohort=self.cohort,
        )
        original_time = stats.last_updated
        stats.applications = 5
        stats.save()
        self.assertGreaterEqual(stats.last_updated, original_time)


# ============================================================================
# Serializer Tests
# ============================================================================


class AttendeeSerializerTests(TestCase):
    """Test AttendeeSerializer"""

    def setUp(self):
        self.user = User.objects.create(
            username="testuser",
            discord_id="123456789",
            discord_username="test_user",
        )

    def test_attendee_serializer_fields(self):
        """Test serializer contains correct fields"""
        serializer = AttendeeSerializer(self.user)
        self.assertIn("id", serializer.data)
        self.assertIn("username", serializer.data)
        self.assertEqual(len(serializer.data), 2)

    def test_attendee_serializer_data(self):
        """Test serializer data is correct"""
        serializer = AttendeeSerializer(self.user)
        self.assertEqual(serializer.data["id"], self.user.id)
        self.assertEqual(serializer.data["username"], self.user.username)


class AttendanceSessionSerializerTests(TestCase):
    """Test AttendanceSessionSerializer"""

    def setUp(self):
        self.user = User.objects.create(
            username="testuser",
            discord_id="123456789",
            discord_username="test_user",
        )
        self.session = AttendanceSession.objects.create(
            title="Test Session",
            key="test-key",
            expires=timezone.now() + timedelta(hours=1),
        )
        self.session.attendees.add(self.user)

    def test_attendance_session_serializer_fields(self):
        """Test serializer contains all fields"""
        serializer = AttendanceSessionSerializer(self.session)
        self.assertIn("session_id", serializer.data)
        self.assertIn("key", serializer.data)
        self.assertIn("title", serializer.data)
        self.assertIn("expires", serializer.data)
        self.assertIn("attendees", serializer.data)

    def test_attendance_session_serializer_attendees(self):
        """Test attendees are serialized correctly"""
        serializer = AttendanceSessionSerializer(self.session)
        self.assertEqual(len(serializer.data["attendees"]), 1)
        self.assertEqual(serializer.data["attendees"][0]["id"], self.user.id)
        self.assertEqual(serializer.data["attendees"][0]["username"], self.user.username)


class MemberSerializerTests(TestCase):
    """Test MemberSerializer"""

    def setUp(self):
        self.user = User.objects.create(
            username="testuser",
            discord_id="123456789",
            discord_username="test_user",
        )

    def test_member_serializer_fields(self):
        """Test serializer contains only id field"""
        serializer = MemberSerializer(self.user)
        self.assertIn("id", serializer.data)
        self.assertEqual(len(serializer.data), 1)


class AttendanceStatsSerializerTests(TestCase):
    """Test AttendanceStatsSerializer"""

    def setUp(self):
        self.user = User.objects.create(
            username="testuser",
            discord_id="123456789",
            discord_username="test_user",
        )
        self.stats = AttendanceSessionStats.objects.create(
            member=self.user,
            sessions_attended=10,
        )

    def test_attendance_stats_serializer_fields(self):
        """Test serializer contains all fields"""
        # Add rank field as it's expected by serializer
        self.stats.rank = 1
        serializer = AttendanceStatsSerializer(self.stats)
        self.assertIn("member", serializer.data)
        self.assertIn("sessions_attended", serializer.data)
        self.assertIn("rank", serializer.data)

    def test_attendance_stats_serializer_member_nested(self):
        """Test member is serialized with UsernameSerializer"""
        self.stats.rank = 1
        serializer = AttendanceStatsSerializer(self.stats)
        self.assertIn("username", serializer.data["member"])


class CohortStatsSerializerTests(TestCase):
    """Test CohortStatsSerializer"""

    def setUp(self):
        self.user = User.objects.create(
            username="testuser",
            discord_id="123456789",
            discord_username="test_user",
        )
        self.cohort = Cohort.objects.create(name="Test Cohort", level="beginner")
        self.stats = CohortStats.objects.create(
            member=self.user,
            cohort=self.cohort,
            applications=10,
            onlineAssessments=5,
            interviews=3,
            offers=1,
            dailyChecks=20,
            streak=5,
        )

    def test_cohort_stats_serializer_fields(self):
        """Test serializer contains correct fields"""
        serializer = CohortStatsSerializer(self.stats)
        expected_fields = [
            "member",
            "cohort",
            "applications",
            "onlineAssessments",
            "interviews",
            "offers",
            "dailyChecks",
            "streak",
        ]
        for field in expected_fields:
            self.assertIn(field, serializer.data)

    def test_cohort_stats_serializer_nested_objects(self):
        """Test member and cohort are nested serializers"""
        serializer = CohortStatsSerializer(self.stats)
        self.assertIsInstance(serializer.data["member"], dict)
        self.assertIsInstance(serializer.data["cohort"], dict)
        self.assertIn("username", serializer.data["member"])
        self.assertIn("name", serializer.data["cohort"])


class CohortStatsLeaderboardSerializerTests(TestCase):
    """Test CohortStatsLeaderboardSerializer"""

    def setUp(self):
        self.user = User.objects.create(
            username="testuser",
            discord_id="123456789",
            discord_username="test_user",
        )
        self.cohort = Cohort.objects.create(name="Test Cohort", level="beginner")
        self.stats = CohortStats.objects.create(
            member=self.user,
            cohort=self.cohort,
            applications=10,
        )

    def test_cohort_stats_leaderboard_serializer_has_rank(self):
        """Test serializer includes rank field"""
        self.stats.rank = 1
        serializer = CohortStatsLeaderboardSerializer(self.stats)
        self.assertIn("rank", serializer.data)


# ============================================================================
# Buffer Tests
# ============================================================================


class MessageTests(TestCase):
    """Test Message pydantic model"""

    def test_message_creation(self):
        """Test creating a message"""
        message = Message(discord_id=123456789, channel_id=987654321)
        self.assertEqual(message.discord_id, 123456789)
        self.assertEqual(message.channel_id, 987654321)

    def test_message_validation_requires_int(self):
        """Test message validation requires integers"""
        with self.assertRaises((TypeError, ValueError)):
            Message(discord_id="invalid", channel_id=987654321)

    def test_message_validation_requires_all_fields(self):
        """Test message validation requires all fields"""
        with self.assertRaises(TypeError):
            Message(discord_id=123456789)


class MessageBufferTests(TestCase):
    """Test MessageBuffer"""

    def setUp(self):
        self.user = User.objects.create(discord_id=123456789, discord_username="test_user")
        self.buffer = MessageBuffer(batch_size=5, max_size=10, flush_interval=60)

    def test_message_buffer_initialization(self):
        """Test buffer initialization"""
        self.assertEqual(len(self.buffer._buffer), 0)
        self.assertEqual(self.buffer._batch_size, 5)
        self.assertEqual(self.buffer._max_size, 10)
        self.assertEqual(self.buffer._flush_interval, 60)

    def test_add_message_to_buffer(self):
        """Test adding a message to buffer"""
        message = Message(discord_id=123456789, channel_id=987654321)
        self.buffer.add_message(message)
        self.assertEqual(len(self.buffer._buffer), 1)

    def test_buffer_drops_message_when_full(self):
        """Test buffer drops messages when full"""
        for _ in range(15):
            message = Message(discord_id=123456789, channel_id=987654321)
            self.buffer.add_message(message)
        # Buffer should not exceed max_size
        self.assertLessEqual(len(self.buffer._buffer), 10)

    def test_aggregate_messages(self):
        """Test message aggregation"""
        messages = [
            Message(discord_id=123456789, channel_id=111),
            Message(discord_id=123456789, channel_id=111),
            Message(discord_id=987654321, channel_id=111),
            Message(discord_id=123456789, channel_id=222),
        ]
        result = self.buffer._aggregate(messages)
        self.assertEqual(result[111][123456789], 2)
        self.assertEqual(result[111][987654321], 1)
        self.assertEqual(result[222][123456789], 1)

    def test_flush_to_db_creates_stats(self):
        """Test flushing to database creates stats"""
        message = Message(discord_id=self.user.discord_id, channel_id=987654321)
        self.buffer.add_message(message)
        self.buffer.flush_to_db()

        stats = DiscordMessageStats.objects.filter(
            member=self.user,
            channel_id=987654321,
        ).first()
        self.assertIsNotNone(stats)
        self.assertEqual(stats.message_count, 1)

    def test_flush_to_db_updates_existing_stats(self):
        """Test flushing to database updates existing stats"""
        # Create initial stats
        DiscordMessageStats.objects.create(
            member=self.user,
            channel_id=987654321,
            message_count=5,
        )

        # Add messages and flush
        for _ in range(3):
            message = Message(discord_id=self.user.discord_id, channel_id=987654321)
            self.buffer.add_message(message)
        self.buffer.flush_to_db()

        # Check stats were updated
        stats = DiscordMessageStats.objects.get(
            member=self.user,
            channel_id=987654321,
        )
        self.assertEqual(stats.message_count, 8)

    def test_flush_to_db_clears_buffer(self):
        """Test flushing clears the buffer"""
        message = Message(discord_id=self.user.discord_id, channel_id=987654321)
        self.buffer.add_message(message)
        self.assertEqual(len(self.buffer._buffer), 1)
        self.buffer.flush_to_db()
        self.assertEqual(len(self.buffer._buffer), 0)

    def test_flush_to_db_handles_missing_users(self):
        """Test flushing handles messages from non-existent users"""
        message = Message(discord_id=999999999, channel_id=987654321)
        self.buffer.add_message(message)
        # Should not raise exception
        self.buffer.flush_to_db()
        # Stats should not be created for non-existent user
        stats_count = DiscordMessageStats.objects.filter(channel_id=987654321).count()
        self.assertEqual(stats_count, 0)

    def test_flush_to_db_with_empty_buffer(self):
        """Test flushing empty buffer does nothing"""
        self.buffer.flush_to_db()
        # Should not raise exception
        self.assertEqual(len(self.buffer._buffer), 0)


# ============================================================================
# Additional View Tests
# ============================================================================


class InjestMessageEventViewTests(AuthenticatedTestCase):
    """Test InjestMessageEventView"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.user = User.objects.create(discord_id=123456789, discord_username="test_user")

    def test_injest_message_event_success(self):
        """Test successfully injesting a message event"""
        response = self.client.post(
            "/engagement/message/",
            {"discord_id": 123456789, "channel_id": 987654321},
        )
        self.assertResponse(response, 202)

    def test_injest_message_event_invalid_discord_id_type(self):
        """Test injesting with invalid discord_id type"""
        response = self.client.post(
            "/engagement/message/",
            {"discord_id": "invalid", "channel_id": 987654321},
        )
        self.assertResponse(response, 400)
        self.assertIn("error", response.data)

    def test_injest_message_event_invalid_channel_id_type(self):
        """Test injesting with invalid channel_id type"""
        response = self.client.post(
            "/engagement/message/",
            {"discord_id": 123456789, "channel_id": "invalid"},
        )
        self.assertResponse(response, 400)

    def test_injest_message_event_missing_discord_id(self):
        """Test injesting without discord_id"""
        response = self.client.post(
            "/engagement/message/",
            {"channel_id": 987654321},
        )
        self.assertResponse(response, 400)

    def test_injest_message_event_missing_channel_id(self):
        """Test injesting without channel_id"""
        response = self.client.post(
            "/engagement/message/",
            {"discord_id": 123456789},
        )
        self.assertResponse(response, 400)


class GetUserStatsTests(AuthenticatedTestCase):
    """Test GetUserStats view"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.user = User.objects.create(discord_id=123456789, discord_username="test_user")
        # Create required stats
        LeetcodeStats.objects.create(user=self.user, total_solved=100)
        GitHubStats.objects.create(user=self.user, total_commits=50)

    def test_get_user_stats_success(self):
        """Test getting user stats"""
        response = self.client.get(f"/engagement/stats/{self.user.id}/")
        self.assertResponse(response, 200)
        self.assertIn("leetcode", response.data)
        self.assertIn("github", response.data)

    def test_get_user_stats_leetcode_data(self):
        """Test leetcode stats are included"""
        response = self.client.get(f"/engagement/stats/{self.user.id}/")
        self.assertEqual(response.data["leetcode"]["total_solved"], 100)

    def test_get_user_stats_github_data(self):
        """Test github stats are included"""
        response = self.client.get(f"/engagement/stats/{self.user.id}/")
        self.assertEqual(response.data["github"]["total_commits"], 50)

    def test_get_user_stats_nonexistent_user(self):
        """Test getting stats for non-existent user"""
        response = self.client.get("/engagement/stats/99999/")
        self.assertResponse(response, 404)


class QueryDiscordMessageStatsTests(AuthenticatedTestCase):
    """Test QueryDiscordMessageStats view"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.user1 = User.objects.create(discord_id=111, discord_username="user1")
        self.user2 = User.objects.create(discord_id=222, discord_username="user2")
        DiscordMessageStats.objects.create(member=self.user1, channel_id=100, message_count=10)
        DiscordMessageStats.objects.create(member=self.user1, channel_id=200, message_count=20)
        DiscordMessageStats.objects.create(member=self.user2, channel_id=100, message_count=5)

    def test_query_all_message_stats(self):
        """Test querying all message stats"""
        response = self.client.get("/engagement/discord-stats/")
        self.assertResponse(response, 200)
        self.assertEqual(len(response.data), 2)  # 2 users

    def test_query_message_stats_by_member_id(self):
        """Test querying by member_id"""
        response = self.client.get(f"/engagement/discord-stats/?member_id={self.user1.id}")
        self.assertResponse(response, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["member"]["id"], self.user1.id)

    def test_query_message_stats_by_channel_id(self):
        """Test querying by channel_id"""
        response = self.client.get("/engagement/discord-stats/?channel_id=100")
        self.assertResponse(response, 200)
        # Should return both users who have messages in channel 100
        self.assertEqual(len(response.data), 2)

    def test_query_message_stats_by_member_and_channel(self):
        """Test querying by both member_id and channel_id"""
        response = self.client.get(
            f"/engagement/discord-stats/?member_id={self.user1.id}&channel_id=100"
        )
        self.assertResponse(response, 200)
        self.assertEqual(len(response.data), 1)

    def test_query_message_stats_aggregation(self):
        """Test stats are properly aggregated"""
        response = self.client.get(f"/engagement/discord-stats/?member_id={self.user1.id}")
        self.assertResponse(response, 200)
        stats = response.data[0]["stats"]
        self.assertIn("100", stats)
        self.assertIn("200", stats)
        self.assertEqual(stats["100"], 10)
        self.assertEqual(stats["200"], 20)


class CohortStatsUpdateViewsTests(AuthenticatedTestCase):
    """Test CohortStats update views"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.user = User.objects.create(discord_id=123456789, discord_username="test_user")
        self.cohort = Cohort.objects.create(name="Test Cohort", level="beginner", is_active=True)
        self.stats = CohortStats.objects.create(
            member=self.user,
            cohort=self.cohort,
        )

    def test_update_application_stats(self):
        """Test updating application stats"""
        response = self.client.put(
            "/engagement/cohort-stats/applications/",
            {"discord_id": 123456789},
        )
        self.assertResponse(response, 200)
        self.stats.refresh_from_db()
        self.assertEqual(self.stats.applications, 1)

    def test_update_application_stats_with_cohort_name(self):
        """Test updating application stats with specific cohort"""
        response = self.client.put(
            "/engagement/cohort-stats/applications/",
            {"discord_id": 123456789, "cohort_name": "Test Cohort"},
        )
        self.assertResponse(response, 200)
        self.stats.refresh_from_db()
        self.assertEqual(self.stats.applications, 1)

    def test_update_oa_stats(self):
        """Test updating online assessment stats"""
        response = self.client.put(
            "/engagement/cohort-stats/oa/",
            {"discord_id": 123456789},
        )
        self.assertResponse(response, 200)
        self.stats.refresh_from_db()
        self.assertEqual(self.stats.onlineAssessments, 1)

    def test_update_interview_stats(self):
        """Test updating interview stats"""
        response = self.client.put(
            "/engagement/cohort-stats/interviews/",
            {"discord_id": 123456789},
        )
        self.assertResponse(response, 200)
        self.stats.refresh_from_db()
        self.assertEqual(self.stats.interviews, 1)

    def test_update_offers_stats(self):
        """Test updating offers stats"""
        response = self.client.put(
            "/engagement/cohort-stats/offers/",
            {"discord_id": 123456789},
        )
        self.assertResponse(response, 200)
        self.stats.refresh_from_db()
        self.assertEqual(self.stats.offers, 1)

    def test_update_daily_checks_first_time(self):
        """Test updating daily checks for the first time"""
        response = self.client.put(
            "/engagement/cohort-stats/daily-checks/",
            {"discord_id": 123456789},
        )
        self.assertResponse(response, 200)
        self.stats.refresh_from_db()
        self.assertEqual(self.stats.dailyChecks, 1)
        self.assertEqual(self.stats.streak, 1)

    def test_update_daily_checks_same_day_no_increment(self):
        """Test updating daily checks on same day doesn't increment"""
        # First update
        self.client.put(
            "/engagement/cohort-stats/daily-checks/",
            {"discord_id": 123456789},
        )
        # Second update on same day
        response = self.client.put(
            "/engagement/cohort-stats/daily-checks/",
            {"discord_id": 123456789},
        )
        self.assertResponse(response, 200)
        self.stats.refresh_from_db()
        # Should still be 1
        self.assertEqual(self.stats.dailyChecks, 1)

    def test_update_stats_missing_discord_id(self):
        """Test updating stats without discord_id"""
        response = self.client.put(
            "/engagement/cohort-stats/applications/",
            {},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())

    def test_update_stats_nonexistent_user(self):
        """Test updating stats for non-existent user"""
        response = self.client.put(
            "/engagement/cohort-stats/applications/",
            {"discord_id": 999999999},
        )
        self.assertEqual(response.status_code, 400)

    def test_update_stats_no_active_cohort(self):
        """Test updating stats when user has no active cohort"""
        user2 = User.objects.create(discord_id=987654321, discord_username="user2")
        response = self.client.put(
            "/engagement/cohort-stats/applications/",
            {"discord_id": 987654321},
        )
        self.assertEqual(response.status_code, 404)

    def test_update_stats_inactive_cohort_not_updated(self):
        """Test that inactive cohorts are not updated"""
        self.cohort.is_active = False
        self.cohort.save()
        response = self.client.put(
            "/engagement/cohort-stats/applications/",
            {"discord_id": 123456789},
        )
        self.assertEqual(response.status_code, 404)

    def test_update_stats_nonexistent_cohort_name(self):
        """Test updating stats with non-existent cohort name"""
        response = self.client.put(
            "/engagement/cohort-stats/applications/",
            {"discord_id": 123456789, "cohort_name": "Nonexistent Cohort"},
        )
        self.assertEqual(response.status_code, 404)

    def test_update_stats_increments_correctly(self):
        """Test that stats increment correctly on multiple updates"""
        for _ in range(5):
            self.client.put(
                "/engagement/cohort-stats/applications/",
                {"discord_id": 123456789},
            )
        self.stats.refresh_from_db()
        self.assertEqual(self.stats.applications, 5)


class EdgeCaseTests(AuthenticatedTestCase):
    """Test edge cases and error conditions"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def test_attend_session_duplicate_attendance(self):
        """Test attending same session twice"""
        user = User.objects.create(discord_id="123456789", discord_username="test_user")
        session = AttendanceSession.objects.create(
            title="Test Session",
            key="test-key",
            expires=timezone.now() + timedelta(hours=1),
        )
        # First attendance
        response1 = self.client.post(
            "/engagement/attendance/attend",
            {"session_key": "test-key", "discord_id": "123456789"},
        )
        self.assertResponse(response1, 201)

        # Second attendance (duplicate)
        response2 = self.client.post(
            "/engagement/attendance/attend",
            {"session_key": "test-key", "discord_id": "123456789"},
        )
        self.assertResponse(response2, 400)
        self.assertIn("already in session", response2.data["error"])

    def test_create_session_invalid_date_format(self):
        """Test creating session with invalid date format"""
        response = self.client.post(
            "/engagement/attendance/session",
            {
                "title": "Test Session",
                "key": "test-key",
                "expires": "invalid-date",
            },
        )
        self.assertResponse(response, 400)

    def test_create_session_missing_required_fields(self):
        """Test creating session without required fields"""
        response = self.client.post(
            "/engagement/attendance/session",
            {"title": "Test Session"},
        )
        self.assertResponse(response, 400)

    def test_get_session_attendees_empty_session(self):
        """Test getting attendees for session with no attendees"""
        session = AttendanceSession.objects.create(
            title="Empty Session",
            key="empty-key",
            expires=timezone.now() + timedelta(hours=1),
        )
        response = self.client.get(f"/engagement/attendance/session/{session.session_id}/")
        self.assertResponse(response, 200)
        self.assertEqual(len(response.data), 0)

    def test_get_member_sessions_no_sessions(self):
        """Test getting sessions for member with no attendance"""
        user = User.objects.create(discord_id="123456789", discord_username="test_user")
        response = self.client.get(f"/engagement/attendance/member/{user.id}/")
        self.assertResponse(response, 200)
        self.assertEqual(len(response.data), 0)

    def test_attendance_session_stats_auto_increment(self):
        """Test that attendance stats auto-increment when attending"""
        user = User.objects.create(discord_id="123456789", discord_username="test_user")
        session = AttendanceSession.objects.create(
            title="Test Session",
            key="test-key",
            expires=timezone.now() + timedelta(hours=1),
        )

        # Attend session
        self.client.post(
            "/engagement/attendance/attend",
            {"session_key": "test-key", "discord_id": "123456789"},
        )

        # Check stats were created/updated
        stats = AttendanceSessionStats.objects.get(member=user)
        self.assertEqual(stats.sessions_attended, 1)
