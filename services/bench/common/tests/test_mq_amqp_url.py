"""AMQP URL building must encode special characters in credentials."""

import pytest
from bench_common.mq.amqp_url import build_amqp_url_from_env


def test_build_amqp_url_default_vhost():
    url = build_amqp_url_from_env(
        user_var="U",
        pass_var="P",
        host_var="H",
        port_var="PORT",
        vhost_var="V",
        default_user="guest",
        default_pass="guest",
        default_host="rabbit",
        default_port="5672",
        default_vhost="/",
    )
    assert url == "amqp://guest:guest@rabbit:5672/%2F"


def test_build_amqp_url_encodes_special_chars_in_password(monkeypatch):
    monkeypatch.setenv("BENCH_RABBIT_USER", "swecc-bench")
    monkeypatch.setenv("BENCH_RABBIT_PASS", "p@ss:BQ#token")
    monkeypatch.setenv("RABBIT_HOST", "rabbitmq-host")
    monkeypatch.setenv("RABBIT_PORT", "5672")
    monkeypatch.setenv("RABBIT_VHOST", "/")

    url = build_amqp_url_from_env()
    assert url == "amqp://swecc-bench:p%40ss%3ABQ%23token@rabbitmq-host:5672/%2F"


def test_build_amqp_url_encodes_at_in_password(monkeypatch):
    """Unencoded @ in password breaks pika port parsing (prod 'BQ' error)."""
    monkeypatch.setenv("BENCH_RABBIT_USER", "user")
    monkeypatch.setenv("BENCH_RABBIT_PASS", "secret@host:5672")
    monkeypatch.setenv("RABBIT_HOST", "rabbitmq-host")
    monkeypatch.setenv("RABBIT_PORT", "5672")
    monkeypatch.setenv("RABBIT_VHOST", "/")

    url = build_amqp_url_from_env()
    assert url == "amqp://user:secret%40host%3A5672@rabbitmq-host:5672/%2F"


def test_build_amqp_url_parsable_by_pika(monkeypatch):
    pika = pytest.importorskip("pika")
    monkeypatch.setenv("BENCH_RABBIT_PASS", "p@ss:BQ#token")
    params = pika.URLParameters(build_amqp_url_from_env())
    assert params.credentials.password == "p@ss:BQ#token"
