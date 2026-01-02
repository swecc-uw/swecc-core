import uuid
from unittest.mock import patch

from django.contrib.auth.models import Group
from django.test import TestCase
from django.utils import timezone
from interview.models import Interview
from members.models import User
from questions.models import QuestionTopic, TechnicalQuestion
from rest_framework import status
from rest_framework.test import APIClient

from .models import Report
from .serializers import ReportSerializer


class AuthenticatedTestCase(TestCase):
    """Base test case that automatically mocks authentication"""

    def setUp(self):
        super().setUp()
        # Create a test user
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
            first_name="Test",
            last_name="User",
        )
        # Create admin group and add user to it
        self.admin_group = Group.objects.create(name="is_admin")
        self.user.groups.add(self.admin_group)

        # Create API client and force authenticate
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

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


# ============================================================================
# Model Tests
# ============================================================================


class ReportModelTests(TestCase):
    """Test Report model"""

    def setUp(self):
        self.user1 = User.objects.create(
            username="user1", discord_id="111111111", discord_username="user_one"
        )
        self.user2 = User.objects.create(
            username="user2", discord_id="222222222", discord_username="user_two"
        )
        self.admin = User.objects.create(
            username="admin", discord_id="333333333", discord_username="admin_user"
        )
        self.admin_group, _ = Group.objects.get_or_create(name="is_admin")
        self.admin.groups.add(self.admin_group)

    def test_create_member_report(self):
        """Test creating a member report"""
        report = Report.objects.create(
            type="member",
            reporter_user_id=self.user1,
            associated_member=self.user2,
            reason="Inappropriate behavior",
            status="pending",
        )

        self.assertIsNotNone(report.report_id)
        self.assertEqual(report.type, "member")
        self.assertEqual(report.reporter_user_id, self.user1)
        self.assertEqual(report.associated_member, self.user2)
        self.assertEqual(report.status, "pending")
        self.assertIsNotNone(report.created)
        self.assertIsNotNone(report.updated)

    def test_create_interview_report(self):
        """Test creating an interview report"""
        interview = Interview.objects.create(
            interviewer=self.user1,
            interviewee=self.user2,
            date_effective=timezone.now(),
            status="active",
        )

        report = Report.objects.create(
            type="interview",
            reporter_user_id=self.user1,
            associated_interview=interview,
            reason="Technical issues",
            status="pending",
        )

        self.assertEqual(report.type, "interview")
        self.assertEqual(report.associated_interview, interview)

    def test_create_question_report(self):
        """Test creating a question report"""
        topic = QuestionTopic.objects.create(name="Arrays", created_by=self.user1)
        question = TechnicalQuestion.objects.create(
            title="Test Q",
            created_by=self.user1,
            topic=topic,
            prompt="Test prompt",
            solution="Test solution",
        )

        report = Report.objects.create(
            type="question",
            reporter_user_id=self.user1,
            associated_question=question,
            reason="Incorrect solution",
            status="pending",
        )

        self.assertEqual(report.type, "question")
        self.assertEqual(report.associated_question, question)

    def test_report_status_choices(self):
        """Test report status choices"""
        report = Report.objects.create(
            type="member",
            reporter_user_id=self.user1,
            associated_member=self.user2,
            reason="Test",
            status="pending",
        )

        # Test all valid statuses
        for status_value, _ in Report.STATUS_CHOICES:
            report.status = status_value
            report.save()
            report.refresh_from_db()
            self.assertEqual(report.status, status_value)

    def test_report_with_assignee(self):
        """Test report with assignee"""
        report = Report.objects.create(
            type="member",
            reporter_user_id=self.user1,
            associated_member=self.user2,
            reason="Test",
            status="resolving",
            assignee=self.admin,
        )

        self.assertEqual(report.assignee, self.admin)
        self.assertEqual(report.status, "resolving")

    def test_report_with_admin_notes(self):
        """Test report with admin notes"""
        report = Report.objects.create(
            type="member",
            reporter_user_id=self.user1,
            associated_member=self.user2,
            reason="Test",
            status="completed",
            admin_notes="Resolved by warning the user",
        )

        self.assertEqual(report.admin_notes, "Resolved by warning the user")

    def test_get_associated_id_member(self):
        """Test get_associated_id for member report"""
        report = Report.objects.create(
            type="member",
            reporter_user_id=self.user1,
            associated_member=self.user2,
            reason="Test",
        )

        self.assertEqual(report.get_associated_id(), str(self.user2.id))

    def test_get_associated_id_interview(self):
        """Test get_associated_id for interview report"""
        interview = Interview.objects.create(
            interviewer=self.user1,
            interviewee=self.user2,
            date_effective=timezone.now(),
            status="active",
        )

        report = Report.objects.create(
            type="interview",
            reporter_user_id=self.user1,
            associated_interview=interview,
            reason="Test",
        )

        self.assertEqual(report.get_associated_id(), str(interview.interview_id))

    def test_get_associated_id_question(self):
        """Test get_associated_id for question report"""
        topic = QuestionTopic.objects.create(name="Arrays", created_by=self.user1)
        question = TechnicalQuestion.objects.create(
            title="Test Q",
            created_by=self.user1,
            topic=topic,
            prompt="Test",
            solution="Test",
        )

        report = Report.objects.create(
            type="question",
            reporter_user_id=self.user1,
            associated_question=question,
            reason="Test",
        )

        self.assertEqual(report.get_associated_id(), str(question.question_id))

    def test_get_associated_id_none(self):
        """Test get_associated_id when no association exists"""
        report = Report.objects.create(type="member", reporter_user_id=self.user1, reason="Test")

        self.assertIsNone(report.get_associated_id())

    def test_report_cascade_delete_reporter(self):
        """Test that deleting reporter cascades to report"""
        report = Report.objects.create(
            type="member",
            reporter_user_id=self.user1,
            associated_member=self.user2,
            reason="Test",
        )
        report_id = report.report_id

        self.user1.delete()
        self.assertFalse(Report.objects.filter(report_id=report_id).exists())

    def test_report_cascade_delete_associated_member(self):
        """Test that deleting associated member cascades to report"""
        report = Report.objects.create(
            type="member",
            reporter_user_id=self.user1,
            associated_member=self.user2,
            reason="Test",
        )
        report_id = report.report_id

        self.user2.delete()
        self.assertFalse(Report.objects.filter(report_id=report_id).exists())

    def test_report_cascade_delete_interview(self):
        """Test that deleting interview cascades to report"""
        interview = Interview.objects.create(
            interviewer=self.user1,
            interviewee=self.user2,
            date_effective=timezone.now(),
            status="active",
        )

        report = Report.objects.create(
            type="interview",
            reporter_user_id=self.user1,
            associated_interview=interview,
            reason="Test",
        )
        report_id = report.report_id

        interview.delete()
        self.assertFalse(Report.objects.filter(report_id=report_id).exists())


