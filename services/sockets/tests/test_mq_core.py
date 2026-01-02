"""
Comprehensive tests for MQ core components.
Tests ConnectionManager, AsyncRabbitProducer, AsyncRabbitConsumer, and RabbitMQManager.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, Mock, call, patch

import pytest
from app.mq.core.connection_manager import ConnectionManager
from app.mq.core.consumer import AsyncRabbitConsumer
from app.mq.core.manager import RabbitMQManager
from app.mq.core.producer import AsyncRabbitProducer
from pika.exchange_type import ExchangeType
from pydantic import BaseModel


# Test Fixtures
@pytest.fixture
def reset_connection_manager():
    """Reset ConnectionManager singleton between tests."""
    ConnectionManager.instance = None
    yield
    ConnectionManager.instance = None


@pytest.fixture
def mock_connection():
    """Mock pika AsyncioConnection."""
    connection = MagicMock()
    connection.is_closed = False
    connection.is_closing = False
    connection.channel = MagicMock()
    connection.close = MagicMock()
    return connection


@pytest.fixture
def mock_channel():
    """Mock pika channel."""
    channel = MagicMock()
    channel.is_open = True
    channel.close = MagicMock()
    channel.add_on_close_callback = MagicMock()
    channel.exchange_declare = MagicMock()
    channel.queue_declare = MagicMock()
    channel.queue_bind = MagicMock()
    channel.basic_qos = MagicMock()
    channel.basic_consume = MagicMock(return_value="consumer-tag-123")
    channel.basic_cancel = MagicMock()
    channel.basic_publish = MagicMock()
    return channel


@pytest.fixture
def event_loop():
    """Create event loop for tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ConnectionManager Tests
class TestConnectionManager:
    """Test ConnectionManager singleton and connection lifecycle."""

    def test_singleton_pattern(self, reset_connection_manager):
        """Test that ConnectionManager is a singleton."""
        # Arrange & Act
        manager1 = ConnectionManager()
        manager2 = ConnectionManager()

        # Assert
        assert manager1 is manager2
        assert ConnectionManager.instance is manager1

    @pytest.mark.asyncio
    async def test_connect_success(self, reset_connection_manager, mock_connection):
        """Test successful connection to RabbitMQ."""
        # Arrange
        manager = ConnectionManager()

        with patch("app.mq.core.connection_manager.AsyncioConnection") as mock_async_conn:
            # Simulate successful connection
            def create_connection(*args, **kwargs):
                # Call on_open_callback immediately
                on_open_cb = kwargs.get("on_open_callback")
                if on_open_cb:
                    on_open_cb(mock_connection)
                return mock_connection

            mock_async_conn.side_effect = create_connection

            # Act
            connection = await manager.connect()

            # Assert
            assert connection is mock_connection
            assert manager.is_connected() is True
            assert manager._connection is mock_connection

    @pytest.mark.asyncio
    async def test_connect_reuses_existing_connection(
        self, reset_connection_manager, mock_connection
    ):
        """Test that connect reuses existing open connection."""
        # Arrange
        manager = ConnectionManager()
        manager._connection = mock_connection
        manager._connected = True

        # Act
        connection = await manager.connect()

        # Assert
        assert connection is mock_connection

    @pytest.mark.asyncio
    async def test_connect_failure(self, reset_connection_manager):
        """Test connection failure handling."""
        # Arrange
        manager = ConnectionManager()

        with patch("app.mq.core.connection_manager.AsyncioConnection") as mock_async_conn:
            mock_async_conn.side_effect = Exception("Connection failed")

            # Act & Assert
            with pytest.raises(Exception, match="Connection failed"):
                await manager.connect()

            assert manager._connection is None

    def test_on_connection_open(self, reset_connection_manager, mock_connection):
        """Test on_connection_open callback."""
        # Arrange
        manager = ConnectionManager()
        manager._ready = asyncio.Event()

        # Act
        manager.on_connection_open(mock_connection)

        # Assert
        assert manager._connected is True
        assert manager._ready.is_set() is True

    def test_on_connection_open_error(self, reset_connection_manager, mock_connection):
        """Test on_connection_open_error callback."""
        # Arrange
        manager = ConnectionManager()
        manager._ready = asyncio.Event()

        # Act
        manager.on_connection_open_error(mock_connection, "Auth failed")

        # Assert
        assert manager._connected is False
        assert manager._ready.is_set() is True

    def test_on_connection_closed_expected(self, reset_connection_manager, mock_connection):
        """Test on_connection_closed when closing is expected."""
        # Arrange
        manager = ConnectionManager()
        manager._closing = True
        manager._connected = True

        # Act
        manager.on_connection_closed(mock_connection, "Normal shutdown")

        # Assert
        assert manager._connected is False

    def test_on_connection_closed_unexpected(self, reset_connection_manager, mock_connection):
        """Test on_connection_closed when closing is unexpected."""
        # Arrange
        manager = ConnectionManager()
        manager._closing = False
        manager._connected = True

        # Act
        manager.on_connection_closed(mock_connection, "Connection lost")

        # Assert
        assert manager._connected is False

    @pytest.mark.asyncio
    async def test_close(self, reset_connection_manager, mock_connection):
        """Test closing connection."""
        # Arrange
        manager = ConnectionManager()
        manager._connection = mock_connection
        manager._connected = True

        # Act
        await manager.close()

        # Assert
        assert manager._closing is True
        assert manager._connected is False
        mock_connection.close.assert_called_once()

    def test_build_amqp_url(self, reset_connection_manager):
        """Test AMQP URL construction."""
        # Arrange
        with patch.dict(
            "os.environ",
            {
                "SOCKET_RABBIT_USER": "testuser",
                "SOCKET_RABBIT_PASS": "testpass",
                "RABBIT_HOST": "testhost",
                "RABBIT_PORT": "5672",
                "RABBIT_VHOST": "/test",
            },
        ):
            manager = ConnectionManager()

            # Act
            url = manager._build_amqp_url()

            # Assert
            assert url == "amqp://testuser:testpass@testhost:5672/%2Ftest"


