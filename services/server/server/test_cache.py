"""
Tests for cache utilities.
"""

import unittest
from unittest.mock import MagicMock, patch

from cache import CachedView, CacheHandler, DjangoCacheHandler


class CacheHandlerTests(unittest.TestCase):
    """Test CacheHandler abstract base class"""

    def test_cache_handler_is_abstract(self):
        """Test that CacheHandler cannot be instantiated directly"""
        # Act & Assert
        with self.assertRaises(TypeError):
            CacheHandler()


class CachedViewTests(unittest.TestCase):
    """Test CachedView abstract base class"""

    def test_cached_view_is_abstract(self):
        """Test that CachedView cannot be instantiated directly"""
        # Act & Assert
        with self.assertRaises(TypeError):
            CachedView()

    def test_cached_view_requires_generate_key(self):
        """Test that CachedView subclass must implement generate_key"""

        # Arrange
        class IncompleteCachedView(CachedView):
            pass

        # Act & Assert
        with self.assertRaises(TypeError):
            IncompleteCachedView()


class DjangoCacheHandlerTests(unittest.TestCase):
    """Test DjangoCacheHandler implementation"""

    @patch("cache.cache")
    def test_django_cache_handler_initialization(self, mock_cache):
        """Test DjangoCacheHandler initialization with expiration"""
        # Act
        handler = DjangoCacheHandler(expiration=3600)

        # Assert
        self.assertEqual(handler.expiration, 3600)

    @patch("cache.cache")
    def test_get_returns_cached_value(self, mock_cache):
        """Test get method returns value from Django cache"""
        # Arrange
        mock_cache.get.return_value = "cached_value"
        handler = DjangoCacheHandler(expiration=3600)

        # Act
        result = handler.get("test_key")

        # Assert
        self.assertEqual(result, "cached_value")
        mock_cache.get.assert_called_once_with("test_key")

    @patch("cache.cache")
    def test_get_returns_none_for_missing_key(self, mock_cache):
        """Test get method returns None for missing key"""
        # Arrange
        mock_cache.get.return_value = None
        handler = DjangoCacheHandler(expiration=3600)

        # Act
        result = handler.get("missing_key")

        # Assert
        self.assertIsNone(result)
        mock_cache.get.assert_called_once_with("missing_key")

    @patch("cache.cache")
    def test_set_stores_value_with_expiration(self, mock_cache):
        """Test set method stores value with timeout"""
        # Arrange
        mock_cache.set.return_value = True
        handler = DjangoCacheHandler(expiration=7200)

        # Act
        result = handler.set("test_key", "test_value")

        # Assert
        self.assertTrue(result)
        mock_cache.set.assert_called_once_with("test_key", "test_value", timeout=7200)

    @patch("cache.cache")
    def test_set_with_complex_value(self, mock_cache):
        """Test set method with complex data structures"""
        # Arrange
        mock_cache.set.return_value = True
        handler = DjangoCacheHandler(expiration=3600)
        complex_value = {"key": "value", "nested": {"data": [1, 2, 3]}}

        # Act
        result = handler.set("complex_key", complex_value)

        # Assert
        self.assertTrue(result)
        mock_cache.set.assert_called_once_with("complex_key", complex_value, timeout=3600)

    @patch("cache.cache")
    def test_get_set_round_trip(self, mock_cache):
        """Test setting and getting a value"""
        # Arrange
        handler = DjangoCacheHandler(expiration=3600)
        test_value = {"data": "test"}

        # Configure mock to return the value we set
        def mock_set(key, value, timeout):
            mock_cache.get.return_value = value
            return True

        mock_cache.set.side_effect = mock_set

        # Act
        handler.set("test_key", test_value)
        result = handler.get("test_key")

        # Assert
        self.assertEqual(result, test_value)

    @patch("cache.cache")
    def test_set_with_zero_expiration(self, mock_cache):
        """Test set method with zero expiration (cache forever)"""
        # Arrange
        mock_cache.set.return_value = True
        handler = DjangoCacheHandler(expiration=0)

        # Act
        result = handler.set("test_key", "test_value")

        # Assert
        self.assertTrue(result)
        mock_cache.set.assert_called_once_with("test_key", "test_value", timeout=0)

    @patch("cache.cache")
    def test_multiple_handlers_with_different_expirations(self, mock_cache):
        """Test multiple cache handlers with different expiration times"""
        # Arrange
        handler1 = DjangoCacheHandler(expiration=1800)
        handler2 = DjangoCacheHandler(expiration=3600)

        # Act
        handler1.set("key1", "value1")
        handler2.set("key2", "value2")

        # Assert
        self.assertEqual(mock_cache.set.call_count, 2)
        mock_cache.set.assert_any_call("key1", "value1", timeout=1800)
        mock_cache.set.assert_any_call("key2", "value2", timeout=3600)