# ============================================================================
# Serializer Tests
# ============================================================================


class ReportSerializerTests(TestCase):
    """Test ReportSerializer"""

    def setUp(self):
        self.user1 = User.objects.create(
            username="user1", discord_id="111111111", discord_username="user_one"
        )
        self.user2 = User.objects.create(
            username="user2", discord_id="222222222", discord_username="user_two"
        )

    def test_serialize_member_report(self):
        """Test serializing a member report"""
        report = Report.objects.create(
            type="member",
            reporter_user_id=self.user1,
            associated_member=self.user2,
            reason="Test reason",
            status="pending",
        )

        serializer = ReportSerializer(report)
        data = serializer.data

        self.assertEqual(data["type"], "member")
        self.assertEqual(data["reason"], "Test reason")
        self.assertEqual(data["status"], "pending")
        self.assertIn("reporter", data)
        self.assertIn("associated_object", data)
        self.assertIn("associated_id", data)

    def test_validate_single_association(self):
        """Test that only one association is allowed"""
        topic = QuestionTopic.objects.create(name="Arrays", created_by=self.user1)
        question = TechnicalQuestion.objects.create(
            title="Test Q",
            created_by=self.user1,
            topic=topic,
            prompt="Test",
            solution="Test",
        )

        # Try to create report with multiple associations
        data = {
            "type": "member",
            "reporter_user_id": self.user1.id,
            "associated_member": self.user2.id,
            "associated_question": question.question_id,
            "reason": "Test",
            "status": "pending",
        }

        serializer = ReportSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("Only one of", str(serializer.errors))

    def test_validate_report_type(self):
        """Test that invalid report type is rejected"""
        data = {
            "type": "invalid_type",
            "reporter_user_id": self.user1.id,
            "associated_member": self.user2.id,
            "reason": "Test",
            "status": "pending",
        }

        serializer = ReportSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        # Django's ChoiceField validation message
        self.assertIn("not a valid choice", str(serializer.errors))

    def test_validate_status(self):
        """Test that invalid status is rejected"""
        data = {
            "type": "member",
            "reporter_user_id": self.user1.id,
            "associated_member": self.user2.id,
            "reason": "Test",
            "status": "invalid_status",
        }

        serializer = ReportSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        # Django's ChoiceField validation message
        self.assertIn("not a valid choice", str(serializer.errors))

    def test_get_associated_object_member(self):
        """Test get_associated_object for member report"""
        report = Report.objects.create(
            type="member",
            reporter_user_id=self.user1,
            associated_member=self.user2,
            reason="Test",
        )

        serializer = ReportSerializer(report)
        associated_object = serializer.data["associated_object"]

        self.assertIsNotNone(associated_object)
        self.assertEqual(associated_object["username"], "user2")

    def test_get_reporter(self):
        """Test get_reporter method"""
        report = Report.objects.create(
            type="member",
            reporter_user_id=self.user1,
            associated_member=self.user2,
            reason="Test",
        )

        serializer = ReportSerializer(report)
        reporter = serializer.data["reporter"]

        self.assertIsNotNone(reporter)
        self.assertEqual(reporter["username"], "user1")


