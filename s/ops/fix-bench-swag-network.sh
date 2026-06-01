#!/bin/bash
# TEMP: Re-attach bench Swarm services to swag-network (fixes public 502 after scratch redeploy).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
. "${REPO_ROOT}/s/lib.sh"

for svc in bench-api bench-worker bench-sandbox; do
  swarm_ensure_gateway_alias "$svc"
  swarm_ensure_swag_network_alias "$svc"
done
swarm_curl_bench_health
log INFO "Done — retry https://api.swecc.org/bench/health"
