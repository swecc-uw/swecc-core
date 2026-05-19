#!/bin/bash
# Add swecc_stack_<service> network alias on an existing swarm service (post-deploy repair).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
# shellcheck source=../lib.sh
. "${REPO_ROOT}/s/lib.sh"

ensure_alias() {
  local svc="$1"
  local alias
  alias="$(swarm_gateway_dns "$svc")"

  if ! docker service inspect "$svc" &>/dev/null; then
    log WARN "Service '$svc' not found"
    return 1
  fi

  log INFO "Ensuring network alias ${alias} on ${svc}"
  if docker service update \
    --network-add "name=${SWARM_NETWORK},alias=${alias}" \
    "$svc" >/dev/null 2>&1; then
    log INFO "Alias ${alias} added"
    return 0
  fi

  log WARN "Alias ${alias} may already exist on ${svc}"
  return 0
}

usage() {
  cat <<EOF
Usage: $0 [service ...]
Default: server sockets bench-api
EOF
  exit 1
}

targets=()
if [[ $# -eq 0 ]]; then
  targets=(server sockets bench-api)
else
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -h|--help) usage ;;
      *) validate_service "$1"; targets+=("$1"); shift ;;
    esac
  done
fi

require_cmd docker
failed=0
for svc in "${targets[@]}"; do
  ensure_alias "$svc" || failed=1
done
exit "$failed"
