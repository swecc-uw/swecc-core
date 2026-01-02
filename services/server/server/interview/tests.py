import random
from datetime import timedelta
from unittest.mock import MagicMock, patch

import numpy as np
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from interview.algorithm import CommonAvailabilityStableMatching
from interview.models import Interview, InterviewAvailability, InterviewPool, validate_availability
from interview.notification import (
    interview_paired_notification_html,
    interview_unpaired_notification_html,
)
from interview.serializers import (
    AvailabilitySerializer,
    InterviewAndQuestionSerializer,
    InterviewMemberSerializer,
    InterviewPoolSerializer,
    InterviewSerializer,
)
from interview.views import get_next_cutoff, get_previous_cutoff, is_valid_availability
from members.models import User
from questions.models import (
    BehavioralQuestion,
    QuestionTopic,
    TechnicalQuestion,
    TechnicalQuestionQueue,
)
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

# ============================================================================
# MODEL TESTS
# ============================================================================


class InterviewAvailabilityModelTests(TestCase):
    """Test InterviewAvailability model"""

    def setUp(self):
        self.user = User.objects.create(
            username="testuser", discord_id="123456789", discord_username="test_user"
        )

    def test_create_interview_availability(self):
        """Test creating interview availability with default values"""
        availability = InterviewAvailability.objects.create(member=self.user)

        self.assertEqual(availability.member, self.user)
        self.assertEqual(len(availability.interview_availability_slots), 7)
        self.assertEqual(len(availability.interview_availability_slots[0]), 48)
        self.assertEqual(len(availability.mentor_availability_slots), 7)
        self.assertEqual(len(availability.mentor_availability_slots[0]), 48)

    def test_set_interview_availability_valid(self):
        """Test setting valid interview availability"""
        availability = InterviewAvailability.objects.create(member=self.user)
        new_availability = [[True] * 48 for _ in range(7)]

        availability.set_interview_availability(new_availability)

        self.assertEqual(availability.interview_availability_slots, new_availability)

    def test_set_mentor_availability_valid(self):
        """Test setting valid mentor availability"""
        availability = InterviewAvailability.objects.create(member=self.user)
        new_availability = [[True] * 48 for _ in range(7)]

        availability.set_mentor_availability(new_availability)

        self.assertEqual(availability.mentor_availability_slots, new_availability)

    def test_validate_availability_invalid_days(self):
        """Test validation fails with wrong number of days"""
        with self.assertRaises(ValidationError):
            validate_availability([[True] * 48 for _ in range(6)])

    def test_validate_availability_invalid_slots(self):
        """Test validation fails with wrong number of slots"""
        with self.assertRaises(ValidationError):
            validate_availability([[True] * 47 for _ in range(7)])

    def test_validate_availability_invalid_type(self):
        """Test validation fails with non-boolean values"""
        with self.assertRaises(ValidationError):
            validate_availability([[1] * 48 for _ in range(7)])

    def test_validate_availability_not_list(self):
        """Test validation fails when not a list"""
        with self.assertRaises(ValidationError):
            validate_availability("not a list")

    def test_str_representation(self):
        """Test string representation"""
        availability = InterviewAvailability.objects.create(member=self.user)
        self.assertEqual(str(availability), f"Availability for {self.user}")


class InterviewPoolModelTests(TestCase):
    """Test InterviewPool model"""

    def setUp(self):
        self.user = User.objects.create(
            username="testuser", discord_id="123456789", discord_username="test_user"
        )

    def test_create_interview_pool(self):
        """Test creating interview pool entry"""
        pool_entry = InterviewPool.objects.create(member=self.user)

        self.assertEqual(pool_entry.member, self.user)
        self.assertIsNotNone(pool_entry.timestamp)

    def test_str_representation(self):
        """Test string representation"""
        pool_entry = InterviewPool.objects.create(member=self.user)
        self.assertEqual(str(pool_entry), f"Interview Pool: {self.user}")

    def test_one_to_one_constraint(self):
        """Test that a user can only have one pool entry"""
        from django.db import IntegrityError

        InterviewPool.objects.create(member=self.user)
        with self.assertRaises(IntegrityError):
            InterviewPool.objects.create(member=self.user)


