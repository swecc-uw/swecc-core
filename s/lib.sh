#!/bin/bash
set -euo pipefail

[[ "${DEBUG:-}" == "1" ]] && set -x

REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
export REPO_ROOT

SERVICES=(server bot ai chronos sockets scheduler bench-api bench-sandbox bench-worker)
export SERVICES

DOCKERHUB_ORG="${DOCKERHUB_USERNAME:-swecc}"
export DOCKERHUB_ORG

SWARM_NETWORK="prod_swecc-network"
export SWARM_NETWORK

# SWAG upstreams use swecc_stack_<service>; Swarm service name stays e.g. server.
SWARM_STACK_NAME="${SWARM_STACK_NAME:-swecc_stack}"
export SWARM_STACK_NAME

swarm_gateway_dns() {
  echo "${SWARM_STACK_NAME}_$1"
}

# Idempotent: attach swecc_stack_* alias on prod_swecc-network (also if create lacked --network-alias).
swarm_ensure_gateway_alias() {
  local svc="$1"
  local alias
  alias="$(swarm_gateway_dns "$svc")"
  docker service update \
    --network-add "name=${SWARM_NETWORK},alias=${alias}" \
    "$svc" >/dev/null 2>&1 || true
}

# Swarm Docker config for --env-file.
# bench-api → bench-api_env (server_env copy + ORCH_* from swecc-infra sync-configs).
# Include BENCH_CORS_ORIGINS with https://mesocosm.swecc.org (and local Vite ports if needed).
# Collision rules:
#   - Shared: DB_* only (django_settings.py), plus ORCH_* for bench (config.Settings)
#   - Shared LLM keys: OPENAI_API_KEY, etc. (both may use LiteLLM)
#   - Do NOT set DJANGO_SETTINGS_MODULE in server_env/bench-api_env (bench-api overrides at boot)
swarm_env_config() {
  local svc="$1"
  case "$svc" in
    bench-api) echo "bench-api_env" ;;
    *) echo "${svc}_env" ;;
  esac
}

# docker service update does not support --env-file (only create does on some versions).
# Apply KEY=value lines via --env-add (updates existing keys).
swarm_service_update_with_env() {
  local svc="$1"
  local env_file="$2"
  shift 2
  local -a update_args=("$@")
  local -a env_add=()
  local line

  [[ -f "$env_file" ]] || die "env file not found: $env_file"

  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    local trimmed="${line#"${line%%[![:space:]]*}"}"
    [[ -z "$trimmed" ]] && continue
    [[ "$trimmed" == \#* ]] && continue
    [[ "$line" != *"="* ]] && continue
    env_add+=(--env-add "$line")
  done <"$env_file"

  if [[ ${#env_add[@]} -eq 0 ]]; then
    die "no env entries in $env_file"
  fi

  swarm_service_update_detached "$svc" "${update_args[@]}" "${env_add[@]}"
}

# Apply Django migrations before rolling the server service. Uses the same
# image and env as production; does not depend on the swarm service CMD (older
# services may still override the image entrypoint with gunicorn-only).
swarm_run_django_migrate() {
  local image="$1"
  local env_file="$2"

  [[ -f "$env_file" ]] || die "env file not found: $env_file"

  log INFO "Running Django migrate (one-shot) on ${SWARM_NETWORK}"
  docker run --rm \
    --network "$SWARM_NETWORK" \
    --env-file "$env_file" \
    "$image" \
    python manage.py migrate --noinput
}

if [[ -t 1 ]]; then
  RED='\033[0;31m'
  GREEN='\033[0;32m'
  YELLOW='\033[0;33m'
  BLUE='\033[0;34m'
  NC='\033[0m'
else
  RED='' GREEN='' YELLOW='' BLUE='' NC=''
fi

log() {
  local level="${1:-INFO}"
  shift
  local msg="$*"
  local timestamp
  timestamp="$(date '+%Y-%m-%d %H:%M:%S')"

  case "$level" in
    INFO)  echo -e "${BLUE}[${timestamp}]${NC} ${GREEN}INFO${NC}  $msg" ;;
    WARN)  echo -e "${BLUE}[${timestamp}]${NC} ${YELLOW}WARN${NC}  $msg" >&2 ;;
    ERROR) echo -e "${BLUE}[${timestamp}]${NC} ${RED}ERROR${NC} $msg" >&2 ;;
    DEBUG) [[ "${DEBUG:-}" == "1" ]] && echo -e "${BLUE}[${timestamp}]${NC} DEBUG $msg" ;;
    *)     echo -e "${BLUE}[${timestamp}]${NC} $level $msg" ;;
  esac
}

