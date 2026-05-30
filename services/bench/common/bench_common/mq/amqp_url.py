"""AMQP URL construction for bench services (RFC 3986 userinfo encoding)."""

from __future__ import annotations

import os
from urllib.parse import quote


def build_amqp_url_from_env(
    *,
    user_var: str = "BENCH_RABBIT_USER",
    pass_var: str = "BENCH_RABBIT_PASS",
    host_var: str = "RABBIT_HOST",
    port_var: str = "RABBIT_PORT",
    vhost_var: str = "RABBIT_VHOST",
    default_user: str = "guest",
    default_pass: str = "guest",
    default_host: str = "rabbitmq-host",
    default_port: str = "5672",
    default_vhost: str = "/",
) -> str:
    """Build an AMQP URL from env vars, percent-encoding user, password, and vhost."""
    user = os.getenv(user_var, default_user).strip()
    password = os.getenv(pass_var, default_pass).strip()
    host = os.getenv(host_var, default_host).strip()
    port = os.getenv(port_var, default_port).strip()
    vhost = os.getenv(vhost_var, default_vhost).strip()
    user_q = quote(user, safe="")
    pass_q = quote(password, safe="")
    vhost_q = quote(vhost, safe="")
    return f"amqp://{user_q}:{pass_q}@{host}:{port}/{vhost_q}"