class InterviewModelTests(TestCase):
    """Test Interview model"""

    def setUp(self):
        self.user1 = User.objects.create(
            username="interviewer", discord_id="111111111", discord_username="interviewer_user"
        )
        self.user2 = User.objects.create(
            username="interviewee", discord_id="222222222", discord_username="interviewee_user"
        )
        self.topic = QuestionTopic.objects.create(name="Arrays", created_by=self.user1)
        self.tech_question = TechnicalQuestion.objects.create(
            title="Two Sum",
            created_by=self.user1,
            topic=self.topic,
            prompt="Find two numbers that add up to target",
            solution="Use hash map",
        )
        self.behavioral_question = BehavioralQuestion.objects.create(
            created_by=self.user1,
            prompt="Tell me about a time...",
            solution="Use STAR method",
        )

    def test_create_interview(self):
        """Test creating an interview"""
        interview = Interview.objects.create(
            interviewer=self.user1,
            interviewee=self.user2,
            status="pending",
            date_effective=timezone.now(),
        )

        self.assertIsNotNone(interview.interview_id)
        self.assertEqual(interview.interviewer, self.user1)
        self.assertEqual(interview.interviewee, self.user2)
        self.assertEqual(interview.status, "pending")

    def test_interview_status_choices(self):
        """Test all valid status choices"""
        statuses = [
            "pending",
            "active",
            "inactive_unconfirmed",
            "inactive_completed",
            "inactive_incomplete",
        ]

        for status_choice in statuses:
            interview = Interview.objects.create(
                interviewer=self.user1,
                interviewee=self.user2,
                status=status_choice,
                date_effective=timezone.now(),
            )
            self.assertEqual(interview.status, status_choice)

    def test_add_technical_questions(self):
        """Test adding technical questions to interview"""
        interview = Interview.objects.create(
            interviewer=self.user1,
            interviewee=self.user2,
            status="pending",
            date_effective=timezone.now(),
        )
        interview.technical_questions.add(self.tech_question)

        self.assertEqual(interview.technical_questions.count(), 1)
        self.assertIn(self.tech_question, interview.technical_questions.all())

    def test_add_behavioral_questions(self):
        """Test adding behavioral questions to interview"""
        interview = Interview.objects.create(
            interviewer=self.user1,
            interviewee=self.user2,
            status="pending",
            date_effective=timezone.now(),
        )
        interview.behavioral_questions.add(self.behavioral_question)

        self.assertEqual(interview.behavioral_questions.count(), 1)
        self.assertIn(self.behavioral_question, interview.behavioral_questions.all())

    def test_str_representation(self):
        """Test string representation"""
        interview = Interview.objects.create(
            interviewer=self.user1,
            interviewee=self.user2,
            status="pending",
            date_effective=timezone.now(),
        )
        expected = f"Interview {interview.interview_id}: {self.user1} - {self.user2}"
        self.assertEqual(str(interview), expected)

    def test_proposed_time_and_by(self):
        """Test proposed time and proposed by fields"""
        proposed_time = timezone.now() + timedelta(days=1)
        interview = Interview.objects.create(
            interviewer=self.user1,
            interviewee=self.user2,
            status="pending",
            date_effective=timezone.now(),
            proposed_time=proposed_time,
            proposed_by=self.user1,
        )

        self.assertEqual(interview.proposed_time, proposed_time)
        self.assertEqual(interview.proposed_by, self.user1)

    def test_committed_time(self):
        """Test committed time field"""
        committed_time = timezone.now() + timedelta(days=2)
        interview = Interview.objects.create(
            interviewer=self.user1,
            interviewee=self.user2,
            status="active",
            date_effective=timezone.now(),
            committed_time=committed_time,
        )

        self.assertEqual(interview.committed_time, committed_time)


# ============================================================================
# ALGORITHM TESTS (EXISTING + ADDITIONAL)
# ============================================================================


