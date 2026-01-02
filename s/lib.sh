#!/bin/bash
set -euo pipefail

[[ "${DEBUG:-}" == "1" ]] && set -x

REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
export REPO_ROOT

SERVICES=(server bot ai chronos sockets scheduler)
export SERVICES

DOCKERHUB_ORG="${DOCKERHUB_USERNAME:-swecc}"
export DOCKERHUB_ORG

SWARM_NETWORK="prod_swecc-network"
export SWARM_NETWORK

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
  echo "${REPO_ROOT}/services/${svc}"
}

docker_image() {
  local svc="$1"
  local tag="${2:-latest}"
  echo "${DOCKERHUB_ORG}/swecc-${svc}:${tag}"
}

get_resource_limits() {
  local svc="$1"
  case "$svc" in
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

wait_for_service() {
  local svc="$1"
  local max_attempts="${2:-30}"
  local attempt=0
  
  log INFO "Waiting for service $svc to be healthy..."
  while [[ $attempt -lt $max_attempts ]]; do
    if docker service ps "$svc" --filter "desired-state=running" --format "{{.CurrentState}}" | grep -q "Running"; then
      log INFO "Service $svc is healthy"
      return 0
    fi
    attempt=$((attempt + 1))
    sleep 2
  done
  
  die "Service $svc failed to become healthy after $max_attempts attempts"
}