die() {
  log ERROR "$@"
  exit 1
}

validate_service() {
  local svc="$1"
  for s in "${SERVICES[@]}"; do
    [[ "$s" == "$svc" ]] && return 0
  done
  die "Unknown service: $svc. Valid services: ${SERVICES[*]}"
}

service_dir() {
  local svc="$1"
  case "$svc" in
    bench-*)
      echo "${REPO_ROOT}/services/bench/${svc#bench-}"
      ;;
    *)
      echo "${REPO_ROOT}/services/${svc}"
      ;;
  esac
}

# Where docker build should run from. For most services this is the same as
# service_dir; for bench-sandbox it's services/bench/ so the Dockerfile can
# COPY common/; bench-api and bench-worker use services/ so they can also
# COPY server/server/bench/ (Django app).
build_context() {
  local svc="$1"
  case "$svc" in
    bench-api|sockets)
      echo "${REPO_ROOT}"
      ;;
    bench-worker)
      echo "${REPO_ROOT}/services"
      ;;
    bench-*)
      echo "${REPO_ROOT}/services/bench"
      ;;
    *)
      echo "${REPO_ROOT}/services/${svc}"
      ;;
  esac
}

# Path to the Dockerfile, relative to build_context.
build_dockerfile() {
  local svc="$1"
  case "$svc" in
    bench-api)
      echo "services/bench/api/Dockerfile"
      ;;
    sockets)
      echo "services/sockets/Dockerfile"
      ;;
    bench-worker)
      echo "bench/worker/Dockerfile"
      ;;
    bench-*)
      echo "${svc#bench-}/Dockerfile"
      ;;
    *)
      echo "Dockerfile"
      ;;
  esac
}

docker_image() {
  local svc="$1"
  local tag="${2:-latest}"
  echo "${DOCKERHUB_ORG}/swecc-${svc}:${tag}"
}

get_resource_limits() {
  local svc="$1"
  case "$svc" in
    bench-sandbox)
      # Reserve low so the task schedules on a ~16GB single-node swarm alongside
      # other services; limit still allows eval workloads to burst when RAM is free.
      echo "CPU_LIMIT=0.5 MEMORY_LIMIT=4G CPU_RESERVE=0.2 MEMORY_RESERVE=512M"
      ;;
    server)
      echo "CPU_LIMIT=0.5 MEMORY_LIMIT=512M CPU_RESERVE=0.2 MEMORY_RESERVE=256M"
      ;;
    scheduler)
      echo "CPU_LIMIT=0.01 MEMORY_LIMIT=64M CPU_RESERVE=0.01 MEMORY_RESERVE=32M"
      ;;
    *)
      echo "CPU_LIMIT=0.3 MEMORY_LIMIT=256M CPU_RESERVE=0.1 MEMORY_RESERVE=128M"
      ;;
  esac
}

require_cmd() {
  local cmd="$1"
  command -v "$cmd" &>/dev/null || die "Required command not found: $cmd"
}

is_github_actions() {
  [[ "${GITHUB_ACTIONS:-}" == "true" ]]
}

git_sha() {
  git -C "${REPO_ROOT}" rev-parse --short HEAD
}

git_sha_full() {
  git -C "${REPO_ROOT}" rev-parse HEAD
}

is_main_branch() {
  local branch
  branch="$(git -C "${REPO_ROOT}" rev-parse --abbrev-ref HEAD)"
  [[ "$branch" == "main" || "$branch" == "master" ]]
}

# Remove leftover *-staging services from failed deploys (frees Swarm memory reservations).
swarm_remove_orphan_staging_services() {
  local name rm_wait
  while IFS= read -r name; do
    [[ -z "$name" ]] && continue
    log WARN "Removing orphaned staging service: $name"
    docker service rm "$name" 2>/dev/null || true
    rm_wait=0
    while docker service inspect "$name" &>/dev/null && [[ $rm_wait -lt 30 ]]; do
      sleep 1
      rm_wait=$((rm_wait + 1))
    done
  done < <(docker service ls --format '{{.Name}}' 2>/dev/null | grep -E -- '-staging$' || true)
}

