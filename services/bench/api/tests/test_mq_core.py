from app.mq.core.manager import RabbitMQManager
from pika.exchange_type import ExchangeType


def test_register_callback_stores_prefetch_count():
    manager = RabbitMQManager()

    @manager.register_callback(
        exchange="swecc-bench-exchange",
        declare_exchange=True,
        queue="bench.run-queue",
        routing_key="bench.run.execute",
        prefetch_count=3,
    )
    async def sample_consumer(body, properties):
        pass

    name = f"{sample_consumer.__module__}.{sample_consumer.__name__}"
    assert manager.callbacks[name]["prefetch_count"] == 3

    manager.create_consumers()
    consumer = manager.consumers[name]
    assert consumer._prefetch_count == 3
    assert consumer._exchange_type == ExchangeType.topic