# AsyncRabbitProducer Tests
class TestAsyncRabbitProducer:
    """Test AsyncRabbitProducer publishing and error handling."""

    @pytest.mark.asyncio
    async def test_connect_success(self, reset_connection_manager, mock_connection, mock_channel):
        """Test successful producer connection."""
        # Arrange
        producer = AsyncRabbitProducer(
            amqp_url="amqp://test",
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            routing_key="test.key",
        )

        with patch.object(ConnectionManager, "connect", return_value=mock_connection):
            # Simulate channel opening
            def mock_channel_open(on_open_callback):
                on_open_callback(mock_channel)

            mock_connection.channel = mock_channel_open

            # Simulate exchange declaration
            def mock_exchange_declare(exchange, exchange_type, callback):
                callback(None)

            mock_channel.exchange_declare = mock_exchange_declare

            # Act
            connection = await producer.connect()

            # Assert
            assert connection is mock_connection
            assert producer._connected is True
            assert producer._channel is mock_channel

    @pytest.mark.asyncio
    async def test_connect_already_connected(self, reset_connection_manager, mock_connection):
        """Test that connect returns early if already connected."""
        # Arrange
        producer = AsyncRabbitProducer(
            amqp_url="amqp://test", exchange="test-exchange", exchange_type=ExchangeType.topic
        )
        producer._connected = True
        producer._connection = mock_connection

        # Act
        connection = await producer.connect()

        # Assert
        assert connection is mock_connection

    @pytest.mark.asyncio
    async def test_publish_success(self, reset_connection_manager, mock_connection, mock_channel):
        """Test successful message publishing."""
        # Arrange
        producer = AsyncRabbitProducer(
            amqp_url="amqp://test",
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            routing_key="test.key",
        )
        producer._connected = True
        producer._channel = mock_channel
        producer._ready = asyncio.Event()
        producer._ready.set()

        # Act
        result = await producer.publish("test message")

        # Assert
        assert result is True
        mock_channel.basic_publish.assert_called_once()
        call_args = mock_channel.basic_publish.call_args
        assert call_args[1]["exchange"] == "test-exchange"
        assert call_args[1]["routing_key"] == "test.key"
        assert call_args[1]["body"] == b"test message"

    @pytest.mark.asyncio
    async def test_publish_with_bytes(self, reset_connection_manager, mock_channel):
        """Test publishing with bytes message."""
        # Arrange
        producer = AsyncRabbitProducer(
            amqp_url="amqp://test",
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            routing_key="test.key",
        )
        producer._connected = True
        producer._channel = mock_channel
        producer._ready = asyncio.Event()
        producer._ready.set()

        # Act
        result = await producer.publish(b"test bytes")

        # Assert
        assert result is True
        call_args = mock_channel.basic_publish.call_args
        assert call_args[1]["body"] == b"test bytes"

    @pytest.mark.asyncio
    async def test_publish_with_routing_key_override(self, reset_connection_manager, mock_channel):
        """Test publishing with routing key override."""
        # Arrange
        producer = AsyncRabbitProducer(
            amqp_url="amqp://test",
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            routing_key="default.key",
        )
        producer._connected = True
        producer._channel = mock_channel
        producer._ready = asyncio.Event()
        producer._ready.set()

        # Act
        result = await producer.publish("test", routing_key="override.key")

        # Assert
        assert result is True
        call_args = mock_channel.basic_publish.call_args
        assert call_args[1]["routing_key"] == "override.key"

    @pytest.mark.asyncio
    async def test_publish_no_routing_key(self, reset_connection_manager, mock_channel):
        """Test publishing without routing key fails."""
        # Arrange
        producer = AsyncRabbitProducer(
            amqp_url="amqp://test", exchange="test-exchange", exchange_type=ExchangeType.topic
        )
        producer._connected = True
        producer._channel = mock_channel
        producer._ready = asyncio.Event()
        producer._ready.set()

        # Act
        result = await producer.publish("test")

        # Assert
        assert result is False

    @pytest.mark.asyncio
    async def test_publish_not_connected(
        self, reset_connection_manager, mock_connection, mock_channel
    ):
        """Test publishing when not connected attempts reconnection."""
        # Arrange
        producer = AsyncRabbitProducer(
            amqp_url="amqp://test",
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            routing_key="test.key",
        )
        producer._connected = False

        with patch.object(ConnectionManager, "connect", return_value=mock_connection):
            # Simulate channel opening
            def mock_channel_open(on_open_callback):
                on_open_callback(mock_channel)

            mock_connection.channel = mock_channel_open

            # Simulate exchange declaration
            def mock_exchange_declare(exchange, exchange_type, callback):
                callback(None)

            mock_channel.exchange_declare = mock_exchange_declare

            # Act
            result = await producer.publish("test")

            # Assert
            assert result is True
            assert producer._connected is True

    @pytest.mark.asyncio
    async def test_publish_failure(self, reset_connection_manager, mock_channel):
        """Test publish failure handling."""
        # Arrange
        producer = AsyncRabbitProducer(
            amqp_url="amqp://test",
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            routing_key="test.key",
        )
        producer._connected = True
        producer._channel = mock_channel
        producer._ready = asyncio.Event()
        producer._ready.set()

        mock_channel.basic_publish.side_effect = Exception("Publish failed")

        # Act
        result = await producer.publish("test")

        # Assert
        assert result is False
        assert producer._connected is False

    @pytest.mark.asyncio
    async def test_close(self, reset_connection_manager, mock_channel):
        """Test closing producer."""
        # Arrange
        producer = AsyncRabbitProducer(
            amqp_url="amqp://test", exchange="test-exchange", exchange_type=ExchangeType.topic
        )
        producer._channel = mock_channel

        # Act
        await producer.close()

        # Assert
        mock_channel.close.assert_called_once()
        assert producer._channel is None

    def test_on_channel_closed(self, reset_connection_manager, mock_channel):
        """Test on_channel_closed callback."""
        # Arrange
        producer = AsyncRabbitProducer(
            amqp_url="amqp://test", exchange="test-exchange", exchange_type=ExchangeType.topic
        )
        producer._channel = mock_channel

        # Act
        producer.on_channel_closed(mock_channel, "Channel closed")

        # Assert
        assert producer._channel is None