# Print task states when a swarm service fails to converge (scheduling, OOM, etc.).
swarm_dump_service_tasks() {
  local svc="$1"
  log WARN "Task status for $svc:"
  docker service ps "$svc" --no-trunc 2>/dev/null || true
}

# Fail fast when Swarm cannot place tasks (common on single-node bench-sandbox deploys).
swarm_check_service_scheduling_failure() {
  local svc="$1"
  local err

  err="$(docker service ps "$svc" --no-trunc --format '{{.Error}}' 2>/dev/null \
    | grep -iE 'insufficient resources|no suitable node' | head -1 || true)"
  if [[ -n "$err" ]]; then
    swarm_dump_service_tasks "$svc"
    die "Service $svc cannot be scheduled: $err"
  fi

  if docker service ps "$svc" --filter "desired-state=running" --format "{{.CurrentState}}" \
    2>/dev/null | grep -qE 'Rejected|Failed'; then
    swarm_dump_service_tasks "$svc"
    die "Service $svc has failed or rejected tasks"
  fi
}

wait_for_service() {
  local svc="$1"
  local max_attempts="${2:-30}"
  local attempt=0
  local state

  log INFO "Waiting for service $svc to be healthy..."
  while [[ $attempt -lt $max_attempts ]]; do
    swarm_check_service_scheduling_failure "$svc"
    if docker service ps "$svc" --filter "desired-state=running" --format "{{.CurrentState}}" \
      | grep -q "Running"; then
      log INFO "Service $svc is healthy"
      return 0
    fi
    attempt=$((attempt + 1))
    sleep 2
  done

  swarm_dump_service_tasks "$svc"
  die "Service $svc failed to become healthy after $max_attempts attempts"
}

# Wait for a detached service update to reach a stable running replica set.
wait_for_service_rollout() {
  local svc="$1"
  local timeout_sec="${2:-${DEPLOY_ROLLOUT_TIMEOUT_SEC:-600}}"
  local elapsed=0
  local running desired

  log INFO "Waiting for rollout of $svc (timeout ${timeout_sec}s)..."
  while [[ $elapsed -lt $timeout_sec ]]; do
    swarm_check_service_scheduling_failure "$svc"

    # Use service inspect (not `docker service ls --filter name=^svc$` — anchors are
    # literal substrings in Swarm filters, so replica checks never matched).
    local update_state running_ps want_replicas
    update_state="$(docker service inspect "$svc" --format '{{if .UpdateStatus}}{{.UpdateStatus.State}}{{end}}' 2>/dev/null)" || update_state=""
    if [[ "$update_state" == "completed" ]]; then
      log INFO "Service $svc rollout complete (update status: completed)"
      return 0
    fi

    running="$(docker service inspect "$svc" --format '{{.ServiceStatus.RunningTasks}}' 2>/dev/null)" || running=""
    desired="$(docker service inspect "$svc" --format '{{.ServiceStatus.DesiredTasks}}' 2>/dev/null)" || desired=""

    if [[ -n "$running" && -n "$desired" && "$desired" -gt 0 && "$running" == "$desired" ]]; then
      if docker service ps "$svc" --filter "desired-state=running" --format "{{.CurrentState}}" \
        | grep -q "Running"; then
        log INFO "Service $svc rollout complete (${running}/${desired} tasks running)"
        return 0
      fi
    fi

    running_ps="$(docker service ps "$svc" --filter "desired-state=running" --format '{{.CurrentState}}' \
      | grep -c '^Running' || true)"
    want_replicas="$(docker service inspect "$svc" --format '{{if .Spec.Mode.Replicated}}{{.Spec.Mode.Replicated.Replicas}}{{else}}1{{end}}' 2>/dev/null)" || want_replicas="1"
    if [[ "$running_ps" -ge "$want_replicas" && "$running_ps" -gt 0 ]]; then
      log INFO "Service $svc rollout complete (${running_ps}/${want_replicas} tasks running via service ps)"
      return 0
    fi

    sleep 5
    elapsed=$((elapsed + 5))
  done

  swarm_dump_service_tasks "$svc"
  die "Service $svc rollout timed out after ${timeout_sec}s"
}

# Create a service without blocking on the first task (CLI can spin for 15+ min otherwise).
swarm_service_create_detached() {
  docker service create --detach "$@"
}

# Apply a service update without blocking indefinitely on swarm convergence.
swarm_service_update_detached() {
  local svc="$1"
  shift
  docker service update --detach "$@" "$svc"
}