class TestCommonAvailabilityStableMatching(TestCase):
    def setUp(self):
        self.algorithm = CommonAvailabilityStableMatching()

    def test_calculate_common_slots_numpy(self):
        availability1 = np.array([[False] * 48 for _ in range(7)], dtype=bool)
        availability2 = np.array([[False] * 48 for _ in range(7)], dtype=bool)
        self.assertEqual(
            self.algorithm.calculate_common_slots_numpy(availability1, availability2), 0
        )

        availability1 = np.array([[True] * 48 for _ in range(7)], dtype=bool)
        availability2 = np.array([[True] * 48 for _ in range(7)], dtype=bool)
        self.assertEqual(
            self.algorithm.calculate_common_slots_numpy(availability1, availability2),
            7 * 48,
        )

        availability1 = np.array([([True] * 24) + ([False] * 24) for _ in range(7)], dtype=bool)
        availability2 = np.array([([True] * 12) + ([False] * 36) for _ in range(7)], dtype=bool)
        self.assertEqual(
            self.algorithm.calculate_common_slots_numpy(availability1, availability2),
            7 * 12,
        )

        availability1 = np.array([[True] * 48 for _ in range(7)], dtype=bool)
        availability2 = np.array([[True] * 48 for _ in range(6)] + [[False] * 48], dtype=bool)
        self.assertEqual(
            self.algorithm.calculate_common_slots_numpy(availability1, availability2),
            6 * 48,
        )

    def test_stable_matching_two_members(self):
        availabilities = {
            0: [[True] * 48 for _ in range(7)],
            1: [[True] * 48 for _ in range(7)],
        }
        self.algorithm.set_availabilities(availabilities)
        result = self.algorithm.pair([0, 1])
        self.assertEqual(result.pairs, [1, 0])

        with self.assertRaises(ValueError):
            self.algorithm.pair([0])

    def test_large_input(self):
        num_members = 200
        pool_member_ids = list(range(num_members))
        availabilities = {
            i: [[random.choice([True, False]) for __ in range(48)] for _ in range(7)]
            for i in pool_member_ids
        }
        start_time = timezone.now()
        self.algorithm.set_availabilities(availabilities)
        result = self.algorithm.pair(pool_member_ids)
        end_time = timezone.now()
        duration = (end_time - start_time).total_seconds() * 1000
        print(f"Time taken for pairing with {num_members} members: {duration:.2f} ms")

        self.assertEqual(len(result.pairs), num_members)

    def test_perfect_matching(self):
        availabilities = {
            0: [[True] * 24 + [False] * 24 for _ in range(7)],
            1: [[False] * 24 + [True] * 24 for _ in range(7)],
            2: [[True] * 24 + [False] * 24 for _ in range(7)],
            3: [[False] * 24 + [True] * 24 for _ in range(7)],
        }
        pool_member_ids = list(availabilities.keys())
        self.algorithm.set_availabilities(availabilities)
        result = self.algorithm.pair(pool_member_ids)
        self.assertEqual(result.pairs, [2, 3, 0, 1])

    def test_predictable_cases(self):
        availabilities = {
            0: [[True] * 48 for _ in range(7)],
            1: [[True] * 48 for _ in range(7)],
            2: [[False] * 48 for _ in range(7)],
            3: [[True] * 48 for _ in range(7)],
        }
        pool_member_ids = list(availabilities.keys())
        possible_expected_matchings = [[1, 0, 3, 2], [3, 2, 1, 0], [2, 3, 0, 1]]
        self.algorithm.set_availabilities(availabilities)
        result = self.algorithm.pair(pool_member_ids)
        self.assertIn(result.pairs, possible_expected_matchings)

    def test_calculate_preferences(self):
        pool_member_ids = [0, 1, 2]
        availabilities = {
            0: [[True] * 48 for _ in range(7)],
            1: [[True] * 48 for _ in range(7)],
            2: [[False] * 48 for _ in range(7)],
        }
        expected_preferences_rankings = {0: [1, 2], 1: [0, 2], 2: [0, 1]}

        prefs = self.algorithm.calculate_preferences(pool_member_ids, availabilities)

        for member, expected_rankings in expected_preferences_rankings.items():
            calculated_rankings = [other_member for other_member, _ in prefs[member]]
            self.assertEqual(calculated_rankings, expected_rankings)

    def _pair_large_input_calculate_preferences(self, num_members=200):
        pool_member_ids = list(range(num_members))
        availabilities = {
            i: [[random.choice([True, False]) for __ in range(48)] for _ in range(7)]
            for i in pool_member_ids
        }
        start_time = timezone.now()
        prefs = self.algorithm.calculate_preferences(pool_member_ids, availabilities)
        pairs = self.algorithm.pair(pool_member_ids)
        end_time = timezone.now()
        duration = (end_time - start_time).total_seconds() * 1000
        print(f"Time taken for pairing {num_members} members: {duration:.2f} ms")
        self.assertEqual(len(prefs), num_members)
        self.assertEqual(len(pairs.pairs), num_members)

    def test_trend_in_clock_time(self):

        for num_members in [10, 20, 50, 100, 200, 500, 1000, 2000]:
            self._pair_large_input_calculate_preferences(num_members)

    def test_set_availabilities_empty(self):
        """Test that setting empty availabilities raises error"""
        with self.assertRaises(ValueError):
            self.algorithm.set_availabilities({})

    def test_pair_without_availabilities(self):
        """Test pairing without setting availabilities raises error"""
        with self.assertRaises(ValueError):
            self.algorithm.pair([0, 1])

    def test_pair_with_missing_availability(self):
        """Test pairing when some members don't have availability"""
        availabilities = {
            0: [[True] * 48 for _ in range(7)],
        }
        self.algorithm.set_availabilities(availabilities)
        with self.assertRaises(ValueError):
            self.algorithm.pair([0, 1])

    def test_pair_with_duplicate_ids(self):
        """Test pairing with duplicate member IDs raises error"""
        availabilities = {
            0: [[True] * 48 for _ in range(7)],
            1: [[True] * 48 for _ in range(7)],
        }
        self.algorithm.set_availabilities(availabilities)
        with self.assertRaises(ValueError):
            self.algorithm.pair([0, 0])

    def test_pair_empty_list(self):
        """Test pairing with empty list raises error"""
        availabilities = {
            0: [[True] * 48 for _ in range(7)],
        }
        self.algorithm.set_availabilities(availabilities)
        with self.assertRaises(ValueError):
            self.algorithm.pair([])

    def test_matching_result_structure(self):
        """Test that matching result has correct structure"""
        availabilities = {
            0: [[True] * 48 for _ in range(7)],
            1: [[True] * 48 for _ in range(7)],
        }
        self.algorithm.set_availabilities(availabilities)
        result = self.algorithm.pair([0, 1])

        self.assertIsNotNone(result.pairs)
        self.assertIsNotNone(result.common_slots)
        self.assertIsNotNone(result.preference_scores)


# ============================================================================
# SERIALIZER TESTS
# ============================================================================