# AsyncRabbitConsumer Tests
class TestAsyncRabbitConsumer:
    """Test AsyncRabbitConsumer consuming and callbacks."""

    @pytest.mark.asyncio
    async def test_connect_success(self, reset_connection_manager, mock_connection, mock_channel):
        """Test successful consumer connection."""
        # Arrange
        callback = AsyncMock()
        consumer = AsyncRabbitConsumer(
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
            callback=callback,
        )

        with patch.object(ConnectionManager, "connect", return_value=mock_connection):
            # Simulate channel opening
            def mock_channel_open(on_open_callback):
                on_open_callback(mock_channel)

            mock_connection.channel = mock_channel_open

            # Act
            await consumer.connect()

            # Assert
            assert consumer._connection is mock_connection

    @pytest.mark.asyncio
    async def test_connect_failure(self, reset_connection_manager):
        """Test consumer connection failure."""
        # Arrange
        callback = AsyncMock()
        consumer = AsyncRabbitConsumer(
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
            callback=callback,
        )

        with patch.object(ConnectionManager, "connect", side_effect=Exception("Connection failed")):
            # Act & Assert
            with pytest.raises(Exception, match="Connection failed"):
                await consumer.connect()

            assert consumer._connection is None

    def test_on_channel_open(self, reset_connection_manager, mock_channel):
        """Test on_channel_open callback."""
        # Arrange
        callback = AsyncMock()
        consumer = AsyncRabbitConsumer(
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
            callback=callback,
        )

        # Act
        consumer.on_channel_open(mock_channel)

        # Assert
        assert consumer._channel is mock_channel
        mock_channel.add_on_close_callback.assert_called_once()

    def test_setup_exchange_declared(self, reset_connection_manager, mock_channel):
        """Test exchange setup when declaration is enabled."""
        # Arrange
        callback = AsyncMock()
        consumer = AsyncRabbitConsumer(
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
            callback=callback,
        )
        consumer._channel = mock_channel

        # Act
        consumer.setup_exchange("test-exchange")

        # Assert
        mock_channel.exchange_declare.assert_called_once()

    def test_setup_exchange_not_declared(self, reset_connection_manager, mock_channel):
        """Test exchange setup when declaration is disabled."""
        # Arrange
        callback = AsyncMock()
        consumer = AsyncRabbitConsumer(
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            declare_exchange=False,
            queue="test-queue",
            routing_key="test.key",
            callback=callback,
        )
        consumer._channel = mock_channel

        # Act
        consumer.setup_exchange("test-exchange")

        # Assert
        mock_channel.exchange_declare.assert_not_called()

    def test_setup_queue(self, reset_connection_manager, mock_channel):
        """Test queue setup."""
        # Arrange
        callback = AsyncMock()
        consumer = AsyncRabbitConsumer(
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
            callback=callback,
        )
        consumer._channel = mock_channel

        # Act
        consumer.setup_queue("test-queue")

        # Assert
        mock_channel.queue_declare.assert_called_once()

    def test_on_queue_declareok(self, reset_connection_manager, mock_channel):
        """Test on_queue_declareok callback."""
        # Arrange
        callback = AsyncMock()
        consumer = AsyncRabbitConsumer(
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
            callback=callback,
        )
        consumer._channel = mock_channel

        # Act
        consumer.on_queue_declareok(None, "test-queue")

        # Assert
        mock_channel.queue_bind.assert_called_once()

    def test_set_qos(self, reset_connection_manager, mock_channel):
        """Test QoS setup."""
        # Arrange
        callback = AsyncMock()
        consumer = AsyncRabbitConsumer(
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
            callback=callback,
            prefetch_count=5,
        )
        consumer._channel = mock_channel

        # Act
        consumer.set_qos()

        # Assert
        mock_channel.basic_qos.assert_called_once()
        call_args = mock_channel.basic_qos.call_args
        assert call_args[1]["prefetch_count"] == 5

    def test_start_consuming(self, reset_connection_manager, mock_channel):
        """Test starting message consumption."""
        # Arrange
        callback = AsyncMock()
        consumer = AsyncRabbitConsumer(
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
            callback=callback,
        )
        consumer._channel = mock_channel

        # Act
        consumer.start_consuming()

        # Assert
        mock_channel.basic_consume.assert_called_once()
        assert consumer._consumer_tag == "consumer-tag-123"

    @pytest.mark.asyncio
    async def test_on_message_without_schema(self, reset_connection_manager):
        """Test message processing without schema validation."""
        # Arrange
        callback = AsyncMock()
        consumer = AsyncRabbitConsumer(
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
            callback=callback,
        )

        mock_deliver = MagicMock()
        mock_deliver.delivery_tag = 1
        mock_properties = MagicMock()
        test_body = b"test message"

        # Act
        consumer.on_message(None, mock_deliver, mock_properties, test_body)

        # Wait for async task to complete
        await asyncio.sleep(0.1)

        # Assert
        callback.assert_called_once_with(test_body, mock_properties)

    @pytest.mark.asyncio
    async def test_on_message_with_schema(self, reset_connection_manager):
        """Test message processing with schema validation."""

        # Arrange
        class TestSchema(BaseModel):
            name: str
            value: int

        callback = AsyncMock()
        consumer = AsyncRabbitConsumer(
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
            callback=callback,
            schema=TestSchema,
        )

        mock_deliver = MagicMock()
        mock_deliver.delivery_tag = 1
        mock_properties = MagicMock()
        test_body = json.dumps({"name": "test", "value": 42}).encode()

        # Act
        consumer.on_message(None, mock_deliver, mock_properties, test_body)

        # Wait for async task to complete
        await asyncio.sleep(0.1)

        # Assert
        callback.assert_called_once()
        call_args = callback.call_args
        assert isinstance(call_args[0][0], TestSchema)
        assert call_args[0][0].name == "test"
        assert call_args[0][0].value == 42

    @pytest.mark.asyncio
    async def test_on_message_schema_validation_error(self, reset_connection_manager):
        """Test message processing with invalid schema."""

        # Arrange
        class TestSchema(BaseModel):
            name: str
            value: int

        callback = AsyncMock()
        consumer = AsyncRabbitConsumer(
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
            callback=callback,
            schema=TestSchema,
        )

        mock_deliver = MagicMock()
        mock_deliver.delivery_tag = 1
        mock_properties = MagicMock()
        test_body = json.dumps({"invalid": "data"}).encode()

        # Act
        consumer.on_message(None, mock_deliver, mock_properties, test_body)

        # Wait for async task to complete
        await asyncio.sleep(0.1)

        # Assert - callback should not be called due to validation error
        callback.assert_not_called()

    def test_stop_consuming(self, reset_connection_manager, mock_channel):
        """Test stopping message consumption."""
        # Arrange
        callback = AsyncMock()
        consumer = AsyncRabbitConsumer(
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
            callback=callback,
        )
        consumer._channel = mock_channel
        consumer._consumer_tag = "consumer-tag-123"

        # Act
        consumer.stop_consuming()

        # Assert
        mock_channel.basic_cancel.assert_called_once_with("consumer-tag-123", consumer.on_cancelok)

    @pytest.mark.asyncio
    async def test_shutdown(self, reset_connection_manager, mock_channel):
        """Test consumer shutdown."""
        # Arrange
        callback = AsyncMock()
        consumer = AsyncRabbitConsumer(
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
            callback=callback,
        )
        consumer._channel = mock_channel
        consumer._consumer_tag = "consumer-tag-123"

        # Act
        await consumer.shutdown()

        # Assert
        assert consumer._channel is None
        assert consumer._consumer_tag is None