# ============================================================================
# View Tests
# ============================================================================


class CreateReportViewTests(AuthenticatedTestCase):
    """Test CreateReport view"""

    def setUp(self):
        super().setUp()
        self.user1 = User.objects.create(
            username="user1", discord_id="111111111", discord_username="user_one"
        )
        self.user2 = User.objects.create(
            username="user2", discord_id="222222222", discord_username="user_two"
        )

    def test_create_member_report(self):
        """Test creating a member report"""
        data = {
            "reporter_user_id": self.user1.id,
            "type": "member",
            "associated_id": self.user2.id,
            "reason": "Inappropriate behavior",
        }

        response = self.client.post("/reports/", data, format="json")
        self.assertResponse(response, status.HTTP_201_CREATED)
        self.assertTrue(Report.objects.filter(type="member").exists())

    def test_create_interview_report(self):
        """Test creating an interview report"""
        interview = Interview.objects.create(
            interviewer=self.user1,
            interviewee=self.user2,
            date_effective=timezone.now(),
            status="active",
        )

        data = {
            "reporter_user_id": self.user1.id,
            "type": "interview",
            "associated_id": str(interview.interview_id),
            "reason": "Technical issues",
        }

        response = self.client.post("/reports/", data, format="json")
        self.assertResponse(response, status.HTTP_201_CREATED)

    def test_create_question_report(self):
        """Test creating a question report"""
        topic = QuestionTopic.objects.create(name="Arrays", created_by=self.user1)
        question = TechnicalQuestion.objects.create(
            title="Test Q",
            created_by=self.user1,
            topic=topic,
            prompt="Test",
            solution="Test",
        )

        data = {
            "reporter_user_id": self.user1.id,
            "type": "question",
            "associated_id": str(question.question_id),
            "reason": "Incorrect solution",
        }

        response = self.client.post("/reports/", data, format="json")
        self.assertResponse(response, status.HTTP_201_CREATED)

    def test_create_report_missing_required_fields(self):
        """Test creating report with missing required fields"""
        data = {"reporter_user_id": self.user1.id}

        response = self.client.post("/reports/", data, format="json")
        self.assertResponse(response, status.HTTP_400_BAD_REQUEST)
        self.assertIn("required", response.data["error"])

    def test_create_report_with_nonexistent_reporter(self):
        """Test creating report with non-existent reporter"""
        data = {
            "reporter_user_id": 99999,
            "type": "member",
            "associated_id": self.user2.id,
            "reason": "Test",
        }

        response = self.client.post("/reports/", data, format="json")
        self.assertResponse(response, status.HTTP_404_NOT_FOUND)
        self.assertIn("not found", response.data["error"])

    def test_create_report_with_nonexistent_associated_member(self):
        """Test creating report with non-existent associated member"""
        data = {
            "reporter_user_id": self.user1.id,
            "type": "member",
            "associated_id": 99999,
            "reason": "Test",
        }

        response = self.client.post("/reports/", data, format="json")
        # View returns 404 for non-existent user (either reporter or associated member)
        self.assertResponse(response, status.HTTP_404_NOT_FOUND)

    def test_create_report_self_report(self):
        """Test that user cannot report themselves"""
        data = {
            "reporter_user_id": self.user1.id,
            "type": "member",
            "associated_id": self.user1.id,
            "reason": "Test",
        }

        response = self.client.post("/reports/", data, format="json")
        self.assertResponse(response, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Cannot report yourself", response.data["error"])

    def test_create_interview_report_not_participant(self):
        """Test that only interview participants can report it"""
        user3 = User.objects.create(
            username="user3", discord_id="333333333", discord_username="user_three"
        )
        interview = Interview.objects.create(
            interviewer=self.user1,
            interviewee=self.user2,
            date_effective=timezone.now(),
            status="active",
        )

        data = {
            "reporter_user_id": user3.id,
            "type": "interview",
            "associated_id": str(interview.interview_id),
            "reason": "Test",
        }

        response = self.client.post("/reports/", data, format="json")
        self.assertResponse(response, status.HTTP_400_BAD_REQUEST)
        self.assertIn("not in interview", response.data["error"])

    def test_create_report_invalid_type(self):
        """Test creating report with invalid type"""
        data = {
            "reporter_user_id": self.user1.id,
            "type": "invalid_type",
            "associated_id": self.user2.id,
            "reason": "Test",
        }

        response = self.client.post("/reports/", data, format="json")
        self.assertResponse(response, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Invalid report type", response.data["error"])

    def test_create_report_default_reason(self):
        """Test that default reason is used when not provided"""
        data = {
            "reporter_user_id": self.user1.id,
            "type": "member",
            "associated_id": self.user2.id,
        }

        response = self.client.post("/reports/", data, format="json")
        self.assertResponse(response, status.HTTP_201_CREATED)

        report = Report.objects.get(report_id=response.data["report"]["report_id"])
        self.assertEqual(report.reason, "No reason provided")


class GetReportViewTests(AuthenticatedTestCase):
    """Test report retrieval views"""

    def setUp(self):
        super().setUp()
        self.user1 = User.objects.create(
            username="user1", discord_id="111111111", discord_username="user_one"
        )
        self.user2 = User.objects.create(
            username="user2", discord_id="222222222", discord_username="user_two"
        )
        self.admin = User.objects.create(
            username="admin", discord_id="333333333", discord_username="admin_user"
        )
        self.admin_group, _ = Group.objects.get_or_create(name="is_admin")
        self.admin.groups.add(self.admin_group)

    def test_get_all_reports(self):
        """Test getting all reports"""
        Report.objects.create(
            type="member",
            reporter_user_id=self.user1,
            associated_member=self.user2,
            reason="Test 1",
        )
        Report.objects.create(
            type="member",
            reporter_user_id=self.user2,
            associated_member=self.user1,
            reason="Test 2",
        )

        response = self.client.get("/reports/all/")
        self.assertResponse(response, status.HTTP_200_OK)
        self.assertEqual(len(response.data["reports"]), 2)

    def test_get_reports_by_user_id(self):
        """Test getting reports by user ID"""
        Report.objects.create(
            type="member",
            reporter_user_id=self.user1,
            associated_member=self.user2,
            reason="Test 1",
        )
        Report.objects.create(
            type="member",
            reporter_user_id=self.user2,
            associated_member=self.user1,
            reason="Test 2",
        )

        response = self.client.get(f"/reports/users/{self.user1.id}/")
        self.assertResponse(response, status.HTTP_200_OK)
        self.assertEqual(len(response.data["reports"]), 1)
        self.assertEqual(response.data["reports"][0]["reason"], "Test 1")

    def test_get_report_by_id(self):
        """Test getting a specific report by ID"""
        report = Report.objects.create(
            type="member",
            reporter_user_id=self.user1,
            associated_member=self.user2,
            reason="Test report",
        )

        response = self.client.get(f"/reports/{report.report_id}/")
        self.assertResponse(response, status.HTTP_200_OK)
        self.assertEqual(response.data["report"]["reason"], "Test report")

    def test_get_nonexistent_report(self):
        """Test getting non-existent report"""
        fake_id = uuid.uuid4()
        response = self.client.get(f"/reports/{fake_id}/")
        self.assertResponse(response, status.HTTP_404_NOT_FOUND)
        self.assertIn("not found", response.data["error"])


class AssignReportViewTests(AuthenticatedTestCase):
    """Test report assignment views"""

    def setUp(self):
        super().setUp()
        self.user1 = User.objects.create(
            username="user1", discord_id="111111111", discord_username="user_one"
        )
        self.user2 = User.objects.create(
            username="user2", discord_id="222222222", discord_username="user_two"
        )
        self.admin = User.objects.create(
            username="admin", discord_id="333333333", discord_username="admin_user"
        )
        self.admin_group, _ = Group.objects.get_or_create(name="is_admin")
        self.admin.groups.add(self.admin_group)

    def test_assign_report_to_admin(self):
        """Test assigning a report to an admin"""
        report = Report.objects.create(
            type="member",
            reporter_user_id=self.user1,
            associated_member=self.user2,
            reason="Test",
            status="pending",
        )

        data = {"assignee": self.admin.id}
        response = self.client.patch(f"/reports/{report.report_id}/assign/", data, format="json")
        self.assertResponse(response, status.HTTP_200_OK)

        report.refresh_from_db()
        self.assertEqual(report.assignee, self.admin)
        self.assertEqual(report.status, "resolving")

    def test_assign_report_missing_assignee(self):
        """Test assigning report without assignee field"""
        report = Report.objects.create(
            type="member",
            reporter_user_id=self.user1,
            associated_member=self.user2,
            reason="Test",
        )

        response = self.client.patch(f"/reports/{report.report_id}/assign/", {}, format="json")
        self.assertResponse(response, status.HTTP_400_BAD_REQUEST)
        self.assertIn("required", response.data["error"])

    def test_assign_report_to_non_admin(self):
        """Test assigning report to non-admin user"""
        report = Report.objects.create(
            type="member",
            reporter_user_id=self.user1,
            associated_member=self.user2,
            reason="Test",
        )

        data = {"assignee": self.user1.id}
        response = self.client.patch(f"/reports/{report.report_id}/assign/", data, format="json")
        self.assertResponse(response, status.HTTP_400_BAD_REQUEST)
        self.assertIn("not an admin", response.data["error"])

    def test_assign_nonexistent_report(self):
        """Test assigning non-existent report"""
        fake_id = uuid.uuid4()
        data = {"assignee": self.admin.id}

        response = self.client.patch(f"/reports/{fake_id}/assign/", data, format="json")
        self.assertResponse(response, status.HTTP_404_NOT_FOUND)


class UpdateReportStatusViewTests(AuthenticatedTestCase):
    """Test report status update views"""

    def setUp(self):
        super().setUp()
        self.user1 = User.objects.create(
            username="user1", discord_id="111111111", discord_username="user_one"
        )
        self.user2 = User.objects.create(
            username="user2", discord_id="222222222", discord_username="user_two"
        )

    def test_update_report_status(self):
        """Test updating report status"""
        report = Report.objects.create(
            type="member",
            reporter_user_id=self.user1,
            associated_member=self.user2,
            reason="Test",
            status="pending",
        )

        data = {"status": "completed"}
        response = self.client.patch(f"/reports/{report.report_id}/status/", data, format="json")
        self.assertResponse(response, status.HTTP_200_OK)

        report.refresh_from_db()
        self.assertEqual(report.status, "completed")

    def test_update_status_all_valid_statuses(self):
        """Test updating to all valid statuses"""
        report = Report.objects.create(
            type="member",
            reporter_user_id=self.user1,
            associated_member=self.user2,
            reason="Test",
            status="pending",
        )

        for status_value, _ in Report.STATUS_CHOICES:
            data = {"status": status_value}
            response = self.client.patch(
                f"/reports/{report.report_id}/status/", data, format="json"
            )
            self.assertResponse(response, status.HTTP_200_OK)

            report.refresh_from_db()
            self.assertEqual(report.status, status_value)

    def test_update_status_invalid(self):
        """Test updating to invalid status"""
        report = Report.objects.create(
            type="member",
            reporter_user_id=self.user1,
            associated_member=self.user2,
            reason="Test",
            status="pending",
        )

        data = {"status": "invalid_status"}
        response = self.client.patch(f"/reports/{report.report_id}/status/", data, format="json")
        self.assertResponse(response, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Invalid status", response.data["error"])

    def test_update_status_missing_field(self):
        """Test updating status without status field"""
        report = Report.objects.create(
            type="member",
            reporter_user_id=self.user1,
            associated_member=self.user2,
            reason="Test",
        )

        response = self.client.patch(f"/reports/{report.report_id}/status/", {}, format="json")
        self.assertResponse(response, status.HTTP_400_BAD_REQUEST)
        self.assertIn("required", response.data["error"])

    def test_update_status_nonexistent_report(self):
        """Test updating status of non-existent report"""
        fake_id = uuid.uuid4()
        data = {"status": "completed"}

        response = self.client.patch(f"/reports/{fake_id}/status/", data, format="json")
        self.assertResponse(response, status.HTTP_404_NOT_FOUND)


# ============================================================================
# Edge Cases and Integration Tests
# ============================================================================


class ReportEdgeCaseTests(AuthenticatedTestCase):
    """Test edge cases and error handling"""

    def setUp(self):
        super().setUp()
        self.user1 = User.objects.create(
            username="user1", discord_id="111111111", discord_username="user_one"
        )
        self.user2 = User.objects.create(
            username="user2", discord_id="222222222", discord_username="user_two"
        )

    def test_multiple_reports_same_user(self):
        """Test creating multiple reports for the same user"""
        for i in range(3):
            Report.objects.create(
                type="member",
                reporter_user_id=self.user1,
                associated_member=self.user2,
                reason=f"Test {i}",
            )

        reports = Report.objects.filter(reporter_user_id=self.user1)
        self.assertEqual(reports.count(), 3)

    def test_report_with_very_long_reason(self):
        """Test creating report with very long reason"""
        long_reason = "A" * 5000
        report = Report.objects.create(
            type="member",
            reporter_user_id=self.user1,
            associated_member=self.user2,
            reason=long_reason,
        )

        self.assertEqual(len(report.reason), 5000)

    def test_report_updated_timestamp(self):
        """Test that updated timestamp changes on save"""
        report = Report.objects.create(
            type="member",
            reporter_user_id=self.user1,
            associated_member=self.user2,
            reason="Test",
        )

        original_updated = report.updated
        report.status = "completed"
        report.save()
        report.refresh_from_db()

        self.assertGreater(report.updated, original_updated)

    def test_concurrent_status_updates(self):
        """Test handling concurrent status updates"""
        report = Report.objects.create(
            type="member",
            reporter_user_id=self.user1,
            associated_member=self.user2,
            reason="Test",
            status="pending",
        )

        # Simulate concurrent updates
        data1 = {"status": "resolving"}
        data2 = {"status": "completed"}

        response1 = self.client.patch(f"/reports/{report.report_id}/status/", data1, format="json")
        response2 = self.client.patch(f"/reports/{report.report_id}/status/", data2, format="json")

        self.assertResponse(response1, status.HTTP_200_OK)
        self.assertResponse(response2, status.HTTP_200_OK)

        # Last update should win
        report.refresh_from_db()
        self.assertEqual(report.status, "completed")

    def test_report_lifecycle(self):
        """Test complete report lifecycle"""
        admin = User.objects.create(
            username="admin", discord_id="333333333", discord_username="admin_user"
        )
        admin_group, _ = Group.objects.get_or_create(name="is_admin")
        admin.groups.add(admin_group)

        # Create report
        data = {
            "reporter_user_id": self.user1.id,
            "type": "member",
            "associated_id": self.user2.id,
            "reason": "Test lifecycle",
        }
        response = self.client.post("/reports/", data, format="json")
        self.assertResponse(response, status.HTTP_201_CREATED)
        report_id = response.data["report"]["report_id"]

        # Assign to admin
        assign_data = {"assignee": admin.id}
        response = self.client.patch(f"/reports/{report_id}/assign/", assign_data, format="json")
        self.assertResponse(response, status.HTTP_200_OK)

        # Update status to completed
        status_data = {"status": "completed"}
        response = self.client.patch(f"/reports/{report_id}/status/", status_data, format="json")
        self.assertResponse(response, status.HTTP_200_OK)

        # Verify final state
        report = Report.objects.get(report_id=report_id)
        self.assertEqual(report.status, "completed")
        self.assertEqual(report.assignee, admin)
