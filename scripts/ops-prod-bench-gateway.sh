#!/usr/bin/env bash
# One-off prod ops for bench-api routing via prod_nginx (run on Swarm manager / deploy runner).
set -euo pipefail

ACTION="${1:-diagnose}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
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

  log "=== prod_nginx ==="
  docker service ps prod_nginx --no-trunc 2>/dev/null || log "prod_nginx stack service not found"
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

  log "=== infra/nginx.conf bench routes (checkout on runner) ==="
  grep -n "bench" "$REPO_ROOT/infra/nginx.conf" || log "no bench lines in nginx.conf"
}

reload_nginx() {
  if [[ ! -f "$REPO_ROOT/infra/stack.yml" ]] || [[ ! -f "$REPO_ROOT/infra/nginx.conf" ]]; then
    log "ERROR: missing infra/stack.yml or infra/nginx.conf under $REPO_ROOT"
    exit 1
  fi
  log "Deploying prod stack (prod_nginx) from repo root"
  log "Bind mount: ${REPO_ROOT}/infra/nginx.conf -> /etc/nginx/nginx.conf"
  export PWD="$REPO_ROOT"
  docker stack deploy -c infra/stack.yml prod
  log "Waiting for prod_nginx tasks..."
  sleep 15
  docker service ps prod_nginx 2>/dev/null || true
  local cid
  cid="$(nginx_container_id)"
  if [[ -n "$cid" ]]; then
    docker exec "$cid" nginx -t
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
  reload-nginx)
    reload_nginx
    verify_external
    ;;
  verify)
    verify_external
    ;;
  full)
    diagnose
    reload_nginx
    verify_external
    ;;
  *)
    log "Unknown action: $ACTION (use diagnose|reload-nginx|verify|full)"
    exit 1
    ;;
esac
