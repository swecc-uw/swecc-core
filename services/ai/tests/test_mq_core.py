"""
Comprehensive tests for MQ core components:
- ConnectionManager
- AsyncRabbitProducer
- AsyncRabbitConsumer
- RabbitMQManager
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, Mock, call, patch

import pytest
from app.mq.core.connection_manager import ConnectionManager
from app.mq.core.consumer import AsyncRabbitConsumer
from app.mq.core.manager import RabbitMQManager
from app.mq.core.producer import AsyncRabbitProducer
from pika.exchange_type import ExchangeType


@pytest.fixture
def reset_connection_manager():
    """Reset ConnectionManager singleton between tests"""
    ConnectionManager.instance = None
    yield
    ConnectionManager.instance = None


@pytest.fixture
def mock_pika_connection():
    """Mock pika AsyncioConnection"""
    mock_conn = MagicMock()
    mock_conn.is_closed = False
    mock_conn.is_closing = False
    mock_conn.close = MagicMock()
    return mock_conn


@pytest.fixture
def mock_channel():
    """Mock pika channel"""
    mock_ch = MagicMock()
    mock_ch.is_open = True
    mock_ch.close = MagicMock()
    mock_ch.exchange_declare = MagicMock()
    mock_ch.queue_declare = MagicMock()
    mock_ch.queue_bind = MagicMock()
    mock_ch.basic_qos = MagicMock()
    mock_ch.basic_consume = MagicMock(return_value="consumer_tag_123")
    mock_ch.basic_cancel = MagicMock()
    mock_ch.basic_publish = MagicMock()
    mock_ch.add_on_close_callback = MagicMock()
    return mock_ch


class TestConnectionManager:
    """Test ConnectionManager singleton and connection lifecycle"""

    def test_singleton_pattern(self, reset_connection_manager):
        """Test that ConnectionManager is a singleton"""
        # Arrange & Act
        manager1 = ConnectionManager()
        manager2 = ConnectionManager()

        # Assert
        assert manager1 is manager2
        assert ConnectionManager.instance is manager1

    @pytest.mark.asyncio
    async def test_connect_success(self, reset_connection_manager, mock_pika_connection):
        """Test successful connection to RabbitMQ"""
        # Arrange
        manager = ConnectionManager()

        with patch("app.mq.core.connection_manager.AsyncioConnection") as mock_async_conn:
            # Simulate connection opening
            def side_effect(*args, **kwargs):
                on_open = kwargs.get("on_open_callback")
                if on_open:
                    on_open(mock_pika_connection)
                return mock_pika_connection

            mock_async_conn.side_effect = side_effect

            # Act
            connection = await manager.connect()

            # Assert
            assert connection is mock_pika_connection
            assert manager.is_connected() is True
            mock_async_conn.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_reuses_existing_connection(
        self, reset_connection_manager, mock_pika_connection
    ):
        """Test that connect reuses existing open connection"""
        # Arrange
        manager = ConnectionManager()
        manager._connection = mock_pika_connection
        manager._connected = True

        # Act
        connection = await manager.connect()

        # Assert
        assert connection is mock_pika_connection

    @pytest.mark.asyncio
    async def test_connect_failure(self, reset_connection_manager):
        """Test connection failure handling"""
        # Arrange
        manager = ConnectionManager()

        with patch("app.mq.core.connection_manager.AsyncioConnection") as mock_async_conn:
            mock_async_conn.side_effect = Exception("Connection failed")

            # Act & Assert
            with pytest.raises(Exception, match="Connection failed"):
                await manager.connect()

            assert manager._connection is None

    def test_on_connection_open(self, reset_connection_manager, mock_pika_connection):
        """Test connection open callback"""
        # Arrange
        manager = ConnectionManager()
        manager._ready = asyncio.Event()

        # Act
        manager.on_connection_open(mock_pika_connection)

        # Assert
        assert manager._connected is True
        assert manager._ready.is_set() is True

    def test_on_connection_open_error(self, reset_connection_manager, mock_pika_connection):
        """Test connection open error callback"""
        # Arrange
        manager = ConnectionManager()
        manager._ready = asyncio.Event()

        # Act
        manager.on_connection_open_error(mock_pika_connection, "Error message")

        # Assert
        assert manager._connected is False
        assert manager._ready.is_set() is True

    def test_on_connection_closed_graceful(self, reset_connection_manager, mock_pika_connection):
        """Test graceful connection close"""
        # Arrange
        manager = ConnectionManager()
        manager._closing = True

        # Act
        manager.on_connection_closed(mock_pika_connection, "Normal shutdown")

        # Assert
        assert manager._connected is False

    def test_on_connection_closed_unexpected(self, reset_connection_manager, mock_pika_connection):
        """Test unexpected connection close"""
        # Arrange
        manager = ConnectionManager()
        manager._closing = False

        # Act
        manager.on_connection_closed(mock_pika_connection, "Connection lost")

        # Assert
        assert manager._connected is False

    @pytest.mark.asyncio
    async def test_close_connection(self, reset_connection_manager, mock_pika_connection):
        """Test closing connection"""
        # Arrange
        manager = ConnectionManager()
        manager._connection = mock_pika_connection
        manager._connected = True

        # Act
        await manager.close()

        # Assert
        assert manager._closing is True
        assert manager._connected is False
        mock_pika_connection.close.assert_called_once()

    def test_build_amqp_url(self, reset_connection_manager):
        """Test AMQP URL construction"""
        # Arrange
        with patch.dict(
            "os.environ",
            {
                "AI_RABBIT_USER": "testuser",
                "AI_RABBIT_PASS": "testpass",
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

    def test_build_amqp_url_defaults(self, reset_connection_manager):
        """Test AMQP URL construction with defaults"""
        # Arrange
        with patch.dict("os.environ", {}, clear=True):
            manager = ConnectionManager()

            # Act
            url = manager._build_amqp_url()

            # Assert
            assert url == "amqp://guest:guest@rabbitmq-host:5672/%2F"


class TestAsyncRabbitProducer:
    """Test AsyncRabbitProducer publishing and error handling"""

    @pytest.mark.asyncio
    async def test_connect_success(
        self, reset_connection_manager, mock_pika_connection, mock_channel
    ):
        """Test successful producer connection"""
        # Arrange
        producer = AsyncRabbitProducer(
            exchange="test-exchange", exchange_type=ExchangeType.topic, routing_key="test.key"
        )

        with patch.object(ConnectionManager, "connect", return_value=mock_pika_connection):
            # Simulate channel opening and exchange declaration
            def channel_side_effect(on_open_callback):
                on_open_callback(mock_channel)

            mock_pika_connection.channel = MagicMock(side_effect=channel_side_effect)

            def exchange_declare_side_effect(exchange, exchange_type, callback):
                callback(None)

            mock_channel.exchange_declare = MagicMock(side_effect=exchange_declare_side_effect)

            # Act
            connection = await producer.connect()

            # Assert
            assert connection is mock_pika_connection
            assert producer._connected is True
            assert producer._channel is mock_channel

    @pytest.mark.asyncio
    async def test_connect_already_connected(self, reset_connection_manager, mock_pika_connection):
        """Test that connect returns early if already connected"""
        # Arrange
        producer = AsyncRabbitProducer(exchange="test-exchange", exchange_type=ExchangeType.topic)
        producer._connected = True
        producer._connection = mock_pika_connection

        # Act
        connection = await producer.connect()

        # Assert
        assert connection is mock_pika_connection

    @pytest.mark.asyncio
    async def test_publish_success(self, reset_connection_manager, mock_channel):
        """Test successful message publishing"""
        # Arrange
        producer = AsyncRabbitProducer(
            exchange="test-exchange", exchange_type=ExchangeType.topic, routing_key="test.key"
        )
        producer._connected = True
        producer._channel = mock_channel
        producer._ready.set()

        # Act
        result = await producer.publish("test message", routing_key="test.key")

        # Assert
        assert result is True
        mock_channel.basic_publish.assert_called_once()
        call_args = mock_channel.basic_publish.call_args
        assert call_args[1]["exchange"] == "test-exchange"
        assert call_args[1]["routing_key"] == "test.key"
        assert call_args[1]["body"] == b"test message"

    @pytest.mark.asyncio
    async def test_publish_bytes_message(self, reset_connection_manager, mock_channel):
        """Test publishing bytes message"""
        # Arrange
        producer = AsyncRabbitProducer(
            exchange="test-exchange", exchange_type=ExchangeType.topic, routing_key="test.key"
        )
        producer._connected = True
        producer._channel = mock_channel
        producer._ready.set()

        # Act
        result = await producer.publish(b"test bytes", routing_key="test.key")

        # Assert
        assert result is True
        call_args = mock_channel.basic_publish.call_args
        assert call_args[1]["body"] == b"test bytes"

    @pytest.mark.asyncio
    async def test_publish_no_routing_key(self, reset_connection_manager, mock_channel):
        """Test publishing without routing key fails"""
        # Arrange
        producer = AsyncRabbitProducer(exchange="test-exchange", exchange_type=ExchangeType.topic)
        producer._connected = True
        producer._channel = mock_channel
        producer._ready.set()

        # Act
        result = await producer.publish("test message")

        # Assert
        assert result is False

    @pytest.mark.asyncio
    async def test_publish_failure(self, reset_connection_manager, mock_channel):
        """Test publishing failure handling"""
        # Arrange
        producer = AsyncRabbitProducer(
            exchange="test-exchange", exchange_type=ExchangeType.topic, routing_key="test.key"
        )
        producer._connected = True
        producer._channel = mock_channel
        producer._ready.set()
        mock_channel.basic_publish.side_effect = Exception("Publish failed")

        # Act
        result = await producer.publish("test message")

        # Assert
        assert result is False
        assert producer._connected is False

    @pytest.mark.asyncio
    async def test_publish_reconnect_on_disconnect(
        self, reset_connection_manager, mock_pika_connection, mock_channel
    ):
        """Test that publish attempts to reconnect if disconnected"""
        # Arrange
        producer = AsyncRabbitProducer(
            exchange="test-exchange", exchange_type=ExchangeType.topic, routing_key="test.key"
        )
        producer._connected = False

        with patch.object(producer, "connect", return_value=mock_pika_connection) as mock_connect:
            producer._channel = mock_channel
            producer._ready.set()

            # Act
            result = await producer.publish("test message")

            # Assert
            mock_connect.assert_called()

    @pytest.mark.asyncio
    async def test_close(self, reset_connection_manager, mock_channel):
        """Test closing producer"""
        # Arrange
        producer = AsyncRabbitProducer(exchange="test-exchange", exchange_type=ExchangeType.topic)
        producer._channel = mock_channel

        # Act
        await producer.close()

        # Assert
        mock_channel.close.assert_called_once()
        assert producer._channel is None


class TestAsyncRabbitConsumer:
    """Test AsyncRabbitConsumer consuming and callbacks"""

    @pytest.mark.asyncio
    async def test_connect_success(
        self, reset_connection_manager, mock_pika_connection, mock_channel
    ):
        """Test successful consumer connection"""
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

        with patch.object(ConnectionManager, "connect", return_value=mock_pika_connection):

            def channel_side_effect(on_open_callback):
                on_open_callback(mock_channel)

            mock_pika_connection.channel = MagicMock(side_effect=channel_side_effect)

            # Act
            await consumer.connect()

            # Assert
            assert consumer._connection is mock_pika_connection
            mock_pika_connection.channel.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_failure(self, reset_connection_manager):
        """Test consumer connection failure"""
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

    def test_on_channel_open(self, mock_channel):
        """Test channel open callback"""
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

        with patch.object(consumer, "setup_exchange") as mock_setup:
            # Act
            consumer.on_channel_open(mock_channel)

            # Assert
            assert consumer._channel is mock_channel
            mock_channel.add_on_close_callback.assert_called_once()
            mock_setup.assert_called_once_with("test-exchange")

    def test_setup_exchange_declare(self, mock_channel):
        """Test exchange declaration"""
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

    def test_setup_exchange_skip_declare(self, mock_channel):
        """Test skipping exchange declaration"""
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

        with patch.object(consumer, "setup_queue") as mock_setup_queue:
            # Act
            consumer.setup_exchange("test-exchange")

            # Assert
            mock_channel.exchange_declare.assert_not_called()
            mock_setup_queue.assert_called_once_with("test-queue")

    def test_setup_queue(self, mock_channel):
        """Test queue declaration"""
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

    def test_on_queue_declareok(self, mock_channel):
        """Test queue declare callback"""
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

    def test_set_qos(self, mock_channel):
        """Test setting QoS"""
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

    def test_start_consuming(self, mock_channel):
        """Test starting consumption"""
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
        assert consumer._consumer_tag == "consumer_tag_123"

    @pytest.mark.asyncio
    async def test_on_message(self, mock_channel):
        """Test message callback invocation"""
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
        consumer.on_message(mock_channel, mock_deliver, mock_properties, test_body)

        # Give asyncio.create_task time to schedule
        await asyncio.sleep(0.1)

        # Assert
        callback.assert_called_once_with(test_body, mock_properties)

    def test_stop_consuming(self, mock_channel):
        """Test stopping consumption"""
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
        consumer._consumer_tag = "consumer_tag_123"

        # Act
        consumer.stop_consuming()

        # Assert
        mock_channel.basic_cancel.assert_called_once_with("consumer_tag_123", consumer.on_cancelok)

    @pytest.mark.asyncio
    async def test_shutdown(self, mock_channel):
        """Test consumer shutdown"""
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
        consumer._consumer_tag = "consumer_tag_123"

        with patch.object(consumer, "stop_consuming") as mock_stop:
            # Act
            await consumer.shutdown()

            # Assert
            mock_stop.assert_called_once()
            assert consumer._channel is None
            assert consumer._consumer_tag is None


class TestRabbitMQManager:
    """Test RabbitMQManager registration and lifecycle"""

    def test_register_callback(self):
        """Test registering a consumer callback"""
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

        # Assert
        callback_name = f"{test_callback.__module__}.{test_callback.__name__}"
        assert callback_name in manager.callbacks
        assert manager.callbacks[callback_name]["exchange"] == "test-exchange"
        assert manager.callbacks[callback_name]["queue"] == "test-queue"
        assert manager.callbacks[callback_name]["routing_key"] == "test.key"

    @pytest.mark.asyncio
    async def test_register_producer(self):
        """Test registering a producer"""
        # Arrange
        manager = RabbitMQManager()

        @manager.register_producer(exchange="test-exchange", routing_key="test.key")
        async def my_test_producer(data):
            return data

        # Assert
        # The producer name is generated from the decorated function's module and name
        # Since this is a test, the module will be the test module
        assert len(manager.producer_factories) == 1
        # Check that a producer factory was registered
        assert "my_test_producer" in list(manager.producer_factories.keys())[0]

    @pytest.mark.asyncio
    async def test_producer_factory_execution(
        self, reset_connection_manager, mock_pika_connection, mock_channel
    ):
        """Test that producer factory processes and publishes messages"""
        # Arrange
        manager = RabbitMQManager()

        @manager.register_producer(exchange="test-exchange", routing_key="test.key")
        async def my_test_producer_exec(data):
            return f"processed: {data}"

        # Get the actual registered producer name
        producer_name = list(manager.producer_factories.keys())[0]

        # Mock the producer
        mock_producer = AsyncMock()
        mock_producer.publish = AsyncMock(return_value=True)
        manager.producers[producer_name] = mock_producer

        # Act
        factory = manager.producer_factories[producer_name]
        result = await factory("test data")

        # Assert
        mock_producer.publish.assert_called_once()
        call_args = mock_producer.publish.call_args
        assert call_args[0][0] == "processed: test data"

    def test_add_consumer(self):
        """Test adding a consumer"""
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
        """Test that adding duplicate consumer raises error"""
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
        """Test creating consumers from registered callbacks"""
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

    @pytest.mark.asyncio
    async def test_start_consumers(self, reset_connection_manager):
        """Test starting all consumers"""
        # Arrange
        manager = RabbitMQManager()
        mock_consumer1 = AsyncMock()
        mock_consumer2 = AsyncMock()
        manager.consumers = {"consumer1": mock_consumer1, "consumer2": mock_consumer2}
        loop = asyncio.get_event_loop()

        # Act
        await manager.start_consumers(loop)

        # Assert
        mock_consumer1.connect.assert_called_once_with(loop=loop)
        mock_consumer2.connect.assert_called_once_with(loop=loop)

    @pytest.mark.asyncio
    async def test_stop_consumers(self):
        """Test stopping all consumers"""
        # Arrange
        manager = RabbitMQManager()
        mock_consumer1 = AsyncMock()
        mock_consumer2 = AsyncMock()
        manager.consumers = {"consumer1": mock_consumer1, "consumer2": mock_consumer2}

        # Act
        await manager.stop_consumers()

        # Assert
        mock_consumer1.shutdown.assert_called_once()
        mock_consumer2.shutdown.assert_called_once()
        assert len(manager.consumers) == 0

    @pytest.mark.asyncio
    async def test_stop_producers(self):
        """Test stopping all producers"""
        # Arrange
        manager = RabbitMQManager()
        mock_producer1 = AsyncMock()
        mock_producer2 = AsyncMock()
        manager.producers = {"producer1": mock_producer1, "producer2": mock_producer2}

        # Act
        await manager.stop_producers()

        # Assert
        mock_producer1.close.assert_called_once()
        mock_producer2.close.assert_called_once()
        assert len(manager.producers) == 0

    @pytest.mark.asyncio
    async def test_stop_all(self, reset_connection_manager):
        """Test stopping all components"""
        # Arrange
        manager = RabbitMQManager()

        with patch.object(manager, "stop_consumers") as mock_stop_consumers, patch.object(
            manager, "stop_producers"
        ) as mock_stop_producers, patch.object(ConnectionManager, "close") as mock_close:

            # Act
            await manager.stop_all()

            # Assert
            mock_stop_consumers.assert_called_once()
            mock_stop_producers.assert_called_once()
            mock_close.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_producers(self):
        """Test connecting all producers"""
        # Arrange
        manager = RabbitMQManager()
        mock_producer1 = AsyncMock()
        mock_producer1._connected = False
        mock_producer2 = AsyncMock()
        mock_producer2._connected = True
        manager.producers = {"producer1": mock_producer1, "producer2": mock_producer2}
        loop = asyncio.get_event_loop()

        # Act
        await manager.connect_producers(loop)

        # Assert
        mock_producer1.connect.assert_called_once_with(loop=loop)
        mock_producer2.connect.assert_not_called()

    def test_get_or_create_producer(self):
        """Test getting or creating a producer"""
        # Arrange
        manager = RabbitMQManager()
        loop = asyncio.get_event_loop()

        # Act
        producer1 = manager.get_or_create_producer(
            "test-producer", "test-exchange", ExchangeType.topic, "test.key", loop
        )
        producer2 = manager.get_or_create_producer(
            "test-producer", "test-exchange", ExchangeType.topic, "test.key", loop
        )

        # Assert
        assert producer1 is producer2
        assert "test-producer" in manager.producers
