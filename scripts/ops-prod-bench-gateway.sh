#!/usr/bin/env bash
# One-off prod ops for bench-api routing via prod_nginx (run on Swarm manager / deploy runner).
set -euo pipefail

ACTION="${1:-diagnose}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Stable path on the EC2 manager (runner workspace paths change per job).
NGINX_CONF_HOST="${NGINX_CONF_HOST:-/opt/swecc/nginx.conf}"
cd "$REPO_ROOT"

log() {
  echo "[$(date -Iseconds)] $*"
}

nginx_container_id() {
  local cid
  cid="$(docker ps -q -f name=prod_nginx 2>/dev/null | head -1 || true)"
  if [[ -z "$cid" ]]; then
    cid="$(docker ps -q --filter "ancestor=nginx:stable-alpine" 2>/dev/null | head -1 || true)"
  fi
  echo "$cid"
}

diagnose() {
  log "=== bench-api service ==="
  docker service ps bench-api --no-trunc 2>/dev/null || log "bench-api service not found"
  log "--- bench-api logs (last 40 lines) ---"
  docker service logs bench-api --tail 40 2>&1 || true

  log "=== prod_nginx (live service name: prod_nginx, not prod_prod_nginx) ==="
  docker service ps prod_nginx --no-trunc 2>/dev/null || log "prod_nginx service not found"
  local cid
  cid="$(nginx_container_id)"
  if [[ -n "$cid" ]]; then
    log "nginx container: $cid"
    docker exec "$cid" nginx -t 2>&1 || true
    log "--- wget bench-api:8000/health from inside nginx ---"
    docker exec "$cid" wget -qO- --timeout=5 http://bench-api:8000/health 2>&1 || log "FAIL: bench-api not reachable from prod_nginx"
    log "--- wget server:8000/health/ from inside nginx ---"
    docker exec "$cid" wget -qO- --timeout=5 http://server:8000/health/ 2>&1 || log "FAIL: server not reachable from prod_nginx"
  else
    log "No running prod_nginx container found"
  fi

  log "=== bench routes in repo infra/nginx.conf ==="
  grep -n "bench" "$REPO_ROOT/infra/nginx.conf" || log "no bench lines in nginx.conf"
}

sync_server_env() {
  if [[ -z "${DB_HOST:-}" ]]; then
    log "ERROR: DB_* secrets not in environment (run via workflow sync-server-env)"
    exit 1
  fi
  chmod +x ./scripts/sync-prod-server-env.sh
  ./scripts/sync-prod-server-env.sh
}

redeploy_bench_api() {
  if [[ -z "${DOCKERHUB_USERNAME:-}" ]] || [[ -z "${DOCKERHUB_TOKEN:-}" ]]; then
    log "SKIP bench-api redeploy (DOCKERHUB_* not set)"
    return 0
  fi
  log "Redeploying bench-api with server_env (./s/ops/deploy.sh)"
  chmod +x ./s/ops/deploy.sh ./s/lib.sh
  echo "${DOCKERHUB_TOKEN}" | docker login -u "${DOCKERHUB_USERNAME}" --password-stdin
  ./s/ops/deploy.sh bench-api
}

reload_nginx() {
  local conf_src="${REPO_ROOT}/infra/nginx.conf"
  if [[ ! -f "$conf_src" ]]; then
    log "ERROR: missing $conf_src"
    exit 1
  fi
  if ! docker service inspect prod_nginx &>/dev/null; then
    log "ERROR: Swarm service prod_nginx not found (will not docker stack deploy — ports already bound)"
    exit 1
  fi

  log "Installing nginx.conf to ${NGINX_CONF_HOST}"
  sudo mkdir -p "$(dirname "$NGINX_CONF_HOST")"
  sudo cp "$conf_src" "$NGINX_CONF_HOST"

  log "Updating prod_nginx bind mount (in-place service update)"
  docker service update --force prod_nginx \
    --mount-rm type=bind,target=/etc/nginx/nginx.conf \
    --mount-add "type=bind,source=${NGINX_CONF_HOST},target=/etc/nginx/nginx.conf,readonly" \
    || docker service update --force prod_nginx \
      --mount-add "type=bind,source=${NGINX_CONF_HOST},target=/etc/nginx/nginx.conf,readonly"

  log "Waiting for prod_nginx..."
  sleep 20
  docker service ps prod_nginx --no-trunc 2>/dev/null || true
  local cid
  cid="$(nginx_container_id)"
  if [[ -n "$cid" ]]; then
    docker exec "$cid" nginx -t 2>&1 || log "WARN: nginx -t failed after update"
  fi
}

verify_external() {
  log "=== HTTPS checks from this host ==="
  curl -sS -o /dev/null -w "GET /health/ -> %{http_code}\n" https://api.swecc.org/health/ || true
  log "GET /bench/health/ body:"
  curl -sS https://api.swecc.org/bench/health/ || curl -sSk https://api.swecc.org/bench/health/ || true
  echo ""
}

case "$ACTION" in
  diagnose)
    diagnose
    ;;
  redeploy-bench-api)
    redeploy_bench_api
    ;;
  sync-server-env)
    sync_server_env
    ;;
  reload-nginx)
    reload_nginx
    verify_external
    ;;
  verify)
    verify_external
    ;;
  full)
    diagnose
    redeploy_bench_api
    reload_nginx
    verify_external
    ;;
  *)
    log "Unknown action: $ACTION (use diagnose|sync-server-env|redeploy-bench-api|reload-nginx|verify|full)"
    exit 1
    ;;
esac