# RabbitMQManager Tests
class TestRabbitMQManager:
    """Test RabbitMQManager registration and lifecycle."""

    def test_register_callback_decorator(self):
        """Test registering a callback with decorator."""
        # Arrange
        manager = RabbitMQManager()

        # Act
        @manager.register_callback(
            exchange="test-exchange",
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
        )
        async def test_callback(body, properties):
            pass

        # Assert
        callback_name = f"{test_callback.__module__}.{test_callback.__name__}"
        assert callback_name in manager.callbacks
        assert manager.callbacks[callback_name]["exchange"] == "test-exchange"
        assert manager.callbacks[callback_name]["queue"] == "test-queue"
        assert manager.callbacks[callback_name]["routing_key"] == "test.key"

    def test_register_callback_with_schema(self):
        """Test registering a callback with schema."""
        # Arrange
        manager = RabbitMQManager()

        class TestSchema(BaseModel):
            name: str

        # Act
        @manager.register_callback(
            exchange="test-exchange",
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
            schema=TestSchema,
        )
        async def test_callback(body, properties):
            pass

        # Assert
        callback_name = f"{test_callback.__module__}.{test_callback.__name__}"
        assert manager.callbacks[callback_name]["schema"] is TestSchema

    @pytest.mark.asyncio
    async def test_register_producer_decorator(self):
        """Test registering a producer with decorator."""
        # Arrange
        manager = RabbitMQManager()
        manager.default_amqp_url = "amqp://test"

        # Act
        @manager.register_producer(exchange="test-exchange", routing_key="test.key")
        async def test_producer(message):
            return message.upper()

        # Assert
        producer_name = "tests.test_mq_core.test_producer"
        assert producer_name in manager.producer_factories

    def test_add_consumer(self):
        """Test adding a consumer."""
        # Arrange
        manager = RabbitMQManager()
        callback = AsyncMock()

        # Act
        consumer = manager.add_consumer(
            name="test-consumer",
            callback=callback,
            exchange="test-exchange",
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
        )

        # Assert
        assert "test-consumer" in manager.consumers
        assert manager.consumers["test-consumer"] is consumer
        assert consumer._exchange == "test-exchange"
        assert consumer._queue == "test-queue"

    def test_add_consumer_duplicate_name(self):
        """Test adding a consumer with duplicate name raises error."""
        # Arrange
        manager = RabbitMQManager()
        callback = AsyncMock()

        manager.add_consumer(
            name="test-consumer",
            callback=callback,
            exchange="test-exchange",
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
        )

        # Act & Assert
        with pytest.raises(ValueError, match="already exists"):
            manager.add_consumer(
                name="test-consumer",
                callback=callback,
                exchange="test-exchange",
                declare_exchange=True,
                queue="test-queue",
                routing_key="test.key",
            )

    def test_create_consumers(self):
        """Test creating consumers from registered callbacks."""
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
        callback_name = f"{test_callback.__module__}.{test_callback.__name__}"
        assert callback_name in manager.consumers

    def test_get_or_create_producer_new(self):
        """Test getting or creating a new producer."""
        # Arrange
        manager = RabbitMQManager()
        manager.default_amqp_url = "amqp://test"

        # Act
        producer = manager.get_or_create_producer(
            name="test-producer",
            exchange="test-exchange",
            exchange_type=ExchangeType.topic,
            routing_key="test.key",
        )

        # Assert
        assert "test-producer" in manager.producers
        assert manager.producers["test-producer"] is producer

    def test_get_or_create_producer_existing(self):
        """Test getting an existing producer."""
        # Arrange
        manager = RabbitMQManager()
        manager.default_amqp_url = "amqp://test"

        producer1 = manager.get_or_create_producer(
            name="test-producer", exchange="test-exchange", exchange_type=ExchangeType.topic
        )

        # Act
        producer2 = manager.get_or_create_producer(
            name="test-producer", exchange="test-exchange", exchange_type=ExchangeType.topic
        )

        # Assert
        assert producer1 is producer2

    @pytest.mark.asyncio
    async def test_start_consumers(self, reset_connection_manager, mock_connection, mock_channel):
        """Test starting all consumers."""
        # Arrange
        manager = RabbitMQManager()
        callback = AsyncMock()

        manager.add_consumer(
            name="test-consumer",
            callback=callback,
            exchange="test-exchange",
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
        )

        loop = asyncio.get_event_loop()

        with patch.object(ConnectionManager, "connect", return_value=mock_connection):

            def mock_channel_open(on_open_callback):
                on_open_callback(mock_channel)

            mock_connection.channel = mock_channel_open

            # Act
            await manager.start_consumers(loop)

            # Assert
            assert manager.consumers["test-consumer"]._connection is mock_connection

    @pytest.mark.asyncio
    async def test_stop_consumers(self):
        """Test stopping all consumers."""
        # Arrange
        manager = RabbitMQManager()
        callback = AsyncMock()

        consumer = manager.add_consumer(
            name="test-consumer",
            callback=callback,
            exchange="test-exchange",
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
        )

        # Act
        await manager.stop_consumers()

        # Assert
        assert len(manager.consumers) == 0

    @pytest.mark.asyncio
    async def test_stop_producers(self):
        """Test stopping all producers."""
        # Arrange
        manager = RabbitMQManager()
        manager.default_amqp_url = "amqp://test"

        producer = manager.get_or_create_producer(
            name="test-producer", exchange="test-exchange", exchange_type=ExchangeType.topic
        )

        # Act
        await manager.stop_producers()

        # Assert
        assert len(manager.producers) == 0

    @pytest.mark.asyncio
    async def test_stop_all(self, reset_connection_manager):
        """Test stopping all consumers and producers."""
        # Arrange
        manager = RabbitMQManager()
        manager.default_amqp_url = "amqp://test"
        callback = AsyncMock()

        manager.add_consumer(
            name="test-consumer",
            callback=callback,
            exchange="test-exchange",
            declare_exchange=True,
            queue="test-queue",
            routing_key="test.key",
        )

        manager.get_or_create_producer(
            name="test-producer", exchange="test-exchange", exchange_type=ExchangeType.topic
        )

        with patch.object(ConnectionManager, "close", new_callable=AsyncMock) as mock_close:
            # Act
            await manager.stop_all()

            # Assert
            assert len(manager.consumers) == 0
            assert len(manager.producers) == 0
            mock_close.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_producers(self, reset_connection_manager, mock_connection, mock_channel):
        """Test connecting all producers."""
        # Arrange
        manager = RabbitMQManager()
        manager.default_amqp_url = "amqp://test"

        producer = manager.get_or_create_producer(
            name="test-producer", exchange="test-exchange", exchange_type=ExchangeType.topic
        )

        loop = asyncio.get_event_loop()

        with patch.object(ConnectionManager, "connect", return_value=mock_connection):

            def mock_channel_open(on_open_callback):
                on_open_callback(mock_channel)

            mock_connection.channel = mock_channel_open

            def mock_exchange_declare(exchange, exchange_type, callback):
                callback(None)

            mock_channel.exchange_declare = mock_exchange_declare

            # Act
            await manager.connect_producers(loop)

            # Assert
            assert producer._connected is True

    @pytest.mark.asyncio
    async def test_start_health_monitor(self, reset_connection_manager):
        """Test starting health monitor."""
        # Arrange
        manager = RabbitMQManager()
        loop = asyncio.get_event_loop()

        with patch.object(ConnectionManager, "is_connected", return_value=True):
            # Act
            await manager.start_health_monitor(loop)

            # Assert - health monitor task should be created
            # We can't easily test the task itself, but we can verify no errors
            await asyncio.sleep(0.1)  # Let the task start
