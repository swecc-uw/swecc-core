"""
Comprehensive tests for RabbitMQ message queue components.
"""

import asyncio
import json
import os
import sys
import unittest
import unittest.mock
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from pika.exchange_type import ExchangeType

# Mock Django models before importing mq.consumers
sys.modules["resume_review"] = MagicMock()
sys.modules["resume_review.models"] = MagicMock()


def async_test(coro):
    """Decorator to run async test methods"""

    def wrapper(*args, **kwargs):
        return asyncio.run(coro(*args, **kwargs))

    return wrapper


from .core.connection_manager import ConnectionManager
from .core.consumer import AsyncRabbitConsumer
from .core.manager import RabbitMQManager
from .core.producer import AsyncRabbitProducer
from .core.synchronous_producer import SynchronousRabbitProducer

# ============================================================================
# ConnectionManager Tests
# ============================================================================


class ConnectionManagerTests(unittest.TestCase):
    """Test ConnectionManager singleton and connection lifecycle"""

    def setUp(self):
        """Reset singleton instance before each test"""
        ConnectionManager.instance = None

    def tearDown(self):
        """Clean up singleton instance after each test"""
        ConnectionManager.instance = None

    @patch.dict(
        os.environ,
        {
            "SERVER_RABBIT_USER": "test_user",
            "SERVER_RABBIT_PASS": "test_pass",
            "RABBIT_HOST": "test_host",
            "RABBIT_PORT": "5672",
            "RABBIT_VHOST": "/",
        },
    )
    def test_connection_manager_singleton_pattern(self):
        """Test ConnectionManager follows singleton pattern"""
        # Act
        manager1 = ConnectionManager()
        manager2 = ConnectionManager()

        # Assert
        self.assertIs(manager1, manager2)

    @patch.dict(
        os.environ,
        {
            "SERVER_RABBIT_USER": "test_user",
            "SERVER_RABBIT_PASS": "test_pass",
            "RABBIT_HOST": "test_host",
            "RABBIT_PORT": "5672",
            "RABBIT_VHOST": "/",
        },
    )
    def test_build_amqp_url_default_values(self):
        """Test AMQP URL building with default values"""
        # Act
        manager = ConnectionManager()
        url = manager._build_amqp_url()

        # Assert - vhost "/" is URL-encoded to "%2F"
        self.assertEqual(url, "amqp://test_user:test_pass@test_host:5672/%2F")

    @patch.dict(
        os.environ,
        {
            "SERVER_RABBIT_USER": "  user  ",
            "SERVER_RABBIT_PASS": "  pass  ",
            "RABBIT_HOST": "  host  ",
            "RABBIT_PORT": "  5672  ",
            "RABBIT_VHOST": "  /  ",
        },
    )
    def test_build_amqp_url_strips_whitespace(self):
        """Test AMQP URL building strips whitespace from env vars"""
        # Act
        manager = ConnectionManager()
        url = manager._build_amqp_url()

        # Assert - vhost is stripped then URL-encoded
        self.assertEqual(url, "amqp://user:pass@host:5672/%2F")

    @patch.dict(
        os.environ,
        {
            "SERVER_RABBIT_USER": "user",
            "SERVER_RABBIT_PASS": "pass",
            "RABBIT_HOST": "host",
            "RABBIT_PORT": "5672",
            "RABBIT_VHOST": "/custom/vhost",
        },
    )
    def test_build_amqp_url_with_custom_vhost(self):
        """Test AMQP URL building with custom vhost"""
        # Act
        manager = ConnectionManager()
        url = manager._build_amqp_url()

        # Assert
        self.assertIn("%2Fcustom%2Fvhost", url)

    @patch.dict(os.environ, {}, clear=True)
    def test_build_amqp_url_uses_defaults_when_env_missing(self):
        """Test AMQP URL building uses defaults when env vars missing"""
        # Act
        manager = ConnectionManager()
        url = manager._build_amqp_url()

        # Assert - vhost "/" is URL-encoded to "%2F"
        self.assertEqual(url, "amqp://guest:guest@rabbitmq-host:5672/%2F")

    def test_connection_manager_initialization(self):
        """Test ConnectionManager initialization state"""
        # Act
        manager = ConnectionManager()

        # Assert
        self.assertIsNone(manager._connection)
        self.assertFalse(manager._closing)
        self.assertFalse(manager._connected)
        self.assertIsNotNone(manager._ready)
        self.assertTrue(manager._initialized)

    def test_is_connected_initially_false(self):
        """Test is_connected returns False initially"""
        # Act
        manager = ConnectionManager()

        # Assert
        self.assertFalse(manager.is_connected())

    def test_on_connection_open_sets_connected(self):
        """Test on_connection_open callback sets connected state"""
        # Arrange
        manager = ConnectionManager()
        mock_connection = MagicMock()

        # Act
        manager.on_connection_open(mock_connection)

        # Assert
        self.assertTrue(manager._connected)
        self.assertTrue(manager._ready.is_set())

    def test_on_connection_open_error_sets_disconnected(self):
        """Test on_connection_open_error callback sets disconnected state"""
        # Arrange
        manager = ConnectionManager()
        mock_connection = MagicMock()
        error = Exception("Connection failed")

        # Act
        manager.on_connection_open_error(mock_connection, error)

        # Assert
        self.assertFalse(manager._connected)

    def test_on_connection_closed_when_closing(self):
        """Test on_connection_closed when intentionally closing"""
        # Arrange
        manager = ConnectionManager()
        manager._closing = True
        mock_connection = MagicMock()

        # Act
        manager.on_connection_closed(mock_connection, "Normal shutdown")

        # Assert
        self.assertFalse(manager._connected)

    def test_on_connection_closed_unexpected(self):
        """Test on_connection_closed when connection drops unexpectedly"""
        # Arrange
        manager = ConnectionManager()
        manager._closing = False
        manager._connected = True
        mock_connection = MagicMock()

        # Act
        manager.on_connection_closed(mock_connection, "Connection lost")

        # Assert
        self.assertFalse(manager._connected)