class InterviewSerializerTests(TestCase):
    """Test InterviewSerializer"""

    def setUp(self):
        self.user1 = User.objects.create(
            username="interviewer", discord_id="111111111", discord_username="interviewer_user"
        )
        self.user2 = User.objects.create(
            username="interviewee", discord_id="222222222", discord_username="interviewee_user"
        )

    def test_serialize_interview(self):
        """Test serializing an interview"""
        interview = Interview.objects.create(
            interviewer=self.user1,
            interviewee=self.user2,
            status="pending",
            date_effective=timezone.now(),
        )

        serializer = InterviewSerializer(interview)
        data = serializer.data

        self.assertEqual(str(data["interview_id"]), str(interview.interview_id))
        self.assertEqual(data["interviewer"], self.user1.id)
        self.assertEqual(data["interviewee"], self.user2.id)
        self.assertEqual(data["status"], "pending")


class InterviewPoolSerializerTests(TestCase):
    """Test InterviewPoolSerializer"""

    def setUp(self):
        self.user = User.objects.create(
            username="testuser", discord_id="123456789", discord_username="test_user"
        )

    def test_serialize_interview_pool(self):
        """Test serializing interview pool entry"""
        pool_entry = InterviewPool.objects.create(member=self.user)

        serializer = InterviewPoolSerializer(pool_entry)
        data = serializer.data

        self.assertEqual(data["member"], self.user.id)
        self.assertIn("timestamp", data)


class InterviewAndQuestionSerializerTests(TestCase):
    """Test InterviewAndQuestionSerializer"""

    def setUp(self):
        self.user1 = User.objects.create(
            username="interviewer", discord_id="111111111", discord_username="interviewer_user"
        )
        self.user2 = User.objects.create(
            username="interviewee", discord_id="222222222", discord_username="interviewee_user"
        )
        self.topic = QuestionTopic.objects.create(name="Arrays", created_by=self.user1)
        self.tech_question = TechnicalQuestion.objects.create(
            title="Two Sum",
            created_by=self.user1,
            topic=self.topic,
            prompt="Find two numbers",
            solution="Use hash map",
        )
        self.behavioral_question = BehavioralQuestion.objects.create(
            created_by=self.user1,
            prompt="Tell me about a time...",
            solution="Use STAR method",
        )

    def test_serialize_interview_with_questions(self):
        """Test serializing interview with questions"""
        interview = Interview.objects.create(
            interviewer=self.user1,
            interviewee=self.user2,
            status="pending",
            date_effective=timezone.now(),
        )
        interview.technical_questions.add(self.tech_question)
        interview.behavioral_questions.add(self.behavioral_question)

        serializer = InterviewAndQuestionSerializer(interview)
        data = serializer.data

        self.assertEqual(len(data["technical_questions"]), 1)
        self.assertEqual(len(data["behavioral_questions"]), 1)
        self.assertEqual(data["technical_questions"][0]["title"], "Two Sum")


class InterviewMemberSerializerTests(TestCase):
    """Test InterviewMemberSerializer"""

    def setUp(self):
        self.user1 = User.objects.create(
            username="interviewer",
            discord_id="111111111",
            discord_username="interviewer_user",
            email="interviewer@test.com",
        )
        self.user2 = User.objects.create(
            username="interviewee",
            discord_id="222222222",
            discord_username="interviewee_user",
            email="interviewee@test.com",
        )

    def test_serialize_interview_with_member_details(self):
        """Test serializing interview with full member details"""
        interview = Interview.objects.create(
            interviewer=self.user1,
            interviewee=self.user2,
            status="pending",
            date_effective=timezone.now(),
        )

        serializer = InterviewMemberSerializer(interview)
        data = serializer.data

        self.assertIn("interviewer", data)
        self.assertIn("interviewee", data)
        self.assertEqual(data["interviewer"]["username"], "interviewer")
        self.assertEqual(data["interviewee"]["username"], "interviewee")


# ============================================================================
# NOTIFICATION TESTS
# ============================================================================


class NotificationTests(TestCase):
    """Test notification HTML generation"""

    def test_interview_paired_notification_html(self):
        """Test paired notification HTML generation"""
        html = interview_paired_notification_html(
            name="John",
            partner_name="Jane",
            partner_email="jane@test.com",
            partner_discord_id="123456789",
            partner_discord_username="jane_discord",
            interview_date=timezone.now(),
        )

        self.assertIn("John", html)
        self.assertIn("Jane", html)
        self.assertIn("jane@test.com", html)
        self.assertIn("jane_discord", html)
        self.assertIn("123456789", html)
        self.assertIn("<!DOCTYPE html>", html)

    def test_interview_unpaired_notification_html(self):
        """Test unpaired notification HTML generation"""
        html = interview_unpaired_notification_html(
            name="John",
            interview_date="January 15, 2024",
        )

        self.assertIn("John", html)
        self.assertIn("January 15, 2024", html)
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("weren't able to find you a mock interview partner", html)


# ============================================================================
# VIEW HELPER FUNCTION TESTS
# ============================================================================


