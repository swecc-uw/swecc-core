#!/bin/bash
# TEMP: Nuke bench Swarm services and recreate them via deploy.sh.
#
# Run on the prod Swarm host (self-hosted deploy runner), from repo root:
#   export DOCKERHUB_USERNAME=swecc   # or your org
#   docker login -u "$DOCKERHUB_USERNAME"
#   git checkout fix/deploy-swarm-env-batch   # or main after merge
#   ./s/ops/redeploy-bench-from-scratch.sh
#
# Order: server (migrate + schema) → bench-api → bench-worker → bench-sandbox
#
# Requires: docker swarm manager, Docker configs bench-api_env, bench-sandbox_env,
#           bench-worker_env (or bench-api_env), server_env on the swarm.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
. "${REPO_ROOT}/s/lib.sh"

BENCH_SERVICES=(bench-api bench-worker bench-sandbox)
STAGING_SUFFIX="-staging"

usage() {
  cat <<EOF
Usage: $0 [--yes]

  1. Remove bench-api, bench-worker, bench-sandbox (+ *-staging) Swarm services
  2. Remove any other *-staging orphans
  3. Pull latest images from Docker Hub
  4. deploy.sh server  (Django migrate; bench schema lives in server)
  5. deploy.sh bench-api
  6. deploy.sh bench-worker
  7. deploy.sh bench-sandbox

Environment:
  DOCKERHUB_USERNAME   Required (default: swecc)
  BENCH_REDEPLOY_YES=1 Skip confirmation prompt (same as --yes)

Run from repo root on the Swarm manager host.
EOF
}

confirm() {
  if [[ "${BENCH_REDEPLOY_YES:-}" == "1" ]] || [[ "${1:-}" == "--yes" ]]; then
    return 0
  fi
  echo "This will remove Swarm services: ${BENCH_SERVICES[*]} (+ staging) and redeploy."
  echo "Server will be rolled first for migrations."
  read -r -p "Continue? [y/N] " ans
  [[ "${ans,,}" == "y" || "${ans,,}" == "yes" ]]
}

swarm_wait_service_gone() {
  local svc="$1"
  local wait=0
  while docker service inspect "$svc" &>/dev/null && [[ $wait -lt 60 ]]; do
    sleep 1
    wait=$((wait + 1))
  done
  if docker service inspect "$svc" &>/dev/null; then
    die "Timed out waiting for service $svc to be removed"
  fi
}

swarm_rm_bench_services() {
  local svc staging name
  log INFO "Removing bench Swarm services"
  for svc in "${BENCH_SERVICES[@]}"; do
    staging="${svc}${STAGING_SUFFIX}"
    for name in "$svc" "$staging"; do
      if docker service inspect "$name" &>/dev/null; then
        log WARN "docker service rm $name"
        docker service rm "$name" || die "Failed to remove service $name"
        swarm_wait_service_gone "$name"
      else
        log INFO "Service $name not present (skip)"
      fi
    done
  done
  swarm_remove_orphan_staging_services
}

pull_bench_images() {
  require_cmd docker
  [[ -n "${DOCKERHUB_USERNAME:-}" ]] || die "Set DOCKERHUB_USERNAME before running"
  local svc image
  log INFO "Pulling images (server + bench)"
  for svc in server "${BENCH_SERVICES[@]}"; do
    image="$(docker_image "$svc" "latest")"
    log INFO "Pull $image"
    docker pull "$image"
  done
}

deploy_bench_stack() {
  local deploy="${REPO_ROOT}/s/ops/deploy.sh"
  chmod +x "$deploy" "${REPO_ROOT}/s/lib.sh"

  log INFO "=== deploy server (migrate + roll) ==="
  "$deploy" server

  for svc in "${BENCH_SERVICES[@]}"; do
    log INFO "=== deploy $svc (fresh create after rm) ==="
    "$deploy" "$svc"
  done
}

main() {
  local yes_flag=""
  [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]] && usage && exit 0
  [[ "${1:-}" == "--yes" ]] && yes_flag="--yes"

  require_cmd docker
  docker info --format '{{.Swarm.LocalNodeState}}' 2>/dev/null | grep -q active \
    || die "This host is not in Swarm mode (run on the deploy runner)"

  confirm "$yes_flag" || die "Aborted"

  swarm_rm_bench_services
  pull_bench_images
  deploy_bench_stack

  log INFO "Done. Check tasks:"
  for svc in "${BENCH_SERVICES[@]}"; do
    echo "--- $svc ---"
    docker service ps "$svc" --no-trunc 2>/dev/null || echo "(missing)"
  done
}

main "$@"
