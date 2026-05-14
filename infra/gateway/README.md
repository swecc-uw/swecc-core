# gateway (linuxserver/swag deployment)

This folder defines the **linuxserver/swag** reverse-proxy deployment used to terminate TLS for `api.swecc.org` and route traffic to the swarm services. There's also a parallel, simpler nginx config at [`../nginx.conf`](../nginx.conf) which is what `infra/stack.yml` actually mounts in the swarm — keep the two in sync when changing routes.

## Compose

[`docker-compose.yaml`](./docker-compose.yaml) runs a single `linuxserver/swag` container that:

- Terminates HTTPS for `api.swecc.org` (Let's Encrypt via HTTP-01 validation)
- Loads every `proxy-confs/*.subdomain.conf` and `proxy-confs/*.subfolder.conf` as nginx server blocks

## Active configs

- [`config/nginx/proxy-confs/api.swecc.org.subdomain.conf`](./config/nginx/proxy-confs/api.swecc.org.subdomain.conf) — the production `api.swecc.org` server block. Currently routes:

  | Path | Upstream | Notes |
  |---|---|---|
  | `/ws`, `/ws/` | `swecc_stack_sockets:8004` | WebSocket upgrade |
  | `/bench/v1/ws/` | `swecc_stack_bench-api:8000` | bench-api trace stream (WS, no buffering) |
  | `/bench/` | `swecc_stack_bench-api:8000` | bench-api HTTP (strips `/bench/`) |
  | `/` (catch-all) | `swecc_stack_server:8000` | Django (auth, members, leaderboard, …) |

- [`config/nginx/proxy-confs/swecc-server.conf`](./config/nginx/proxy-confs/swecc-server.conf) — legacy reference for the Django service. **Not** loaded by SWAG (wrong filename suffix); kept around as documentation only.

## Adding a new route

Add a new `location` block in `api.swecc.org.subdomain.conf` **above** the catch-all `location /` (longer prefixes win in nginx, but the catch-all is unconditional so anything not claimed by an earlier block falls through to Django). If you also use the swarm gateway, mirror the same block in `../nginx.conf` — and in `../nginx.dev.conf` for local-dev parity.