class ViewHelperTests(TestCase):
    """Test view helper functions"""

    def test_is_valid_availability_valid(self):
        """Test valid availability format"""
        availability = [True] * 48
        self.assertTrue(is_valid_availability(availability))

    def test_is_valid_availability_invalid_length(self):
        """Test invalid availability length"""
        availability = [True] * 47
        self.assertFalse(is_valid_availability(availability))

    def test_is_valid_availability_invalid_type(self):
        """Test invalid availability type"""
        availability = [1] * 48
        self.assertFalse(is_valid_availability(availability))

    def test_is_valid_availability_not_list(self):
        """Test non-list availability"""
        self.assertFalse(is_valid_availability("not a list"))

    @patch("interview.views.django_now")
    def test_get_next_cutoff(self, mock_now):
        """Test get_next_cutoff function"""
        # Mock a Wednesday at 10 AM
        mock_now.return_value = timezone.datetime(2024, 1, 10, 10, 0, 0, tzinfo=timezone.utc)

        cutoff = get_next_cutoff()
        self.assertIsNotNone(cutoff)
        # Should be the previous Sunday at 11 PM
        self.assertEqual(cutoff.weekday(), 6)  # Sunday
        self.assertEqual(cutoff.hour, 23)

    @patch("interview.views.django_now")
    def test_get_next_cutoff_force_current_week(self, mock_now):
        """Test get_next_cutoff with force_current_week"""
        mock_now.return_value = timezone.datetime(2024, 1, 10, 10, 0, 0, tzinfo=timezone.utc)

        cutoff = get_next_cutoff(force_current_week=True)
        self.assertIsNotNone(cutoff)

    @patch("interview.views.django_now")
    def test_get_previous_cutoff(self, mock_now):
        """Test get_previous_cutoff function"""
        mock_now.return_value = timezone.datetime(2024, 1, 10, 10, 0, 0, tzinfo=timezone.utc)

        cutoff = get_previous_cutoff()
        self.assertIsNotNone(cutoff)
        self.assertEqual(cutoff.weekday(), 6)  # Sunday
        self.assertEqual(cutoff.hour, 23)


# ============================================================================
# API VIEW TESTS
# ============================================================================


