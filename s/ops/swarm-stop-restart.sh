#!/bin/bash
# TEMPORARY — full stop + remove + recreate for stuck Swarm services.
# Clears paused/updating UpdateStatus by deleting the service and running deploy.sh.
#
# Usage:
#   ./s/ops/swarm-stop-restart.sh bench-api
#   ./s/ops/swarm-stop-restart.sh bench-api bench-worker
#
# Run on the EC2 deploy runner (workflow_dispatch in debug-swarm-stop-restart.yml).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
# shellcheck source=/dev/null
. "${REPO_ROOT}/s/lib.sh"

TARGET_SVCS=()

usage() {
  cat <<EOF
Usage: $0 <service> [service ...]

Full stop and restart (scale to 0, remove service, deploy.sh recreate).
Default target in the workflow is bench-api.

Examples:
  $0 bench-api
  $0 bench-api bench-worker
EOF
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h | --help) usage ;;
    -*) die "Unknown option: $1" ;;
    *)
      validate_service "$1"
      TARGET_SVCS+=("$1")
      shift
      ;;
  esac
done

[[ ${#TARGET_SVCS[@]} -gt 0 ]] || usage

require_cmd docker

if ! docker info --format '{{.Swarm.LocalNodeState}}' 2>/dev/null | grep -qE 'active|manager'; then
  die "This host is not an active Swarm manager (run on the EC2 deploy runner)"
fi

[[ -n "${DOCKERHUB_USERNAME:-}" ]] || die "DOCKERHUB_USERNAME must be set (deploy pulls from Hub)"

wait_for_scale_zero() {
  local svc="$1"
  local timeout_sec="${2:-120}"
  local elapsed=0 running

  while [[ $elapsed -lt $timeout_sec ]]; do
    running="$(docker service ps "$svc" --filter "desired-state=running" --format '{{.CurrentState}}' \
      | grep -c '^Running' || true)"
    if [[ "${running:-0}" -eq 0 ]]; then
      return 0
    fi
    log INFO "Waiting for $svc tasks to stop (${running} still running)..."
    sleep 3
    elapsed=$((elapsed + 3))
  done
  die "Timed out waiting for $svc to scale to 0"
}

wait_for_service_removed() {
  local svc="$1"
  local timeout_sec="${2:-60}"
  local elapsed=0

  while docker service inspect "$svc" &>/dev/null && [[ $elapsed -lt $timeout_sec ]]; do
    sleep 1
    elapsed=$((elapsed + 1))
  done
  if docker service inspect "$svc" &>/dev/null; then
    die "Timed out waiting for service $svc to be removed"
  fi
}

stop_restart_service() {
  local svc="$1"

  echo ""
  echo "══════════════════════════════════════════════════════════════"
  echo "  STOP + RESTART: $svc"
  echo "══════════════════════════════════════════════════════════════"

  if ! docker service inspect "$svc" &>/dev/null; then
    log INFO "Service $svc does not exist; creating via deploy.sh"
    "${REPO_ROOT}/s/ops/deploy.sh" "$svc"
    return 0
  fi

  local update_state replicas
  update_state="$(docker service inspect "$svc" --format '{{if .UpdateStatus}}{{.UpdateStatus.State}}{{end}}' 2>/dev/null || true)"
  replicas="$(docker service inspect "$svc" --format '{{if .Spec.Mode.Replicated}}{{.Spec.Mode.Replicated.Replicas}}{{else}}1{{end}}' 2>/dev/null || echo "?")"
  log INFO "Before stop: UpdateStatus=${update_state:-<none>} replicas=${replicas}"

  log INFO "Step 1/3: scale $svc to 0 (full stop)"
  docker service scale "$svc=0" || die "Failed to scale $svc to 0"
  wait_for_scale_zero "$svc"

  log INFO "Step 2/3: remove $svc (clear stuck Swarm update state)"
  docker service rm "$svc" || die "Failed to remove service $svc"
  wait_for_service_removed "$svc"
  log INFO "Service $svc removed"

  swarm_remove_orphan_staging_services

  log INFO "Step 3/3: recreate $svc via deploy.sh"
  "${REPO_ROOT}/s/ops/deploy.sh" "$svc"
  log INFO "Stop + restart complete for $svc"
}

main() {
  log INFO "Swarm stop-restart for: ${TARGET_SVCS[*]}"
  local svc
  for svc in "${TARGET_SVCS[@]}"; do
    stop_restart_service "$svc"
  done
  log INFO "Done."
}

main
