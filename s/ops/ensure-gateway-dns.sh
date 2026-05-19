#!/bin/bash
# Register swecc_stack_<service> aliases on prod_swecc-network (SWAG / swecc-infra nginx).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
# shellcheck source=../lib.sh
. "${REPO_ROOT}/s/lib.sh"

usage() {
  cat <<EOF
Usage: $0 [service ...]

Services: ${SERVICES[*]}
Default (no args): server sockets bench-api
EOF
  exit 1
}

ensure_alias() {
  local svc="$1"
  local alias
  alias="$(swarm_gateway_dns "$svc")"

  if ! docker service inspect "$svc" &>/dev/null; then
    log WARN "Swarm service '$svc' does not exist — deploy it first"
    return 1
  fi

  log INFO "Ensuring alias ${alias} on ${svc}"
  if docker service update \
    --network-add "name=${SWARM_NETWORK},alias=${alias}" \
    "$svc" >/dev/null 2>&1; then
    log INFO "Alias ${alias} applied"
    return 0
  fi

  log WARN "Alias may already exist on ${svc}"
  return 0
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