# ============================================================================
# AsyncRabbitProducer Tests
# ============================================================================


class AsyncRabbitProducerTests(unittest.TestCase):
    """Test AsyncRabbitProducer"""

    def setUp(self):
        """Reset ConnectionManager singleton before each test"""
        ConnectionManager.instance = None

    def tearDown(self):
        """Clean up ConnectionManager singleton after each test"""
        ConnectionManager.instance = None

    def test_producer_initialization(self):
        """Test AsyncRabbitProducer initialization"""
        # Act
        producer = AsyncRabbitProducer(
            amqp_url="amqp://guest:guest@localhost:5672/",
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            routing_key="test.key",
        )

        # Assert
        self.assertEqual(producer._url, "amqp://guest:guest@localhost:5672/")
        self.assertEqual(producer._exchange, "test-exchange")
        self.assertEqual(producer._exchange_type, ExchangeType.topic)
        self.assertEqual(producer._default_routing_key, "test.key")
        self.assertFalse(producer._connected)
        self.assertIsNone(producer._connection)
        self.assertIsNone(producer._channel)

    def test_producer_initialization_without_routing_key(self):
        """Test AsyncRabbitProducer initialization without default routing key"""
        # Act
        producer = AsyncRabbitProducer(
            amqp_url="amqp://guest:guest@localhost:5672/",
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
        )

        # Assert
        self.assertIsNone(producer._default_routing_key)

    def test_on_channel_open_sets_channel(self):
        """Test on_channel_open callback sets channel"""
        # Arrange
        producer = AsyncRabbitProducer(
            amqp_url="amqp://guest:guest@localhost:5672/",
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
        )
        mock_channel = MagicMock()

        # Act
        producer.on_channel_open(mock_channel)

        # Assert
        self.assertEqual(producer._channel, mock_channel)
        mock_channel.add_on_close_callback.assert_called_once()

    def test_on_channel_closed_clears_channel(self):
        """Test on_channel_closed callback clears channel"""
        # Arrange
        producer = AsyncRabbitProducer(
            amqp_url="amqp://guest:guest@localhost:5672/",
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
        )
        mock_channel = MagicMock()
        producer._channel = mock_channel

        # Act
        producer.on_channel_closed(mock_channel, "Channel closed")

        # Assert
        self.assertIsNone(producer._channel)

    def test_on_exchange_declareok_sets_ready(self):
        """Test on_exchange_declareok sets ready event"""
        # Arrange
        producer = AsyncRabbitProducer(
            amqp_url="amqp://guest:guest@localhost:5672/",
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
        )
        mock_frame = MagicMock()

        # Act
        producer.on_exchange_declareok(mock_frame)

        # Assert
        self.assertTrue(producer._ready.is_set())


