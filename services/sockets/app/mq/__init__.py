import logging
from typing import Callable
from pika.exchange_type import ExchangeType
from .core.manager import RabbitMQManager
from .core.connection_manager import ConnectionManager

LOGGER = logging.getLogger(__name__)

_manager = RabbitMQManager()

DEFAULT_EXCHANGE = "swecc-socket-exchange"


def consumer(
    queue,
    routing_key,
    exchange=DEFAULT_EXCHANGE,
    exchange_type=ExchangeType.topic,
    declare_exchange=True,
    schema=None
) -> Callable:
    """decorator for registering consumers"""
    return _manager.register_callback(
        exchange, declare_exchange, queue, routing_key, exchange_type, schema
    )


def producer(
    exchange=DEFAULT_EXCHANGE,
    exchange_type=ExchangeType.topic,
    declare_exchange=True,
    routing_key=None,
) -> Callable:
    """decorator for registering producers"""
    return _manager.register_producer(
        exchange,
        exchange_type,
        routing_key,
    )


async def initialize_rabbitmq(loop):
    global _manager

    await ConnectionManager(loop=loop).connect()

    _manager.create_consumers()

    try:
        await _manager.start_consumers(loop)
        await _manager.connect_producers(loop)
        LOGGER.info("RabbitMQ consumers and producers initialized")
    except Exception as e:
        LOGGER.error(f"Error initializing RabbitMQ: {str(e)}")
        LOGGER.info("Will continue to retry connections in the background")
    finally:
        LOGGER.info("Starting health monitor")
        await _manager.start_health_monitor(loop)


async def shutdown_rabbitmq():
    global _manager

    if _manager:
        await _manager.stop_all()
