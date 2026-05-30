from app.mq.core.connection_manager import ConnectionManager
from app.mq.core.manager import RabbitMQManager
from pika.exchange_type import ExchangeType


def test_build_amqp_url_encodes_bench_rabbit_password(monkeypatch):
    import pika

    monkeypatch.setenv("BENCH_RABBIT_USER", "swecc-bench")
    monkeypatch.setenv("BENCH_RABBIT_PASS", "p@ss:BQ#x")
    monkeypatch.setenv("RABBIT_HOST", "rabbitmq-host")
    monkeypatch.setenv("RABBIT_PORT", "5672")
    monkeypatch.setenv("RABBIT_VHOST", "/")
    ConnectionManager.instance = None
    url = ConnectionManager()._build_amqp_url()
    pika.URLParameters(url)


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