# ============================================================================
# AsyncRabbitConsumer Tests
# ============================================================================


class AsyncRabbitConsumerTests(unittest.TestCase):
    """Test AsyncRabbitConsumer"""

    def setUp(self):
        """Reset ConnectionManager singleton before each test"""
        ConnectionManager.instance = None

    def tearDown(self):
        """Clean up ConnectionManager singleton after each test"""
        ConnectionManager.instance = None

    async def async_callback(self, body, properties):
        """Test callback for consumer"""
        pass

    def test_consumer_initialization(self):
        """Test AsyncRabbitConsumer initialization"""
        # Act
        consumer = AsyncRabbitConsumer(
            amqp_url="amqp://guest:guest@localhost:5672/",
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
            callback=self.async_callback,
            prefetch_count=5,
        )

        # Assert
        self.assertEqual(consumer._url, "amqp://guest:guest@localhost:5672/")
        self.assertEqual(consumer._exchange, "test-exchange")
        self.assertEqual(consumer._queue, "test-queue")
        self.assertEqual(consumer._routing_key, "test.key")
        self.assertEqual(consumer._prefetch_count, 5)
        self.assertTrue(consumer._declare_exchange)
        self.assertIsNone(consumer._connection)
        self.assertIsNone(consumer._channel)
        self.assertFalse(consumer._closing)

    def test_consumer_initialization_default_prefetch(self):
        """Test AsyncRabbitConsumer initialization with default prefetch"""
        # Act
        consumer = AsyncRabbitConsumer(
            amqp_url="amqp://guest:guest@localhost:5672/",
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
            callback=self.async_callback,
        )

        # Assert
        self.assertEqual(consumer._prefetch_count, 1)

    def test_on_channel_open_sets_channel(self):
        """Test on_channel_open callback sets channel"""
        # Arrange
        consumer = AsyncRabbitConsumer(
            amqp_url="amqp://guest:guest@localhost:5672/",
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
            callback=self.async_callback,
        )
        mock_channel = MagicMock()

        # Act
        consumer.on_channel_open(mock_channel)

        # Assert
        self.assertEqual(consumer._channel, mock_channel)
        mock_channel.add_on_close_callback.assert_called_once()

    def test_on_channel_closed_logs_reason(self):
        """Test on_channel_closed callback"""
        # Arrange
        consumer = AsyncRabbitConsumer(
            amqp_url="amqp://guest:guest@localhost:5672/",
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
            callback=self.async_callback,
        )
        mock_channel = MagicMock()

        # Act - should not raise exception
        consumer.on_channel_closed(mock_channel, "Channel closed")

        # Assert - just verify it doesn't crash
        self.assertTrue(True)

    def test_setup_exchange_when_declare_is_true(self):
        """Test setup_exchange declares exchange when flag is True"""
        # Arrange
        consumer = AsyncRabbitConsumer(
            amqp_url="amqp://guest:guest@localhost:5672/",
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
            callback=self.async_callback,
        )
        mock_channel = MagicMock()
        consumer._channel = mock_channel

        # Act
        consumer.setup_exchange("test-exchange")

        # Assert
        mock_channel.exchange_declare.assert_called_once()

    def test_setup_exchange_when_declare_is_false(self):
        """Test setup_exchange skips declaration when flag is False"""
        # Arrange
        consumer = AsyncRabbitConsumer(
            amqp_url="amqp://guest:guest@localhost:5672/",
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            declare_exchange=False,
            queue="test-queue",
            routing_key="test.key",
            callback=self.async_callback,
        )
        mock_channel = MagicMock()
        consumer._channel = mock_channel

        # Act
        consumer.setup_exchange("test-exchange")

        # Assert
        mock_channel.exchange_declare.assert_not_called()

    def test_on_exchange_declareok_calls_setup_queue(self):
        """Test on_exchange_declareok proceeds to queue setup"""
        # Arrange
        consumer = AsyncRabbitConsumer(
            amqp_url="amqp://guest:guest@localhost:5672/",
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
            callback=self.async_callback,
        )
        mock_channel = MagicMock()
        consumer._channel = mock_channel
        mock_frame = MagicMock()

        # Act
        consumer.on_exchange_declareok(mock_frame, exchange_name="test-exchange")

        # Assert
        mock_channel.queue_declare.assert_called_once()

    def test_setup_queue_declares_queue(self):
        """Test setup_queue declares the queue"""
        # Arrange
        consumer = AsyncRabbitConsumer(
            amqp_url="amqp://guest:guest@localhost:5672/",
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
            callback=self.async_callback,
        )
        mock_channel = MagicMock()
        consumer._channel = mock_channel

        # Act
        consumer.setup_queue("test-queue")

        # Assert
        mock_channel.queue_declare.assert_called_once_with(
            queue="test-queue", callback=unittest.mock.ANY
        )

    def test_on_queue_declareok_binds_queue(self):
        """Test on_queue_declareok binds queue to exchange"""
        # Arrange
        consumer = AsyncRabbitConsumer(
            amqp_url="amqp://guest:guest@localhost:5672/",
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
            callback=self.async_callback,
        )
        mock_channel = MagicMock()
        consumer._channel = mock_channel
        mock_frame = MagicMock()

        # Act
        consumer.on_queue_declareok(mock_frame, queue_name="test-queue")

        # Assert
        mock_channel.queue_bind.assert_called_once()

    def test_on_bindok_sets_qos(self):
        """Test on_bindok sets QoS"""
        # Arrange
        consumer = AsyncRabbitConsumer(
            amqp_url="amqp://guest:guest@localhost:5672/",
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
            callback=self.async_callback,
            prefetch_count=10,
        )
        mock_channel = MagicMock()
        consumer._channel = mock_channel
        mock_frame = MagicMock()

        # Act
        consumer.on_bindok(mock_frame, queue_name="test-queue")

        # Assert
        mock_channel.basic_qos.assert_called_once_with(
            prefetch_count=10, callback=unittest.mock.ANY
        )


