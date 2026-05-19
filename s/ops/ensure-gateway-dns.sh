#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
# shellcheck source=../lib.sh
. "${REPO_ROOT}/s/lib.sh"

usage() {
  cat <<EOF
Usage: $0 [service ...]
Default: server sockets bench-api

Re-attach swecc_stack_* DNS aliases on prod_swecc-network (safe to re-run).
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
for svc in "${targets[@]}"; do
  swarm_ensure_gateway_routing "$svc" || true
done
