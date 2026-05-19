#!/bin/bash
# Register swecc_stack_<service> DNS aliases on prod_swecc-network so SWAG/nginx
# (api.swecc.org.subdomain.conf) can reach services created by deploy.sh.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
# shellcheck source=../lib.sh
. "${REPO_ROOT}/s/lib.sh"

usage() {
  cat <<EOF
Usage: $0 [service ...]

Services: ${SERVICES[*]}

With no args, fixes bench-api only (the usual /bench/health 502).

Examples:
  $0 bench-api
  $0 server bench-api
EOF
  exit 1
}

ensure_alias() {
  local svc="$1"
  local alias
  alias="$(swarm_gateway_dns "$svc")"

  if ! docker service inspect "$svc" &>/dev/null; then
    log WARN "Swarm service '$svc' does not exist — run Deploy $svc workflow first"
    return 1
  fi

  log INFO "Adding gateway alias ${alias} on ${svc} (${SWARM_NETWORK})"
  if docker service update \
    --network-add "name=${SWARM_NETWORK},alias=${alias}" \
    "$svc" >/dev/null; then
    log INFO "Alias ${alias} applied"
    return 0
  fi

  log WARN "Could not add alias (may already exist) — checking tasks"
  docker service ps "$svc" --no-trunc | head -5 || true
  return 0
}

targets=()
if [[ $# -eq 0 ]]; then
  targets=(bench-api)
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