# ============================================================================
# SynchronousRabbitProducer Tests
# ============================================================================


class SynchronousRabbitProducerTests(unittest.TestCase):
    """Test SynchronousRabbitProducer"""

    def setUp(self):
        """Reset singleton instance before each test"""
        SynchronousRabbitProducer._instance = None

    def tearDown(self):
        """Clean up singleton instance after each test"""
        SynchronousRabbitProducer._instance = None

    @patch.dict(os.environ, {"RABBIT_HOST": "test-host"})
    @patch("mq.core.synchronous_producer.pika.BlockingConnection")
    def test_synchronous_producer_singleton_pattern(self, mock_blocking_connection):
        """Test SynchronousRabbitProducer follows singleton pattern"""
        # Arrange
        mock_connection = MagicMock()
        mock_channel = MagicMock()
        mock_connection.channel.return_value = mock_channel
        mock_blocking_connection.return_value = mock_connection

        # Act
        producer1 = SynchronousRabbitProducer()
        producer2 = SynchronousRabbitProducer()

        # Assert
        self.assertIs(producer1, producer2)
        # Connection should only be created once
        self.assertEqual(mock_blocking_connection.call_count, 1)

    @patch.dict(os.environ, {"RABBIT_HOST": "custom-host"})
    @patch("mq.core.synchronous_producer.pika.BlockingConnection")
    def test_synchronous_producer_initialization(self, mock_blocking_connection):
        """Test SynchronousRabbitProducer initialization"""
        # Arrange
        mock_connection = MagicMock()
        mock_channel = MagicMock()
        mock_connection.channel.return_value = mock_channel
        mock_blocking_connection.return_value = mock_connection

        # Act - __new__ doesn't accept parameters, they go to __init__
        producer = SynchronousRabbitProducer()

        # Assert
        self.assertEqual(producer.host, "custom-host")
        self.assertTrue(producer._initialized)
        self.assertIsNotNone(producer._connection)
        self.assertIsNotNone(producer._channel)

    @patch.dict(os.environ, {}, clear=True)
    @patch("mq.core.synchronous_producer.pika.BlockingConnection")
    def test_synchronous_producer_default_host(self, mock_blocking_connection):
        """Test SynchronousRabbitProducer uses default host"""
        # Arrange
        mock_connection = MagicMock()
        mock_channel = MagicMock()
        mock_connection.channel.return_value = mock_channel
        mock_blocking_connection.return_value = mock_connection

        # Act
        producer = SynchronousRabbitProducer()

        # Assert
        self.assertEqual(producer.host, "rabbitmq-host")

    @patch.dict(os.environ, {"RABBIT_HOST": "test-host"})
    @patch("mq.core.synchronous_producer.pika.BlockingConnection")
    def test_publish_success(self, mock_blocking_connection):
        """Test successful message publishing"""
        # Arrange
        mock_connection = MagicMock()
        mock_channel = MagicMock()
        mock_connection.is_closed = False
        mock_channel.is_closed = False
        mock_connection.channel.return_value = mock_channel
        mock_blocking_connection.return_value = mock_connection

        producer = SynchronousRabbitProducer()

        # Act
        producer.publish("test.routing.key", "test message body")

        # Assert
        mock_channel.basic_publish.assert_called_once_with(
            exchange="swecc-server-exchange",
            routing_key="test.routing.key",
            body="test message body",
        )

    @patch.dict(os.environ, {"RABBIT_HOST": "test-host"})
    @patch("mq.core.synchronous_producer.pika.BlockingConnection")
    def test_publish_with_custom_exchange(self, mock_blocking_connection):
        """Test publishing with custom exchange"""
        # Arrange
        mock_connection = MagicMock()
        mock_channel = MagicMock()
        mock_connection.is_closed = False
        mock_channel.is_closed = False
        mock_connection.channel.return_value = mock_channel
        mock_blocking_connection.return_value = mock_connection

        producer = SynchronousRabbitProducer()

        # Act
        producer.publish("test.key", "test body", exchange="custom-exchange")

        # Assert
        mock_channel.basic_publish.assert_called_once_with(
            exchange="custom-exchange", routing_key="test.key", body="test body"
        )

    @patch.dict(os.environ, {"RABBIT_HOST": "test-host"})
    @patch("mq.core.synchronous_producer.pika.BlockingConnection")
    def test_publish_reconnects_when_connection_closed(self, mock_blocking_connection):
        """Test publish reconnects when connection is closed"""
        # Arrange
        mock_connection1 = MagicMock()
        mock_connection2 = MagicMock()
        mock_channel1 = MagicMock()
        mock_channel2 = MagicMock()

        mock_connection1.is_closed = True
        mock_connection2.is_closed = False
        mock_channel2.is_closed = False

        mock_connection1.channel.return_value = mock_channel1
        mock_connection2.channel.return_value = mock_channel2

        mock_blocking_connection.side_effect = [mock_connection1, mock_connection2]

        producer = SynchronousRabbitProducer()

        # Act
        producer.publish("test.key", "test body")

        # Assert
        self.assertEqual(mock_blocking_connection.call_count, 2)
        mock_channel2.basic_publish.assert_called_once()

    @patch.dict(os.environ, {"RABBIT_HOST": "test-host"})
    @patch("mq.core.synchronous_producer.pika.BlockingConnection")
    def test_publish_retries_on_failure(self, mock_blocking_connection):
        """Test publish retries once on failure"""
        # Arrange
        mock_connection = MagicMock()
        mock_channel = MagicMock()
        mock_connection.is_closed = False
        mock_channel.is_closed = False
        mock_connection.channel.return_value = mock_channel
        mock_blocking_connection.return_value = mock_connection

        # First call fails, second succeeds
        mock_channel.basic_publish.side_effect = [Exception("Publish failed"), None]

        producer = SynchronousRabbitProducer()

        # Act
        producer.publish("test.key", "test body")

        # Assert
        self.assertEqual(mock_channel.basic_publish.call_count, 2)
        self.assertEqual(mock_blocking_connection.call_count, 2)  # Reconnects on failure


