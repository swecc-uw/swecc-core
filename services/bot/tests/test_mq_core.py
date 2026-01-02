"""Tests for MQ core components."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, Mock, call, patch

import pika
import pytest
from mq.core.connection_manager import ConnectionManager
from mq.core.consumer import AsyncRabbitConsumer
from mq.core.manager import RabbitMQManager
from mq.core.producer import AsyncRabbitProducer
from pika.exchange_type import ExchangeType


@pytest.fixture
def reset_connection_manager():
    """Reset ConnectionManager singleton between tests."""
    ConnectionManager.instance = None
    yield
    ConnectionManager.instance = None


@pytest.fixture
def mock_env_rabbitmq(monkeypatch):
    """Mock RabbitMQ environment variables."""
    monkeypatch.setenv("BOT_RABBIT_USER", "test_user")
    monkeypatch.setenv("BOT_RABBIT_PASS", "test_pass")
    monkeypatch.setenv("RABBIT_HOST", "test-host")
    monkeypatch.setenv("RABBIT_PORT", "5672")
    monkeypatch.setenv("RABBIT_VHOST", "/test")


class TestConnectionManager:
    """Test suite for ConnectionManager."""

    def test_connection_manager_singleton(self, reset_connection_manager):
        """Test that ConnectionManager is a singleton."""
        # Arrange & Act
        manager1 = ConnectionManager()
        manager2 = ConnectionManager()

        # Assert
        assert manager1 is manager2
        assert ConnectionManager.instance is manager1

    def test_connection_manager_initialization(self, reset_connection_manager, mock_env_rabbitmq):
        """Test ConnectionManager initialization."""
        # Arrange & Act
        manager = ConnectionManager()

        # Assert
        assert manager._connection is None
        assert manager._closing is False
        assert manager._connected is False
        assert manager.initialized is True
        assert "test_user:test_pass@test-host:5672" in manager._url

    def test_build_amqp_url(self, reset_connection_manager, mock_env_rabbitmq):
        """Test AMQP URL building with environment variables."""
        # Arrange & Act
        manager = ConnectionManager()

        # Assert
        assert "amqp://test_user:test_pass@test-host:5672" in manager._url
        assert "%2Ftest" in manager._url  # URL-encoded /test

    def test_build_amqp_url_defaults(self, reset_connection_manager, monkeypatch):
        """Test AMQP URL building with default values."""
        # Arrange
        monkeypatch.delenv("BOT_RABBIT_USER", raising=False)
        monkeypatch.delenv("BOT_RABBIT_PASS", raising=False)
        monkeypatch.delenv("RABBIT_HOST", raising=False)
        monkeypatch.delenv("RABBIT_PORT", raising=False)
        monkeypatch.delenv("RABBIT_VHOST", raising=False)

        # Act
        manager = ConnectionManager()

        # Assert
        assert "amqp://guest:guest@rabbitmq-host:5672" in manager._url

    @pytest.mark.asyncio
    async def test_connect_creates_connection(self, reset_connection_manager, mock_env_rabbitmq):
        """Test that connect creates a new connection."""
        # Arrange
        manager = ConnectionManager()
        mock_connection = MagicMock()
        mock_connection.is_closed = False
        mock_connection.is_closing = False

        with patch("mq.core.connection_manager.AsyncioConnection") as mock_async_conn:
            mock_async_conn.return_value = mock_connection

            # Simulate connection opening
            def simulate_open(*args, **kwargs):
                on_open = kwargs.get("on_open_callback")
                if on_open:
                    on_open(mock_connection)
                return mock_connection

            mock_async_conn.side_effect = simulate_open

            # Act
            result = await manager.connect()

            # Assert
            assert result is mock_connection
            assert manager._connected is True
            mock_async_conn.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_reuses_existing_connection(
        self, reset_connection_manager, mock_env_rabbitmq
    ):
        """Test that connect reuses existing open connection."""
        # Arrange
        manager = ConnectionManager()
        mock_connection = MagicMock()
        mock_connection.is_closed = False
        mock_connection.is_closing = False
        manager._connection = mock_connection

        # Act
        result = await manager.connect()

        # Assert
        assert result is mock_connection

    def test_on_connection_open(self, reset_connection_manager, mock_env_rabbitmq):
        """Test connection open callback."""
        # Arrange
        manager = ConnectionManager()
        mock_connection = MagicMock()

        # Act
        manager.on_connection_open(mock_connection)

        # Assert
        assert manager._connected is True
        assert manager._ready.is_set()

    def test_on_connection_open_error(self, reset_connection_manager, mock_env_rabbitmq):
        """Test connection open error callback."""
        # Arrange
        manager = ConnectionManager()
        mock_connection = MagicMock()
        error = Exception("Connection failed")

        # Act
        manager.on_connection_open_error(mock_connection, error)

        # Assert
        assert manager._connected is False
        assert manager._ready.is_set()

    def test_on_connection_closed_graceful(self, reset_connection_manager, mock_env_rabbitmq):
        """Test graceful connection close callback."""
        # Arrange
        manager = ConnectionManager()
        manager._closing = True
        mock_connection = MagicMock()

        # Act
        manager.on_connection_closed(mock_connection, "Normal shutdown")

        # Assert
        assert manager._connected is False

    def test_on_connection_closed_unexpected(self, reset_connection_manager, mock_env_rabbitmq):
        """Test unexpected connection close callback."""
        # Arrange
        manager = ConnectionManager()
        manager._closing = False
        mock_connection = MagicMock()

        # Act
        manager.on_connection_closed(mock_connection, "Connection lost")

        # Assert
        assert manager._connected is False

    @pytest.mark.asyncio
    async def test_close_connection(self, reset_connection_manager, mock_env_rabbitmq):
        """Test closing connection."""
        # Arrange
        manager = ConnectionManager()
        mock_connection = MagicMock()
        mock_connection.is_closing = False
        mock_connection.is_closed = False
        manager._connection = mock_connection

        # Act
        await manager.close()

        # Assert
        assert manager._closing is True
        assert manager._connected is False
        mock_connection.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_already_closed_connection(
        self, reset_connection_manager, mock_env_rabbitmq
    ):
        """Test closing already closed connection."""
        # Arrange
        manager = ConnectionManager()
        mock_connection = MagicMock()
        mock_connection.is_closed = True
        manager._connection = mock_connection

        # Act
        await manager.close()

        # Assert
        assert manager._closing is True
        assert manager._connected is False
        mock_connection.close.assert_not_called()

    def test_is_connected(self, reset_connection_manager, mock_env_rabbitmq):
        """Test is_connected method."""
        # Arrange
        manager = ConnectionManager()

        # Act & Assert
        assert manager.is_connected() is False

        manager._connected = True
        assert manager.is_connected() is True


class TestAsyncRabbitProducer:
    """Test suite for AsyncRabbitProducer."""

    @pytest.fixture
    def mock_connection_manager(self):
        """Mock ConnectionManager for producer tests."""
        with patch("mq.core.producer.ConnectionManager") as mock_cm:
            mock_instance = MagicMock()
            mock_connection = MagicMock()
            mock_connection.is_closed = False
            mock_connection.is_closing = False
            mock_instance.connect = AsyncMock(return_value=mock_connection)
            mock_cm.return_value = mock_instance
            yield mock_cm

    def test_producer_initialization(self):
        """Test AsyncRabbitProducer initialization."""
        # Arrange & Act
        producer = AsyncRabbitProducer(
            amqp_url="amqp://test",
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            routing_key="test.key",
        )

        # Assert
        assert producer._url == "amqp://test"
        assert producer._exchange == "test-exchange"
        assert producer._exchange_type == ExchangeType.topic
        assert producer._default_routing_key == "test.key"
        assert producer._connection is None
        assert producer._channel is None
        assert producer._connected is False

    @pytest.mark.asyncio
    async def test_producer_connect_success(self, mock_connection_manager):
        """Test producer connection success."""
        # Arrange
        producer = AsyncRabbitProducer(
            amqp_url="amqp://test", exchange="test-exchange", exchange_type=ExchangeType.topic
        )
        mock_channel = MagicMock()

        # Simulate channel opening
        def simulate_channel_open(*args, **kwargs):
            on_open = kwargs.get("on_open_callback")
            if on_open:
                on_open(mock_channel)

        mock_connection = mock_connection_manager.return_value.connect.return_value
        mock_connection.channel = MagicMock(side_effect=simulate_channel_open)

        # Simulate exchange declaration
        def simulate_exchange_declare(*args, **kwargs):
            callback = kwargs.get("callback")
            if callback:
                callback(None)

        mock_channel.exchange_declare = MagicMock(side_effect=simulate_exchange_declare)
        mock_channel.add_on_close_callback = MagicMock()

        # Act
        result = await producer.connect()

        # Assert
        assert producer._connected is True
        assert result is not None

    @pytest.mark.asyncio
    async def test_producer_connect_reuses_connection(self, mock_connection_manager):
        """Test that producer reuses existing connection."""
        # Arrange
        producer = AsyncRabbitProducer(
            amqp_url="amqp://test", exchange="test-exchange", exchange_type=ExchangeType.topic
        )
        mock_connection = MagicMock()
        producer._connected = True
        producer._connection = mock_connection

        # Act
        result = await producer.connect()

        # Assert
        assert result is mock_connection
        # Should not create new connection
        mock_connection_manager.return_value.connect.assert_not_called()

    def test_producer_on_channel_open(self):
        """Test producer channel open callback."""
        # Arrange
        producer = AsyncRabbitProducer(
            amqp_url="amqp://test", exchange="test-exchange", exchange_type=ExchangeType.topic
        )
        mock_channel = MagicMock()
        mock_channel.exchange_declare = MagicMock()

        # Act
        producer.on_channel_open(mock_channel)

        # Assert
        assert producer._channel is mock_channel
        mock_channel.add_on_close_callback.assert_called_once()
        mock_channel.exchange_declare.assert_called_once()

    def test_producer_on_channel_closed(self):
        """Test producer channel closed callback."""
        # Arrange
        producer = AsyncRabbitProducer(
            amqp_url="amqp://test", exchange="test-exchange", exchange_type=ExchangeType.topic
        )
        mock_channel = MagicMock()
        producer._channel = mock_channel

        # Act
        producer.on_channel_closed(mock_channel, "Channel closed")

        # Assert
        assert producer._channel is None

    def test_producer_on_exchange_declareok(self):
        """Test producer exchange declare callback."""
        # Arrange
        producer = AsyncRabbitProducer(
            amqp_url="amqp://test", exchange="test-exchange", exchange_type=ExchangeType.topic
        )

        # Act
        producer.on_exchange_declareok(None)

        # Assert
        assert producer._ready.is_set()

    @pytest.mark.asyncio
    async def test_producer_publish_string_message(self, mock_connection_manager):
        """Test publishing a string message."""
        # Arrange
        producer = AsyncRabbitProducer(
            amqp_url="amqp://test",
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            routing_key="test.key",
        )
        producer._connected = True
        producer._channel = MagicMock()
        producer._ready.set()

        # Act
        result = await producer.publish("test message", routing_key="test.key")

        # Assert
        assert result is True
        producer._channel.basic_publish.assert_called_once()
        call_args = producer._channel.basic_publish.call_args
        assert call_args[1]["exchange"] == "test-exchange"
        assert call_args[1]["routing_key"] == "test.key"
        assert call_args[1]["body"] == b"test message"

    @pytest.mark.asyncio
    async def test_producer_publish_bytes_message(self, mock_connection_manager):
        """Test publishing a bytes message."""
        # Arrange
        producer = AsyncRabbitProducer(
            amqp_url="amqp://test",
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            routing_key="test.key",
        )
        producer._connected = True
        producer._channel = MagicMock()
        producer._ready.set()

        # Act
        result = await producer.publish(b"test bytes", routing_key="test.key")

        # Assert
        assert result is True
        call_args = producer._channel.basic_publish.call_args
        assert call_args[1]["body"] == b"test bytes"

    @pytest.mark.asyncio
    async def test_producer_publish_uses_default_routing_key(self, mock_connection_manager):
        """Test that publish uses default routing key when not specified."""
        # Arrange
        producer = AsyncRabbitProducer(
            amqp_url="amqp://test",
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            routing_key="default.key",
        )
        producer._connected = True
        producer._channel = MagicMock()
        producer._ready.set()

        # Act
        result = await producer.publish("test")

        # Assert
        assert result is True
        call_args = producer._channel.basic_publish.call_args
        assert call_args[1]["routing_key"] == "default.key"

    @pytest.mark.asyncio
    async def test_producer_publish_without_routing_key_fails(self, mock_connection_manager):
        """Test that publish fails without routing key."""
        # Arrange
        producer = AsyncRabbitProducer(
            amqp_url="amqp://test", exchange="test-exchange", exchange_type=ExchangeType.topic
        )
        producer._connected = True
        producer._channel = MagicMock()
        producer._ready.set()

        # Act
        result = await producer.publish("test")

        # Assert
        assert result is False

    @pytest.mark.asyncio
    async def test_producer_publish_handles_exception(self, mock_connection_manager):
        """Test that publish handles exceptions gracefully."""
        # Arrange
        producer = AsyncRabbitProducer(
            amqp_url="amqp://test",
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            routing_key="test.key",
        )
        producer._connected = True
        producer._channel = MagicMock()
        producer._channel.basic_publish.side_effect = Exception("Publish failed")
        producer._ready.set()

        # Act
        result = await producer.publish("test", routing_key="test.key")

        # Assert
        assert result is False
        assert producer._connected is False

    @pytest.mark.asyncio
    async def test_producer_close(self):
        """Test closing producer."""
        # Arrange
        producer = AsyncRabbitProducer(
            amqp_url="amqp://test", exchange="test-exchange", exchange_type=ExchangeType.topic
        )
        mock_channel = MagicMock()
        mock_channel.is_open = True
        producer._channel = mock_channel

        # Act
        await producer.close()

        # Assert
        mock_channel.close.assert_called_once()
        assert producer._channel is None


class TestAsyncRabbitConsumer:
    """Test suite for AsyncRabbitConsumer."""

    @pytest.fixture
    def mock_callback(self):
        """Mock callback for consumer."""
        return AsyncMock()

    @pytest.fixture
    def mock_connection_manager(self):
        """Mock ConnectionManager for consumer tests."""
        with patch("mq.core.consumer.ConnectionManager") as mock_cm:
            mock_instance = MagicMock()
            mock_connection = MagicMock()
            mock_connection.is_closed = False
            mock_connection.is_closing = False
            mock_instance.connect = AsyncMock(return_value=mock_connection)
            mock_cm.return_value = mock_instance
            yield mock_cm

    def test_consumer_initialization(self, mock_callback):
        """Test AsyncRabbitConsumer initialization."""
        # Arrange & Act
        consumer = AsyncRabbitConsumer(
            amqp_url="amqp://test",
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
            callback=mock_callback,
            prefetch_count=5,
        )

        # Assert
        assert consumer._url == "amqp://test"
        assert consumer._exchange == "test-exchange"
        assert consumer._exchange_type == ExchangeType.topic
        assert consumer._queue == "test-queue"
        assert consumer._routing_key == "test.key"
        assert consumer.message_callback is mock_callback
        assert consumer._prefetch_count == 5
        assert consumer._declare_exchange is True
        assert consumer._connection is None
        assert consumer._channel is None
        assert consumer._closing is False
        assert consumer._consumer_tag is None

    @pytest.mark.asyncio
    async def test_consumer_connect_success(self, mock_callback, mock_connection_manager):
        """Test consumer connection success."""
        # Arrange
        consumer = AsyncRabbitConsumer(
            amqp_url="amqp://test",
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
            callback=mock_callback,
        )
        mock_connection = mock_connection_manager.return_value.connect.return_value
        mock_connection.channel = MagicMock()

        # Act
        await consumer.connect()

        # Assert
        assert consumer._connection is not None
        mock_connection.channel.assert_called_once()

    def test_consumer_on_channel_open(self, mock_callback):
        """Test consumer channel open callback."""
        # Arrange
        consumer = AsyncRabbitConsumer(
            amqp_url="amqp://test",
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
            callback=mock_callback,
        )
        mock_channel = MagicMock()
        mock_channel.exchange_declare = MagicMock()

        # Act
        consumer.on_channel_open(mock_channel)

        # Assert
        assert consumer._channel is mock_channel
        mock_channel.add_on_close_callback.assert_called_once()
        mock_channel.exchange_declare.assert_called_once()

    def test_consumer_on_channel_open_skip_exchange_declaration(self, mock_callback):
        """Test consumer skips exchange declaration when declare_exchange is False."""
        # Arrange
        consumer = AsyncRabbitConsumer(
            amqp_url="amqp://test",
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            declare_exchange=False,
            queue="test-queue",
            routing_key="test.key",
            callback=mock_callback,
        )
        mock_channel = MagicMock()
        mock_channel.queue_declare = MagicMock()

        # Act
        consumer.on_channel_open(mock_channel)

        # Assert
        assert consumer._channel is mock_channel
        mock_channel.exchange_declare.assert_not_called()
        mock_channel.queue_declare.assert_called_once()

    def test_consumer_on_channel_closed(self, mock_callback):
        """Test consumer channel closed callback."""
        # Arrange
        consumer = AsyncRabbitConsumer(
            amqp_url="amqp://test",
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
            callback=mock_callback,
        )
        mock_channel = MagicMock()

        # Act & Assert - should not raise
        consumer.on_channel_closed(mock_channel, "Channel closed")

    def test_consumer_on_exchange_declareok(self, mock_callback):
        """Test consumer exchange declare callback."""
        # Arrange
        consumer = AsyncRabbitConsumer(
            amqp_url="amqp://test",
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
            callback=mock_callback,
        )
        mock_channel = MagicMock()
        consumer._channel = mock_channel

        # Act
        consumer.on_exchange_declareok(None, "test-exchange")

        # Assert
        mock_channel.queue_declare.assert_called_once()

    def test_consumer_on_queue_declareok(self, mock_callback):
        """Test consumer queue declare callback."""
        # Arrange
        consumer = AsyncRabbitConsumer(
            amqp_url="amqp://test",
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
            callback=mock_callback,
        )
        mock_channel = MagicMock()
        consumer._channel = mock_channel

        # Act
        consumer.on_queue_declareok(None, "test-queue")

        # Assert
        mock_channel.queue_bind.assert_called_once()
        call_args = mock_channel.queue_bind.call_args
        assert call_args[0][0] == "test-queue"
        assert call_args[0][1] == "test-exchange"

    def test_consumer_on_bindok(self, mock_callback):
        """Test consumer bind callback."""
        # Arrange
        consumer = AsyncRabbitConsumer(
            amqp_url="amqp://test",
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
            callback=mock_callback,
        )
        mock_channel = MagicMock()
        consumer._channel = mock_channel

        # Act
        consumer.on_bindok(None, "test-queue")

        # Assert
        mock_channel.basic_qos.assert_called_once()

    def test_consumer_on_basic_qos_ok(self, mock_callback):
        """Test consumer QoS callback."""
        # Arrange
        consumer = AsyncRabbitConsumer(
            amqp_url="amqp://test",
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
            callback=mock_callback,
            prefetch_count=10,
        )
        mock_channel = MagicMock()
        consumer._channel = mock_channel

        # Act
        consumer.on_basic_qos_ok(None)

        # Assert
        mock_channel.basic_consume.assert_called_once()

    @pytest.mark.asyncio
    async def test_consumer_on_message(self, mock_callback):
        """Test consumer message callback."""
        # Arrange
        consumer = AsyncRabbitConsumer(
            amqp_url="amqp://test",
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
            callback=mock_callback,
        )
        mock_channel = MagicMock()
        mock_deliver = MagicMock()
        mock_deliver.delivery_tag = 123
        mock_properties = MagicMock()
        test_body = b"test message"

        # Act
        with patch("asyncio.create_task") as mock_create_task:
            consumer.on_message(mock_channel, mock_deliver, mock_properties, test_body)

            # Assert
            mock_create_task.assert_called_once()
            # Verify the callback would be called with correct args
            task_arg = mock_create_task.call_args[0][0]
            assert asyncio.iscoroutine(task_arg)

    def test_consumer_stop_consuming(self, mock_callback):
        """Test stopping consumer."""
        # Arrange
        consumer = AsyncRabbitConsumer(
            amqp_url="amqp://test",
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
            callback=mock_callback,
        )
        mock_channel = MagicMock()
        consumer._channel = mock_channel
        consumer._consumer_tag = "test-tag"

        # Act
        consumer.stop_consuming()

        # Assert
        mock_channel.basic_cancel.assert_called_once_with("test-tag", consumer.on_cancelok)

    def test_consumer_on_cancelok(self, mock_callback):
        """Test consumer cancel callback."""
        # Arrange
        consumer = AsyncRabbitConsumer(
            amqp_url="amqp://test",
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
            callback=mock_callback,
        )
        mock_channel = MagicMock()
        consumer._channel = mock_channel

        # Act
        consumer.on_cancelok(None)

        # Assert
        mock_channel.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_consumer_shutdown(self, mock_callback):
        """Test consumer shutdown."""
        # Arrange
        consumer = AsyncRabbitConsumer(
            amqp_url="amqp://test",
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
            callback=mock_callback,
        )
        mock_channel = MagicMock()
        consumer._channel = mock_channel
        consumer._consumer_tag = "test-tag"

        # Act
        await consumer.shutdown()

        # Assert
        assert consumer._channel is None
        assert consumer._consumer_tag is None

    @pytest.mark.asyncio
    async def test_consumer_shutdown_handles_exception(self, mock_callback):
        """Test consumer shutdown handles exceptions."""
        # Arrange
        consumer = AsyncRabbitConsumer(
            amqp_url="amqp://test",
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
            callback=mock_callback,
        )
        mock_channel = MagicMock()
        mock_channel.basic_cancel.side_effect = Exception("Cancel failed")
        consumer._channel = mock_channel

        # Act & Assert - should not raise
        await consumer.shutdown()
        assert consumer._channel is None


class TestRabbitMQManager:
    """Test suite for RabbitMQManager."""

    @pytest.fixture
    def manager(self, mock_env_rabbitmq):
        """Create a RabbitMQManager instance for testing."""
        return RabbitMQManager()

    def test_manager_initialization(self, manager):
        """Test RabbitMQManager initialization."""
        # Assert
        assert isinstance(manager.consumers, dict)
        assert isinstance(manager.producers, dict)
        assert isinstance(manager.callbacks, dict)
        assert isinstance(manager.producer_factories, dict)
        assert len(manager.consumers) == 0
        assert len(manager.producers) == 0
        assert "test_user:test_pass@test-host:5672" in manager.default_amqp_url

    def test_manager_set_context(self, manager):
        """Test setting client and bot context."""
        # Arrange
        mock_client = MagicMock()
        mock_context = MagicMock()

        # Act
        manager.set_context(mock_client, mock_context)

        # Assert
        assert manager.client is mock_client
        assert manager.bot_context is mock_context

    def test_manager_register_callback_decorator(self, manager):
        """Test registering a callback with decorator."""

        # Arrange & Act
        @manager.register_callback(
            exchange="test-exchange",
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
            exchange_type=ExchangeType.topic,
            needs_context=False,
        )
        async def test_callback(body, properties):
            pass

        # Assert
        callback_name = f"{test_callback.__module__}.{test_callback.__name__}"
        assert callback_name in manager.callbacks
        assert manager.callbacks[callback_name]["callback"] is test_callback
        assert manager.callbacks[callback_name]["exchange"] == "test-exchange"
        assert manager.callbacks[callback_name]["queue"] == "test-queue"
        assert manager.callbacks[callback_name]["routing_key"] == "test.key"
        assert manager.callbacks[callback_name]["needs_context"] is False

    def test_manager_register_callback_with_context(self, manager):
        """Test registering a callback that needs context."""

        # Arrange & Act
        @manager.register_callback(
            exchange="test-exchange",
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
            needs_context=True,
        )
        async def test_callback_with_context(body, properties, client, context):
            pass

        # Assert
        callback_name = (
            f"{test_callback_with_context.__module__}.{test_callback_with_context.__name__}"
        )
        assert manager.callbacks[callback_name]["needs_context"] is True

    @pytest.mark.asyncio
    async def test_manager_register_producer_decorator(self, manager):
        """Test registering a producer with decorator."""

        # Arrange & Act
        @manager.register_producer(
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            routing_key="test.key",
            needs_context=False,
        )
        async def test_producer(message):
            return message

        # Assert
        # The decorator registers using the original function's name
        # but returns the factory, so we need to construct the expected name
        producer_name = "tests.test_mq_core.test_producer"
        assert producer_name in manager.producer_factories

    def test_manager_get_or_create_producer(self, manager):
        """Test getting or creating a producer."""
        # Arrange & Act
        producer1 = manager.get_or_create_producer(
            name="test-producer",
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            routing_key="test.key",
        )
        producer2 = manager.get_or_create_producer(
            name="test-producer",
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            routing_key="test.key",
        )

        # Assert
        assert producer1 is producer2
        assert "test-producer" in manager.producers
        assert isinstance(producer1, AsyncRabbitProducer)

    def test_manager_add_consumer(self, manager):
        """Test adding a consumer."""
        # Arrange
        mock_callback = AsyncMock()

        # Act
        consumer = manager.add_consumer(
            name="test-consumer",
            callback=mock_callback,
            exchange="test-exchange",
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
            exchange_type=ExchangeType.topic,
        )

        # Assert
        assert "test-consumer" in manager.consumers
        assert manager.consumers["test-consumer"] is consumer
        assert isinstance(consumer, AsyncRabbitConsumer)

    def test_manager_add_consumer_duplicate_raises_error(self, manager):
        """Test that adding duplicate consumer raises error."""
        # Arrange
        mock_callback = AsyncMock()
        manager.add_consumer(
            name="test-consumer",
            callback=mock_callback,
            exchange="test-exchange",
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
        )

        # Act & Assert
        with pytest.raises(ValueError, match="already exists"):
            manager.add_consumer(
                name="test-consumer",
                callback=mock_callback,
                exchange="test-exchange",
                declare_exchange=True,
                queue="test-queue",
                routing_key="test.key",
            )

    def test_manager_create_consumers(self, manager):
        """Test creating consumers from registered callbacks."""

        # Arrange
        @manager.register_callback(
            exchange="test-exchange",
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
            needs_context=False,
        )
        async def test_callback(body, properties):
            pass

        # Act
        manager.create_consumers()

        # Assert
        callback_name = f"{test_callback.__module__}.{test_callback.__name__}"
        assert callback_name in manager.consumers

    @pytest.mark.asyncio
    async def test_manager_start_consumers(self, manager):
        """Test starting all consumers."""
        # Arrange
        mock_callback = AsyncMock()
        consumer = manager.add_consumer(
            name="test-consumer",
            callback=mock_callback,
            exchange="test-exchange",
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
        )
        consumer.connect = AsyncMock()
        mock_loop = MagicMock()

        # Act
        await manager.start_consumers(mock_loop)

        # Assert
        consumer.connect.assert_called_once_with(loop=mock_loop)

    @pytest.mark.asyncio
    async def test_manager_stop_consumers(self, manager):
        """Test stopping all consumers."""
        # Arrange
        mock_callback = AsyncMock()
        consumer = manager.add_consumer(
            name="test-consumer",
            callback=mock_callback,
            exchange="test-exchange",
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
        )
        consumer.shutdown = AsyncMock()

        # Act
        await manager.stop_consumers()

        # Assert
        consumer.shutdown.assert_called_once()
        assert len(manager.consumers) == 0

    @pytest.mark.asyncio
    async def test_manager_stop_producers(self, manager):
        """Test stopping all producers."""
        # Arrange
        producer = manager.get_or_create_producer(
            name="test-producer",
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            routing_key="test.key",
        )
        producer.close = AsyncMock()

        # Act
        await manager.stop_producers()

        # Assert
        producer.close.assert_called_once()
        assert len(manager.producers) == 0

    @pytest.mark.asyncio
    async def test_manager_connect_producers(self, manager):
        """Test connecting all producers."""
        # Arrange
        producer = manager.get_or_create_producer(
            name="test-producer",
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            routing_key="test.key",
        )
        producer._connected = False
        producer.connect = AsyncMock()
        mock_loop = MagicMock()

        # Act
        await manager.connect_producers(mock_loop)

        # Assert
        producer.connect.assert_called_once_with(loop=mock_loop)

    @pytest.mark.asyncio
    async def test_manager_connect_producers_skips_connected(self, manager):
        """Test that connect_producers skips already connected producers."""
        # Arrange
        producer = manager.get_or_create_producer(
            name="test-producer",
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            routing_key="test.key",
        )
        producer._connected = True
        producer.connect = AsyncMock()
        mock_loop = MagicMock()

        # Act
        await manager.connect_producers(mock_loop)

        # Assert
        producer.connect.assert_not_called()

    @pytest.mark.asyncio
    async def test_manager_stop_all(self, manager):
        """Test stopping all consumers and producers."""
        # Arrange
        mock_callback = AsyncMock()
        consumer = manager.add_consumer(
            name="test-consumer",
            callback=mock_callback,
            exchange="test-exchange",
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
        )
        producer = manager.get_or_create_producer(
            name="test-producer",
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            routing_key="test.key",
        )
        consumer.shutdown = AsyncMock()
        producer.close = AsyncMock()

        with patch("mq.core.manager.ConnectionManager") as mock_cm:
            mock_instance = MagicMock()
            mock_instance.close = AsyncMock()
            mock_cm.return_value = mock_instance

            # Act
            await manager.stop_all()

            # Assert
            consumer.shutdown.assert_called_once()
            producer.close.assert_called_once()
            mock_instance.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_manager_producer_factory_without_context(self, manager):
        """Test producer factory without context."""

        # Arrange
        @manager.register_producer(
            exchange="test-exchange", routing_key="test.key", needs_context=False
        )
        async def test_producer(message):
            return f"processed: {message}"

        # The decorator registers using the original function's name
        producer_name = "tests.test_mq_core.test_producer"
        factory = manager.producer_factories[producer_name]

        with patch.object(manager, "get_or_create_producer") as mock_get_producer:
            mock_producer_instance = MagicMock()
            mock_producer_instance.publish = AsyncMock(return_value=True)
            mock_get_producer.return_value = mock_producer_instance

            # Act
            result = await factory("test message")

            # Assert
            assert result is True
            mock_producer_instance.publish.assert_called_once()
            call_args = mock_producer_instance.publish.call_args
            assert call_args[0][0] == "processed: test message"

    @pytest.mark.asyncio
    async def test_manager_producer_factory_with_context(self, manager):
        """Test producer factory with context."""
        # Arrange
        mock_client = MagicMock()
        mock_context = MagicMock()
        manager.set_context(mock_client, mock_context)

        @manager.register_producer(
            exchange="test-exchange", routing_key="test.key", needs_context=True
        )
        async def test_producer_with_context(message, client, context):
            return f"{message}-{client}-{context}"

        # The decorator registers using the original function's name
        producer_name = "tests.test_mq_core.test_producer_with_context"
        factory = manager.producer_factories[producer_name]

        with patch.object(manager, "get_or_create_producer") as mock_get_producer:
            mock_producer_instance = MagicMock()
            mock_producer_instance.publish = AsyncMock(return_value=True)
            mock_get_producer.return_value = mock_producer_instance

            # Act
            result = await factory("test")

            # Assert
            assert result is True
            mock_producer_instance.publish.assert_called_once()