class AuthenticatedTestCase(APITestCase):
    """Base test case with authentication mocking"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()

        # Create verified group
        self.verified_group = Group.objects.create(name="is_verified")
        self.admin_group = Group.objects.create(name="is_admin")

        # Create test users
        self.user = User.objects.create(
            username="testuser",
            discord_id="123456789",
            discord_username="test_user",
            email="test@example.com",
            first_name="Test",
        )
        self.user.groups.add(self.verified_group)

        self.admin_user = User.objects.create(
            username="adminuser",
            discord_id="987654321",
            discord_username="admin_user",
            email="admin@example.com",
            first_name="Admin",
        )
        self.admin_user.groups.add(self.verified_group, self.admin_group)

        # Create additional test users
        self.user2 = User.objects.create(
            username="testuser2",
            discord_id="111222333",
            discord_username="test_user2",
            email="test2@example.com",
            first_name="Test2",
        )
        self.user2.groups.add(self.verified_group)

        # Mock permissions
        self.verified_patcher = patch("custom_auth.permissions.IsVerified.has_permission")
        self.admin_patcher = patch("custom_auth.permissions.IsAdmin.has_permission")

        self.mock_verified = self.verified_patcher.start()
        self.mock_admin = self.admin_patcher.start()

        self.mock_verified.return_value = True
        self.mock_admin.return_value = True

    def tearDown(self):
        super().tearDown()
        self.verified_patcher.stop()
        self.admin_patcher.stop()


class AuthenticatedMemberSignupForInterviewTests(AuthenticatedTestCase):
    """Test AuthenticatedMemberSignupForInterview view"""

    def test_get_not_signed_up(self):
        """Test GET when user is not signed up"""
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/interview/signup/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["sign_up"])

    def test_get_signed_up(self):
        """Test GET when user is signed up"""
        InterviewPool.objects.create(member=self.user)
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/interview/signup/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["sign_up"])

    def test_post_signup_new(self):
        """Test POST to sign up new user"""
        self.client.force_authenticate(user=self.user)
        availability = [[True] * 48 for _ in range(7)]
        response = self.client.post("/interview/signup/", {"availability": availability})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(InterviewPool.objects.filter(member=self.user).exists())

    def test_post_signup_existing(self):
        """Test POST to update existing signup"""
        InterviewPool.objects.create(member=self.user)
        self.client.force_authenticate(user=self.user)
        availability = [[True] * 48 for _ in range(7)]
        response = self.client.post("/interview/signup/", {"availability": availability})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_post_signup_invalid_availability(self):
        """Test POST with invalid availability"""
        self.client.force_authenticate(user=self.user)
        availability = [[True] * 47 for _ in range(7)]  # Invalid length
        response = self.client.post("/interview/signup/", {"availability": availability})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_delete_signup(self):
        """Test DELETE to cancel signup"""
        InterviewPool.objects.create(member=self.user)
        self.client.force_authenticate(user=self.user)
        response = self.client.delete("/interview/signup/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(InterviewPool.objects.filter(member=self.user).exists())

    def test_delete_not_signed_up(self):
        """Test DELETE when not signed up"""
        self.client.force_authenticate(user=self.user)
        response = self.client.delete("/interview/signup/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class GetInterviewPoolStatusTests(AuthenticatedTestCase):
    """Test GetInterviewPoolStatus view"""

    def test_get_pool_status_empty(self):
        """Test getting pool status when empty"""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get("/interview/pool/status/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["number_sign_up"], 0)

    def test_get_pool_status_with_members(self):
        """Test getting pool status with members"""
        InterviewPool.objects.create(member=self.user)
        InterviewPool.objects.create(member=self.user2)

        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get("/interview/pool/status/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(response.data["number_sign_up"], 0)


class InterviewAvailabilityViewTests(AuthenticatedTestCase):
    """Test InterviewAvailabilityView"""

    def test_get_availability_exists(self):
        """Test GET when availability exists"""
        availability = [[True] * 48 for _ in range(7)]
        InterviewAvailability.objects.create(
            member=self.user, interview_availability_slots=availability
        )

        self.client.force_authenticate(user=self.user)
        response = self.client.get("/interview/availability/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.user.id)
        self.assertEqual(len(response.data["availability"]), 7)

    def test_get_availability_not_exists(self):
        """Test GET when availability doesn't exist"""
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/interview/availability/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_post_availability_update(self):
        """Test POST to update availability"""
        InterviewAvailability.objects.create(member=self.user)
        new_availability = [[True] * 48 for _ in range(7)]

        self.client.force_authenticate(user=self.user)
        response = self.client.post("/interview/availability/", {"availability": new_availability})

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_post_availability_invalid(self):
        """Test POST with invalid availability"""
        InterviewAvailability.objects.create(member=self.user)
        invalid_availability = [[True] * 47 for _ in range(7)]

        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            "/interview/availability/", {"availability": invalid_availability}
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class MemberInterviewsViewTests(AuthenticatedTestCase):
    """Test MemberInterviewsView"""

    def setUp(self):
        super().setUp()
        self.topic = QuestionTopic.objects.create(name="Arrays", created_by=self.admin_user)
        self.tech_question = TechnicalQuestion.objects.create(
            title="Two Sum",
            created_by=self.admin_user,
            topic=self.topic,
            prompt="Find two numbers",
            solution="Use hash map",
        )

    def test_get_member_interviews_as_interviewer(self):
        """Test getting interviews where user is interviewer"""
        Interview.objects.create(
            interviewer=self.user,
            interviewee=self.user2,
            status="pending",
            date_effective=timezone.now(),
        )

        self.client.force_authenticate(user=self.user)
        response = self.client.get("/interview/member/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_member_interviews_as_interviewee(self):
        """Test getting interviews where user is interviewee"""
        Interview.objects.create(
            interviewer=self.user2,
            interviewee=self.user,
            status="pending",
            date_effective=timezone.now(),
        )

        self.client.force_authenticate(user=self.user)
        response = self.client.get("/interview/member/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)


class InterviewDetailViewTests(AuthenticatedTestCase):
    """Test InterviewDetailView"""

    def setUp(self):
        super().setUp()
        self.interview = Interview.objects.create(
            interviewer=self.user,
            interviewee=self.user2,
            status="pending",
            date_effective=timezone.now(),
        )

    def test_get_interview_detail_as_participant(self):
        """Test getting interview detail as participant"""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(f"/interview/{self.interview.interview_id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_interview_detail_as_other_participant(self):
        """Test getting interview detail as other participant"""
        self.client.force_authenticate(user=self.user2)
        response = self.client.get(f"/interview/{self.interview.interview_id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)


class InterviewAllTests(AuthenticatedTestCase):
    """Test InterviewAll view"""

    def test_get_all_interviews_empty(self):
        """Test getting all interviews when none exist"""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get("/interview/all/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_get_all_interviews_with_data(self):
        """Test getting all interviews with data"""
        Interview.objects.create(
            interviewer=self.user,
            interviewee=self.user2,
            status="pending",
            date_effective=timezone.now(),
        )

        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get("/interview/all/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("interviews", response.data)


class PairInterviewTests(AuthenticatedTestCase):
    """Test PairInterview view"""

    def setUp(self):
        super().setUp()
        self.topic = QuestionTopic.objects.create(name="Arrays", created_by=self.admin_user)
        self.tech_question1 = TechnicalQuestion.objects.create(
            title="Two Sum",
            created_by=self.admin_user,
            topic=self.topic,
            prompt="Find two numbers",
            solution="Use hash map",
        )
        self.tech_question2 = TechnicalQuestion.objects.create(
            title="Three Sum",
            created_by=self.admin_user,
            topic=self.topic,
            prompt="Find three numbers",
            solution="Use two pointers",
        )
        TechnicalQuestionQueue.objects.create(question=self.tech_question1, position=1)
        TechnicalQuestionQueue.objects.create(question=self.tech_question2, position=2)

    @patch("interview.views.send_email")
    def test_pair_interviews_success(self, mock_send_email):
        """Test successful interview pairing"""
        # Create pool members with availability
        InterviewPool.objects.create(member=self.user)
        InterviewPool.objects.create(member=self.user2)

        InterviewAvailability.objects.create(
            member=self.user, interview_availability_slots=[[True] * 48 for _ in range(7)]
        )
        InterviewAvailability.objects.create(
            member=self.user2, interview_availability_slots=[[True] * 48 for _ in range(7)]
        )

        self.client.force_authenticate(user=self.admin_user)
        response = self.client.post("/interview/pair/", {})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("paired_interviews", response.data)

    def test_pair_interviews_odd_number(self):
        """Test pairing with odd number of members"""
        InterviewPool.objects.create(member=self.user)

        self.client.force_authenticate(user=self.admin_user)
        response = self.client.post("/interview/pair/", {})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_pair_interviews_insufficient_questions(self):
        """Test pairing without enough questions in queue"""
        TechnicalQuestionQueue.objects.all().delete()

        InterviewPool.objects.create(member=self.user)
        InterviewPool.objects.create(member=self.user2)

        self.client.force_authenticate(user=self.admin_user)
        response = self.client.post("/interview/pair/", {})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_get_pair_interview_endpoint(self):
        """Test GET on pair interview endpoint"""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get("/interview/pair/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)


class InterviewAssignQuestionRandomTests(AuthenticatedTestCase):
    """Test InterviewAssignQuestionRandom view"""

    def setUp(self):
        super().setUp()
        self.topic = QuestionTopic.objects.create(name="Arrays", created_by=self.admin_user)
        self.tech_question = TechnicalQuestion.objects.create(
            title="Two Sum",
            created_by=self.admin_user,
            topic=self.topic,
            prompt="Find two numbers",
            solution="Use hash map",
        )
        self.behavioral_question = BehavioralQuestion.objects.create(
            created_by=self.admin_user,
            prompt="Tell me about a time...",
            solution="Use STAR method",
        )

    def test_assign_questions_to_interviews(self):
        """Test assigning random questions to interviews"""
        interview = Interview.objects.create(
            interviewer=self.user,
            interviewee=self.user2,
            status="pending",
            date_effective=timezone.now(),
        )

        self.client.force_authenticate(user=self.admin_user)
        response = self.client.post("/interview/assign-questions/")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_assign_questions_no_interviews(self):
        """Test assigning questions when no interviews exist"""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.post("/interview/assign-questions/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class InterviewAssignQuestionRandomIndividualTests(AuthenticatedTestCase):
    """Test InterviewAssignQuestionRandomIndividual view"""

    def setUp(self):
        super().setUp()
        self.topic = QuestionTopic.objects.create(name="Arrays", created_by=self.admin_user)
        self.tech_question = TechnicalQuestion.objects.create(
            title="Two Sum",
            created_by=self.admin_user,
            topic=self.topic,
            prompt="Find two numbers",
            solution="Use hash map",
        )
        self.behavioral_question = BehavioralQuestion.objects.create(
            created_by=self.admin_user,
            prompt="Tell me about a time...",
            solution="Use STAR method",
        )
        self.interview = Interview.objects.create(
            interviewer=self.user,
            interviewee=self.user2,
            status="pending",
            date_effective=timezone.now(),
        )

    def test_assign_questions_to_individual_interview(self):
        """Test assigning questions to individual interview"""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.post(f"/interview/{self.interview.interview_id}/assign-questions/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_assign_questions_interview_not_found(self):
        """Test assigning questions to non-existent interview"""
        import uuid

        fake_id = uuid.uuid4()
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.post(f"/interview/{fake_id}/assign-questions/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class InterviewQuestionsTests(AuthenticatedTestCase):
    """Test InterviewQuestions view"""

    def setUp(self):
        super().setUp()
        self.topic = QuestionTopic.objects.create(name="Arrays", created_by=self.admin_user)
        self.tech_question = TechnicalQuestion.objects.create(
            title="Two Sum",
            created_by=self.admin_user,
            topic=self.topic,
            prompt="Find two numbers",
            solution="Use hash map",
        )
        self.interview = Interview.objects.create(
            interviewer=self.user,
            interviewee=self.user2,
            status="pending",
            date_effective=timezone.now(),
        )
        self.interview.technical_questions.add(self.tech_question)

    def test_get_interview_questions(self):
        """Test getting questions for an interview"""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(f"/interview/{self.interview.interview_id}/questions/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("technical_questions", response.data)
        self.assertIn("behavioral_questions", response.data)

    def test_get_interview_questions_not_found(self):
        """Test getting questions for non-existent interview"""
        import uuid

        fake_id = uuid.uuid4()
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(f"/interview/{fake_id}/questions/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class InterviewRunningStatusTests(AuthenticatedTestCase):
    """Test InterviewRunningStatus view"""

    def setUp(self):
        super().setUp()
        self.interview = Interview.objects.create(
            interviewer=self.user,
            interviewee=self.user2,
            status="active",
            date_effective=timezone.now(),
        )

    def test_get_running_status(self):
        """Test getting running status of active interview"""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(f"/interview/{self.interview.interview_id}/status/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "active")

    def test_get_running_status_not_found(self):
        """Test getting status of non-existent interview"""
        import uuid

        fake_id = uuid.uuid4()
        self.client.force_authenticate(user=self.user)
        response = self.client.get(f"/interview/{fake_id}/status/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_put_complete_interview(self):
        """Test completing an active interview"""
        self.client.force_authenticate(user=self.user)
        response = self.client.put(f"/interview/{self.interview.interview_id}/status/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)


class UserInterviewsDetailViewTests(AuthenticatedTestCase):
    """Test UserInterviewsDetailView"""

    def setUp(self):
        super().setUp()
        self.topic = QuestionTopic.objects.create(name="Arrays", created_by=self.admin_user)
        self.tech_question = TechnicalQuestion.objects.create(
            title="Two Sum",
            created_by=self.admin_user,
            topic=self.topic,
            prompt="Find two numbers",
            solution="Use hash map",
        )
        self.interview = Interview.objects.create(
            interviewer=self.user,
            interviewee=self.user2,
            status="pending",
            date_effective=timezone.now(),
        )
        self.interview.technical_questions.add(self.tech_question)

    def test_get_user_interviews_detail(self):
        """Test getting detailed user interviews"""
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/interview/user/interviews/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("interviews", response.data)

    def test_get_user_interviews_detail_as_interviewee(self):
        """Test getting interviews as interviewee"""
        self.client.force_authenticate(user=self.user2)
        response = self.client.get("/interview/user/interviews/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)


class GetSignupDataTests(AuthenticatedTestCase):
    """Test GetSignupData view"""

    def test_get_signup_data_empty(self):
        """Test getting signup data when empty"""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get("/interview/signup-data/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data, list)

    def test_get_signup_data_with_signups(self):
        """Test getting signup data with signups"""
        InterviewPool.objects.create(member=self.user)

        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get("/interview/signup-data/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)


# ============================================================================
# EDGE CASE AND INTEGRATION TESTS
# ============================================================================


class InterviewEdgeCaseTests(AuthenticatedTestCase):
    """Test edge cases and boundary conditions"""

    def test_interview_with_null_proposed_by(self):
        """Test interview with null proposed_by field"""
        interview = Interview.objects.create(
            interviewer=self.user,
            interviewee=self.user2,
            status="pending",
            date_effective=timezone.now(),
            proposed_by=None,
        )
        self.assertIsNone(interview.proposed_by)

    def test_interview_with_null_proposed_time(self):
        """Test interview with null proposed_time"""
        interview = Interview.objects.create(
            interviewer=self.user,
            interviewee=self.user2,
            status="pending",
            date_effective=timezone.now(),
            proposed_time=None,
        )
        self.assertIsNone(interview.proposed_time)

    def test_interview_with_null_committed_time(self):
        """Test interview with null committed_time"""
        interview = Interview.objects.create(
            interviewer=self.user,
            interviewee=self.user2,
            status="pending",
            date_effective=timezone.now(),
            committed_time=None,
        )
        self.assertIsNone(interview.committed_time)

    def test_interview_with_null_date_completed(self):
        """Test interview with null date_completed"""
        interview = Interview.objects.create(
            interviewer=self.user,
            interviewee=self.user2,
            status="pending",
            date_effective=timezone.now(),
            date_completed=None,
        )
        self.assertIsNone(interview.date_completed)

    def test_availability_boundary_values(self):
        """Test availability with boundary values"""
        # All false
        availability_all_false = [[False] * 48 for _ in range(7)]
        avail = InterviewAvailability.objects.create(
            member=self.user, interview_availability_slots=availability_all_false
        )
        self.assertEqual(avail.interview_availability_slots, availability_all_false)

        # All true
        availability_all_true = [[True] * 48 for _ in range(7)]
        avail.set_interview_availability(availability_all_true)
        self.assertEqual(avail.interview_availability_slots, availability_all_true)

    def test_multiple_interviews_same_users(self):
        """Test creating multiple interviews with same users"""
        interview1 = Interview.objects.create(
            interviewer=self.user,
            interviewee=self.user2,
            status="pending",
            date_effective=timezone.now(),
        )
        interview2 = Interview.objects.create(
            interviewer=self.user,
            interviewee=self.user2,
            status="pending",
            date_effective=timezone.now() + timedelta(days=7),
        )

        self.assertNotEqual(interview1.interview_id, interview2.interview_id)

    def test_interview_cascade_delete_on_user(self):
        """Test that interviews are deleted when user is deleted"""
        interview = Interview.objects.create(
            interviewer=self.user,
            interviewee=self.user2,
            status="pending",
            date_effective=timezone.now(),
        )
        interview_id = interview.interview_id

        self.user.delete()

        self.assertFalse(Interview.objects.filter(interview_id=interview_id).exists())