# ============================================================================
# RabbitMQManager Tests
# ============================================================================


class RabbitMQManagerTests(unittest.TestCase):
    """Test RabbitMQManager"""

    def setUp(self):
        """Reset ConnectionManager singleton before each test"""
        ConnectionManager.instance = None

    def tearDown(self):
        """Clean up ConnectionManager singleton after each test"""
        ConnectionManager.instance = None

    @patch.dict(
        os.environ,
        {
            "SERVER_RABBIT_USER": "test_user",
            "SERVER_RABBIT_PASS": "test_pass",
            "RABBIT_HOST": "test_host",
            "RABBIT_PORT": "5672",
            "RABBIT_VHOST": "/",
        },
    )
    def test_manager_initialization(self):
        """Test RabbitMQManager initialization"""
        # Act
        manager = RabbitMQManager()

        # Assert
        self.assertIsInstance(manager.consumers, dict)
        self.assertIsInstance(manager.producers, dict)
        self.assertIsInstance(manager.callbacks, dict)
        self.assertIsInstance(manager.producer_factories, dict)
        self.assertEqual(len(manager.consumers), 0)
        self.assertEqual(len(manager.producers), 0)

    @patch.dict(
        os.environ,
        {
            "SERVER_RABBIT_USER": "user",
            "SERVER_RABBIT_PASS": "pass",
            "RABBIT_HOST": "host",
            "RABBIT_PORT": "5672",
            "RABBIT_VHOST": "/test",
        },
    )
    def test_build_amqp_url(self):
        """Test _build_amqp_url method"""
        # Act
        manager = RabbitMQManager()
        url = manager._build_amqp_url()

        # Assert
        self.assertIn("user", url)
        self.assertIn("pass", url)
        self.assertIn("host", url)
        self.assertIn("5672", url)

    def test_register_callback_decorator(self):
        """Test register_callback decorator"""
        # Arrange
        manager = RabbitMQManager()

        # Act
        @manager.register_callback(
            exchange="test-exchange",
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
            exchange_type=ExchangeType.topic,
        )
        async def test_callback(body, properties):
            pass

        # Assert
        callback_name = f"{test_callback.__module__}.{test_callback.__name__}"
        self.assertIn(callback_name, manager.callbacks)
        self.assertEqual(manager.callbacks[callback_name]["exchange"], "test-exchange")
        self.assertEqual(manager.callbacks[callback_name]["queue"], "test-queue")
        self.assertEqual(manager.callbacks[callback_name]["routing_key"], "test.key")

    def test_register_producer_decorator(self):
        """Test register_producer decorator"""
        # Arrange
        manager = RabbitMQManager()

        # Act
        @manager.register_producer(
            exchange="test-exchange", exchange_type=ExchangeType.topic, routing_key="test.key"
        )
        async def test_producer(message):
            return message

        # Assert - the decorator registers with the original function's module and name
        producer_name = "mq.tests.test_producer"
        self.assertIn(producer_name, manager.producer_factories)

    def test_add_consumer_success(self):
        """Test adding a consumer"""
        # Arrange
        manager = RabbitMQManager()

        async def test_callback(body, properties):
            pass

        # Act
        consumer = manager.add_consumer(
            name="test-consumer",
            callback=test_callback,
            exchange="test-exchange",
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
        )

        # Assert
        self.assertIn("test-consumer", manager.consumers)
        self.assertIsInstance(consumer, AsyncRabbitConsumer)

    def test_add_consumer_duplicate_name_raises_error(self):
        """Test adding consumer with duplicate name raises ValueError"""
        # Arrange
        manager = RabbitMQManager()

        async def test_callback(body, properties):
            pass

        manager.add_consumer(
            name="test-consumer",
            callback=test_callback,
            exchange="test-exchange",
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
        )

        # Act & Assert
        with self.assertRaises(ValueError) as context:
            manager.add_consumer(
                name="test-consumer",
                callback=test_callback,
                exchange="test-exchange",
                declare_exchange=True,
                queue="test-queue",
                routing_key="test.key",
            )
        self.assertIn("already exists", str(context.exception))

    def test_get_or_create_producer_creates_new(self):
        """Test get_or_create_producer creates new producer"""
        # Arrange
        manager = RabbitMQManager()

        # Act
        producer = manager.get_or_create_producer(
            name="test-producer",
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            routing_key="test.key",
        )

        # Assert
        self.assertIn("test-producer", manager.producers)
        self.assertIsInstance(producer, AsyncRabbitProducer)

    def test_get_or_create_producer_returns_existing(self):
        """Test get_or_create_producer returns existing producer"""
        # Arrange
        manager = RabbitMQManager()
        producer1 = manager.get_or_create_producer(
            name="test-producer",
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            routing_key="test.key",
        )

        # Act
        producer2 = manager.get_or_create_producer(
            name="test-producer",
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            routing_key="test.key",
        )

        # Assert
        self.assertIs(producer1, producer2)

    def test_create_consumers_from_callbacks(self):
        """Test create_consumers creates consumers from registered callbacks"""
        # Arrange
        manager = RabbitMQManager()

        @manager.register_callback(
            exchange="test-exchange",
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
        )
        async def test_callback(body, properties):
            pass

        # Act
        manager.create_consumers()

        # Assert
        self.assertEqual(len(manager.consumers), 1)
        callback_name = f"{test_callback.__module__}.{test_callback.__name__}"
        self.assertIn(callback_name, manager.consumers)


