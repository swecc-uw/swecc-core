from unittest.mock import MagicMock, patch

import requests
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .views import (
    DisableMetricCollection,
    DisableMetricTask,
    EnableMetricCollection,
    EnableMetricTask,
    GetAllContainerStatus,
    GetChronosHealth,
    GetContainerMetadata,
    GetContainerRecentUsage,
    GetContainerUsageHistory,
    GetMetricCollectionStatus,
    GetMetricTaskStatus,
    GetRunningContainer,
    MetricServerAPI,
    MetricViewAllRecent,
)

# ============================================================================
# MetricServerAPI Tests
# ============================================================================


class MetricServerAPITest(TestCase):
    """Test MetricServerAPI base class"""

    def setUp(self):
        self.api = MetricServerAPI()

    @patch("metrics.views.requests.get")
    def test_get_from_metric_service_success(self, mock_get):
        """Test successful GET request to metric service"""
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "ok"}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = self.api.get_from_metric_service("/test")
        self.assertEqual(result, {"status": "ok"})
        mock_get.assert_called_once()

    @patch("metrics.views.requests.get")
    def test_get_from_metric_service_failure(self, mock_get):
        """Test failed GET request to metric service"""
        mock_get.side_effect = requests.exceptions.RequestException("Connection error")

        with self.assertRaises(Exception) as context:
            self.api.get_from_metric_service("/test")
        self.assertIn("Failed to fetch data from metric service", str(context.exception))

    @patch("metrics.views.requests.post")
    def test_post_from_metric_service_success(self, mock_post):
        """Test successful POST request to metric service"""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        # Should not raise exception
        self.api.post_from_metric_service("/test", {"key": "value"})
        mock_post.assert_called_once()

    @patch("metrics.views.requests.post")
    def test_post_from_metric_service_failure(self, mock_post):
        """Test failed POST request to metric service"""
        mock_post.side_effect = requests.exceptions.RequestException("Connection error")

        with self.assertRaises(Exception) as context:
            self.api.post_from_metric_service("/test", {"key": "value"})
        self.assertIn("Failed to fetch data from metric service", str(context.exception))

    @patch("metrics.views.requests.post")
    def test_post_job_to_metric_service_success(self, mock_post):
        """Test successful POST job to metric service"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        # Should not raise exception
        self.api.post_job_to_metric_service("/test", "job_123")
        mock_post.assert_called_once()

    @patch("metrics.views.requests.post")
    def test_post_job_to_metric_service_not_found(self, mock_post):
        """Test POST job with 404 response"""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_post.return_value = mock_response

        with self.assertRaises(Exception) as context:
            self.api.post_job_to_metric_service("/test", "job_123")
        self.assertIn("not found", str(context.exception))

    @patch("metrics.views.requests.post")
    def test_post_job_to_metric_service_failure(self, mock_post):
        """Test failed POST job to metric service"""
        mock_post.side_effect = requests.exceptions.RequestException("Connection error")

        with self.assertRaises(Exception) as context:
            self.api.post_job_to_metric_service("/test", "job_123")
        self.assertIn("Failed to post to metric service", str(context.exception))


# ============================================================================
# View Tests - Base class for authenticated tests
# ============================================================================


class AuthenticatedMetricsTestCase(APITestCase):
    """Base test case that mocks admin authentication"""

    def setUp(self):
        super().setUp()
        self.admin_patcher = patch("custom_auth.permissions.IsAdmin.has_permission")
        self.mock_admin_perm = self.admin_patcher.start()
        self.mock_admin_perm.return_value = True

    def tearDown(self):
        super().tearDown()
        self.admin_patcher.stop()


# ============================================================================
# Container Status Views Tests
# ============================================================================


class GetAllContainerStatusTest(AuthenticatedMetricsTestCase):
    """Test GetAllContainerStatus view"""

    def setUp(self):
        super().setUp()
        self.url = reverse("container-status")

    @patch.object(GetAllContainerStatus, "get_from_metric_service")
    def test_get_all_container_status_success(self, mock_get):
        """Test successful GET all container status"""
        mock_get.return_value = {"container1": "running", "container2": "stopped"}

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {"container1": "running", "container2": "stopped"})

    @patch.object(GetAllContainerStatus, "get_from_metric_service")
    def test_get_all_container_status_failure(self, mock_get):
        """Test failed GET all container status"""
        mock_get.side_effect = Exception("Service unavailable")

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertIn("error", response.data)


class GetRunningContainerTest(AuthenticatedMetricsTestCase):
    """Test GetRunningContainer view"""

    def setUp(self):
        super().setUp()
        self.url = reverse("container-running")

    @patch.object(GetRunningContainer, "get_from_metric_service")
    def test_get_running_containers_success(self, mock_get):
        """Test successful GET running containers"""
        mock_get.return_value = {
            "container1": "running",
            "container2": "stopped",
            "container3": "running",
        }

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, ["container1", "container3"])

    @patch.object(GetRunningContainer, "get_from_metric_service")
    def test_get_running_containers_failure(self, mock_get):
        """Test failed GET running containers"""
        mock_get.side_effect = Exception("Service unavailable")

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)


class GetChronosHealthTest(AuthenticatedMetricsTestCase):
    """Test GetChronosHealth view"""

    def setUp(self):
        super().setUp()
        self.url = reverse("chronos-health")

    @patch.object(GetChronosHealth, "get_from_metric_service")
    def test_get_chronos_health_success(self, mock_get):
        """Test successful GET chronos health"""
        mock_get.return_value = {"status": "healthy"}

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {"status": "healthy"})

    @patch.object(GetChronosHealth, "get_from_metric_service")
    def test_get_chronos_health_failure(self, mock_get):
        """Test failed GET chronos health"""
        mock_get.side_effect = Exception("Service unavailable")

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class GetContainerMetadataTest(AuthenticatedMetricsTestCase):
    """Test GetContainerMetadata view"""

    def setUp(self):
        super().setUp()
        self.container_name = "test-container"
        self.url = reverse("container-metadata", kwargs={"container_name": self.container_name})

    @patch.object(GetContainerMetadata, "get_from_metric_service")
    def test_get_container_metadata_success(self, mock_get):
        """Test successful GET container metadata"""
        mock_get.return_value = {"name": "test-container", "image": "test:latest"}

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "test-container")

    @patch.object(GetContainerMetadata, "get_from_metric_service")
    def test_get_container_metadata_failure(self, mock_get):
        """Test failed GET container metadata"""
        mock_get.side_effect = Exception("Container not found")

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)


class GetContainerRecentUsageTest(AuthenticatedMetricsTestCase):
    """Test GetContainerRecentUsage view"""

    def setUp(self):
        super().setUp()
        self.container_name = "test-container"
        self.url = reverse("container-usage-recent", kwargs={"container_name": self.container_name})

    @patch.object(GetContainerRecentUsage, "get_from_metric_service")
    def test_get_container_recent_usage_success(self, mock_get):
        """Test successful GET container recent usage"""
        mock_get.return_value = {"cpu": "50%", "memory": "1GB"}

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {"cpu": "50%", "memory": "1GB"})

    @patch.object(GetContainerRecentUsage, "get_from_metric_service")
    def test_get_container_recent_usage_failure(self, mock_get):
        """Test failed GET container recent usage"""
        mock_get.side_effect = Exception("Service unavailable")

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)


class GetContainerUsageHistoryTest(AuthenticatedMetricsTestCase):
    """Test GetContainerUsageHistory view"""

    def setUp(self):
        super().setUp()
        self.container_name = "test-container"
        self.url = reverse(
            "container-usage-history", kwargs={"container_name": self.container_name}
        )

    @patch.object(GetContainerUsageHistory, "get_from_metric_service")
    def test_get_container_usage_history_success(self, mock_get):
        """Test successful GET container usage history"""
        mock_get.return_value = [{"timestamp": "2024-01-01", "cpu": "50%"}]

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    @patch.object(GetContainerUsageHistory, "get_from_metric_service")
    def test_get_container_usage_history_failure(self, mock_get):
        """Test failed GET container usage history"""
        mock_get.side_effect = Exception("Service unavailable")

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================================
# Metric Task Management Views Tests
# ============================================================================


class DisableMetricTaskTest(AuthenticatedMetricsTestCase):
    """Test DisableMetricTask view"""

    def setUp(self):
        super().setUp()
        self.url = reverse("disable-metrics-poll")

    @patch.object(DisableMetricTask, "post_job_to_metric_service")
    def test_disable_metric_task_success(self, mock_post):
        """Test successful POST to disable metric task"""
        mock_post.return_value = None

        response = self.client.post(self.url, {"job_id": "test_job"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("successfully paused", response.data["message"])

    @patch.object(DisableMetricTask, "post_job_to_metric_service")
    def test_disable_metric_task_missing_job_id(self, mock_post):
        """Test POST without job_id"""
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Missing 'job_id'", response.data["error"])

    @patch.object(DisableMetricTask, "post_job_to_metric_service")
    def test_disable_metric_task_not_found(self, mock_post):
        """Test POST with non-existent job"""
        mock_post.side_effect = Exception("Job with ID 'test_job' not found")

        response = self.client.post(self.url, {"job_id": "test_job"})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @patch.object(DisableMetricTask, "post_job_to_metric_service")
    def test_disable_metric_task_failure(self, mock_post):
        """Test POST with service failure"""
        mock_post.side_effect = Exception("Service error")

        response = self.client.post(self.url, {"job_id": "test_job"})
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)


class EnableMetricTaskTest(AuthenticatedMetricsTestCase):
    """Test EnableMetricTask view"""

    def setUp(self):
        super().setUp()
        self.url = reverse("enable-metrics-poll")

    @patch.object(EnableMetricTask, "post_job_to_metric_service")
    def test_enable_metric_task_success(self, mock_post):
        """Test successful POST to enable metric task"""
        mock_post.return_value = None

        response = self.client.post(self.url, {"job_id": "test_job"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("successfully resumed", response.data["message"])

    @patch.object(EnableMetricTask, "post_job_to_metric_service")
    def test_enable_metric_task_missing_job_id(self, mock_post):
        """Test POST without job_id"""
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch.object(EnableMetricTask, "post_job_to_metric_service")
    def test_enable_metric_task_not_found(self, mock_post):
        """Test POST with non-existent job"""
        mock_post.side_effect = Exception("Job with ID 'test_job' not found")

        response = self.client.post(self.url, {"job_id": "test_job"})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class EnableMetricCollectionTest(AuthenticatedMetricsTestCase):
    """Test EnableMetricCollection view"""

    def setUp(self):
        super().setUp()
        self.url = reverse("enable-metrics-collection")

    @patch.object(EnableMetricCollection, "post_job_to_metric_service")
    def test_enable_metric_collection_success(self, mock_post):
        """Test successful POST to enable metric collection"""
        mock_post.return_value = None

        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("enable metric collection", response.data["message"])

    @patch.object(EnableMetricCollection, "post_job_to_metric_service")
    def test_enable_metric_collection_failure(self, mock_post):
        """Test POST with service failure"""
        mock_post.side_effect = Exception("Service error")

        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)


class DisableMetricCollectionTest(AuthenticatedMetricsTestCase):
    """Test DisableMetricCollection view"""

    def setUp(self):
        super().setUp()
        self.url = reverse("disable-metrics-collection")

    @patch.object(DisableMetricCollection, "post_job_to_metric_service")
    def test_disable_metric_collection_success(self, mock_post):
        """Test successful POST to disable metric collection"""
        mock_post.return_value = None

        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("disable metric collection", response.data["message"])

    @patch.object(DisableMetricCollection, "post_job_to_metric_service")
    def test_disable_metric_collection_failure(self, mock_post):
        """Test POST with service failure"""
        mock_post.side_effect = Exception("Service error")

        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)


class GetMetricCollectionStatusTest(AuthenticatedMetricsTestCase):
    """Test GetMetricCollectionStatus view"""

    def setUp(self):
        super().setUp()
        self.url = reverse("metrics-collection-status")

    @patch.object(GetMetricCollectionStatus, "get_from_metric_service")
    def test_get_metric_collection_status_success(self, mock_get):
        """Test successful GET metric collection status"""
        mock_get.return_value = {"status": {"collect_metrics_and_sent_to_db": "running"}}

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "running")

    @patch.object(GetMetricCollectionStatus, "get_from_metric_service")
    def test_get_metric_collection_status_failure(self, mock_get):
        """Test failed GET metric collection status"""
        mock_get.side_effect = Exception("Service unavailable")

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)


class GetMetricTaskStatusTest(AuthenticatedMetricsTestCase):
    """Test GetMetricTaskStatus view"""

    def setUp(self):
        super().setUp()
        self.job_id = "test_job"
        self.url = reverse("metrics-poll-status", kwargs={"job_id": self.job_id})

    @patch.object(GetMetricTaskStatus, "get_from_metric_service")
    def test_get_metric_task_status_success(self, mock_get):
        """Test successful GET metric task status"""
        mock_get.return_value = {"status": "running"}

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {"status": "running"})

    @patch.object(GetMetricTaskStatus, "get_from_metric_service")
    def test_get_metric_task_status_failure(self, mock_get):
        """Test failed GET metric task status"""
        mock_get.side_effect = Exception("Service unavailable")

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)


class MetricViewAllRecentTest(AuthenticatedMetricsTestCase):
    """Test MetricViewAllRecent view"""

    def setUp(self):
        super().setUp()
        self.url = reverse("metrics-view-all-recent")

    @patch.object(MetricViewAllRecent, "get_from_metric_service")
    def test_get_all_recent_metrics_success(self, mock_get):
        """Test successful GET all recent metrics"""
        mock_get.return_value = [{"container": "test1", "cpu": "50%"}]

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    @patch.object(MetricViewAllRecent, "get_from_metric_service")
    def test_get_all_recent_metrics_truncated(self, mock_get):
        """Test GET all recent metrics with truncation"""
        # Create more than MAX_ALL_METRICS_LENGTH items
        mock_data = [{"container": f"test{i}", "cpu": "50%"} for i in range(150)]
        mock_get.return_value = mock_data

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should be truncated to MAX_ALL_METRICS_LENGTH (100)
        self.assertEqual(len(response.data), 100)

    @patch.object(MetricViewAllRecent, "get_from_metric_service")
    def test_get_all_recent_metrics_failure(self, mock_get):
        """Test failed GET all recent metrics"""
        mock_get.side_effect = Exception("Service unavailable")

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================================
# Permission Tests
# ============================================================================


class MetricsPermissionTest(APITestCase):
    """Test that metrics views require admin permission"""

    def test_container_status_requires_admin(self):
        """Test that container status endpoint requires admin permission"""
        url = reverse("container-status")
        response = self.client.get(url)
        # Should fail without admin permission
        self.assertIn(
            response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]
        )

    def test_chronos_health_requires_admin(self):
        """Test that chronos health endpoint requires admin permission"""
        url = reverse("chronos-health")
        response = self.client.get(url)
        self.assertIn(
            response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]
        )

    def test_disable_task_requires_admin(self):
        """Test that disable task endpoint requires admin permission"""
        url = reverse("disable-metrics-poll")
        response = self.client.post(url, {"job_id": "test"})
        self.assertIn(
            response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]
        )

    def test_enable_task_requires_admin(self):
        """Test that enable task endpoint requires admin permission"""
        url = reverse("enable-metrics-poll")
        response = self.client.post(url, {"job_id": "test"})
        self.assertIn(
            response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]
        )
