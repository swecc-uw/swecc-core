"""Shared RabbitMQ helpers for bench-api and bench-worker."""

from bench_common.mq.amqp_url import build_amqp_url_from_env

__all__ = ["build_amqp_url_from_env"]