# ============================================================================
# Producers Module Tests
# ============================================================================


class ProducersModuleTests(unittest.TestCase):
    """Test producers.py module functions"""

    @patch("mq.producers.SynchronousRabbitProducer")
    def test_publish_verified_email(self, mock_producer_class):
        """Test publish_verified_email function"""
        # Arrange
        from .producers import publish_verified_email

        mock_producer = MagicMock()
        mock_producer_class.return_value = mock_producer

        # Act
        publish_verified_email("123456789")

        # Assert
        mock_producer.publish.assert_called_once_with("server.verified-email", "123456789")

    @patch("mq.producers.DJANGO_DEBUG", True)
    @patch("mq.producers.SynchronousRabbitProducer")
    def test_dev_publish_to_review_resume_in_debug_mode(self, mock_producer_class):
        """Test dev_publish_to_review_resume in debug mode"""
        # Arrange
        from .producers import dev_publish_to_review_resume

        mock_producer = MagicMock()
        mock_producer_class.return_value = mock_producer

        # Act
        dev_publish_to_review_resume("test-key")

        # Assert
        mock_producer.publish.assert_called_once()
        call_args = mock_producer.publish.call_args
        self.assertEqual(call_args[0][0], "to-review")
        self.assertIn("test-key", call_args[0][1])
        self.assertEqual(call_args[1]["exchange"], "swecc-ai-exchange")

    @patch("mq.producers.DJANGO_DEBUG", False)
    @patch("mq.producers.SynchronousRabbitProducer")
    def test_dev_publish_to_review_resume_in_production_mode(self, mock_producer_class):
        """Test dev_publish_to_review_resume does nothing in production"""
        # Arrange
        from .producers import dev_publish_to_review_resume

        mock_producer = MagicMock()
        mock_producer_class.return_value = mock_producer

        # Act
        dev_publish_to_review_resume("test-key")

        # Assert
        mock_producer.publish.assert_not_called()


# ============================================================================
# Consumers Module Tests
# ============================================================================


class ConsumersModuleTests(unittest.TestCase):
    """Test consumers.py module functions"""

    @async_test
    @patch("mq.consumers.logger")
    async def test_verified_email_callback(self, mock_logger):
        """Test verified_email_callback function"""
        # Arrange
        from .consumers import verified_email_callback

        mock_properties = MagicMock()

        # Act
        await verified_email_callback(b"test message", mock_properties)

        # Assert
        mock_logger.info.assert_called_once()
        self.assertIn("test message", str(mock_logger.info.call_args))

    @async_test
    @patch("mq.consumers.Resume")
    @patch("mq.consumers.logger")
    async def test_reviewed_feedback_success(self, mock_logger, mock_resume_model):
        """Test reviewed_feedback with valid message"""
        # Arrange
        from .consumers import reviewed_feedback

        mock_properties = MagicMock()
        mock_resume = MagicMock()
        mock_resume.member.id = 123
        mock_resume.file_name = "resume.pdf"
        mock_resume_model.objects.filter.return_value.first.return_value = mock_resume

        message_body = json.dumps(
            {"feedback": "Great resume!", "key": "123-456-resume.pdf"}
        ).encode("utf-8")

        # Act
        await reviewed_feedback(message_body, mock_properties)

        # Assert
        mock_logger.info.assert_called()

    @async_test
    @patch("mq.consumers.logger")
    async def test_reviewed_feedback_invalid_json(self, mock_logger):
        """Test reviewed_feedback with invalid JSON"""
        # Arrange
        from .consumers import reviewed_feedback

        mock_properties = MagicMock()
        message_body = b"invalid json"

        # Act
        await reviewed_feedback(message_body, mock_properties)

        # Assert
        mock_logger.error.assert_called()
        self.assertIn("Failed to decode JSON", str(mock_logger.error.call_args))

    @async_test
    @patch("mq.consumers.logger")
    async def test_reviewed_feedback_missing_feedback(self, mock_logger):
        """Test reviewed_feedback with missing feedback field"""
        # Arrange
        from .consumers import reviewed_feedback

        mock_properties = MagicMock()
        message_body = json.dumps({"key": "123-456-resume.pdf"}).encode("utf-8")

        # Act
        await reviewed_feedback(message_body, mock_properties)

        # Assert
        mock_logger.error.assert_called()
        self.assertIn("Feedback or key not found", str(mock_logger.error.call_args))

    @async_test
    @patch("mq.consumers.logger")
    async def test_reviewed_feedback_missing_key(self, mock_logger):
        """Test reviewed_feedback with missing key field"""
        # Arrange
        from .consumers import reviewed_feedback

        mock_properties = MagicMock()
        message_body = json.dumps({"feedback": "Great resume!"}).encode("utf-8")

        # Act
        await reviewed_feedback(message_body, mock_properties)

        # Assert
        mock_logger.error.assert_called()
        self.assertIn("Feedback or key not found", str(mock_logger.error.call_args))

    @async_test
    @patch("mq.consumers.Resume")
    @patch("mq.consumers.logger")
    async def test_reviewed_feedback_resume_not_found(self, mock_logger, mock_resume_model):
        """Test reviewed_feedback when resume doesn't exist"""
        # Arrange
        from .consumers import reviewed_feedback

        mock_properties = MagicMock()
        mock_resume_model.objects.filter.return_value.first.return_value = None

        message_body = json.dumps(
            {"feedback": "Great resume!", "key": "123-456-resume.pdf"}
        ).encode("utf-8")

        # Act
        await reviewed_feedback(message_body, mock_properties)

        # Assert
        mock_logger.error.assert_called()
        self.assertIn("Resume with ID", str(mock_logger.error.call_args))
