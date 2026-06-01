#!/bin/bash
# Temporary Swarm deploy diagnostics + optional recovery for stuck docker service updates.
#
# Run on the EC2 deploy runner (same host as s/ops/deploy.sh), e.g. via:
#   .github/workflows/debug-swarm-deploy.yml  (workflow_dispatch)
#
# Usage:
#   ./s/ops/swarm-deploy-diagnose.sh                    # diagnose bench stack
#   ./s/ops/swarm-deploy-diagnose.sh server bench-sandbox
#   ./s/ops/swarm-deploy-diagnose.sh --recover          # diagnose + force-unstick
#   ./s/ops/swarm-deploy-diagnose.sh --recover --redeploy server bench-api
#
# Secrets are never printed — env output is key names / duplicate counts only.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
# shellcheck source=/dev/null
. "${REPO_ROOT}/s/lib.sh"

RECOVER=0
REDEPLOY=0
SERVICES=()

usage() {
  cat <<EOF
Usage: $0 [--recover] [--redeploy] [service ...]

  --recover   Clear paused/stuck Swarm updates (--rollback then --force when needed)
  --redeploy  After --recover, run s/ops/deploy.sh for each service (needs DOCKERHUB_* on runner)

Default services (when none listed): server bench-api bench-sandbox bench-worker

Examples:
  $0
  $0 --recover server bench-sandbox
  $0 --recover --redeploy bench-api
EOF
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h | --help) usage ;;
    --recover) RECOVER=1; shift ;;
    --redeploy) REDEPLOY=1; shift ;;
    -*) die "Unknown option: $1" ;;
    *)
      validate_service "$1"
      SERVICES+=("$1")
      shift
      ;;
  esac
done

if [[ ${#SERVICES[@]} -eq 0 ]]; then
  SERVICES=(server bench-api bench-sandbox bench-worker)
fi

if [[ "$REDEPLOY" -eq 1 && "$RECOVER" -ne 1 ]]; then
  die "--redeploy requires --recover"
fi

require_cmd docker

if ! docker info --format '{{.Swarm.LocalNodeState}}' 2>/dev/null | grep -qE 'active|manager'; then
  die "This host is not an active Swarm manager (run on the EC2 deploy runner)"
fi

print_service_header() {
  local svc="$1"
  echo ""
  echo "══════════════════════════════════════════════════════════════"
  echo "  SERVICE: $svc"
  echo "══════════════════════════════════════════════════════════════"
}

diagnose_service() {
  local svc="$1"

  if ! docker service inspect "$svc" &>/dev/null; then
    log WARN "Service $svc does not exist on this Swarm"
    return 1
  fi

  print_service_header "$svc"

  local update_state update_msg started
  update_state="$(docker service inspect "$svc" --format '{{if .UpdateStatus}}{{.UpdateStatus.State}}{{end}}' 2>/dev/null || true)"
  update_msg="$(docker service inspect "$svc" --format '{{if .UpdateStatus}}{{.UpdateStatus.Message}}{{end}}' 2>/dev/null || true)"
  started="$(docker service inspect "$svc" --format '{{if .UpdateStatus}}{{.UpdateStatus.StartedAt}}{{end}}' 2>/dev/null || true)"

  echo "UpdateStatus.state:   ${update_state:-<none>}"
  echo "UpdateStatus.message: ${update_msg:-<none>}"
  echo "UpdateStatus.started: ${started:-<none>}"

  local running desired replicas
  running="$(docker service inspect "$svc" --format '{{.ServiceStatus.RunningTasks}}' 2>/dev/null || echo "?")"
  desired="$(docker service inspect "$svc" --format '{{.ServiceStatus.DesiredTasks}}' 2>/dev/null || echo "?")"
  replicas="$(docker service inspect "$svc" --format '{{if .Spec.Mode.Replicated}}{{.Spec.Mode.Replicated.Replicas}}{{else}}1{{end}}' 2>/dev/null || echo "?")"
  echo "Tasks: running=${running} desired=${desired} spec.replicas=${replicas}"

  local image
  image="$(docker service inspect "$svc" --format '{{.Spec.TaskTemplate.ContainerSpec.Image}}' 2>/dev/null || true)"
  echo "Image: ${image:-<unknown>}"

  echo ""
  echo "--- duplicate env keys (count key_name) ---"
  docker service inspect "$svc" --format '{{range .Spec.TaskTemplate.ContainerSpec.Env}}{{println .}}{{end}}' 2>/dev/null \
    | awk -F= '{print $1}' | sort | uniq -c | sort -rn | head -20 || true

  local env_total dup_keys
  env_total="$(docker service inspect "$svc" --format '{{range .Spec.TaskTemplate.ContainerSpec.Env}}{{println .}}{{end}}' 2>/dev/null | grep -c . || true)"
  dup_keys="$(docker service inspect "$svc" --format '{{range .Spec.TaskTemplate.ContainerSpec.Env}}{{println .}}{{end}}' 2>/dev/null \
    | awk -F= '{print $1}' | sort | uniq -cd | wc -l | tr -d ' ')"
  echo "Env entries on service: ${env_total:-0}  (keys with duplicates: ${dup_keys:-0})"

  echo ""
  echo "--- recent tasks ---"
  docker service ps "$svc" --no-trunc --format 'table {{.Name}}\t{{.CurrentState}}\t{{.Error}}' 2>/dev/null | head -8 || true

  if [[ -n "$update_state" && "$update_state" != "completed" ]]; then
    log WARN "$svc may block deploy.sh (UpdateStatus=${update_state})"
    return 2
  fi
  return 0
}

recover_service() {
  local svc="$1"
  local update_state

  if ! docker service inspect "$svc" &>/dev/null; then
    log WARN "Skip recover — service $svc not found"
    return 0
  fi

  update_state="$(docker service inspect "$svc" --format '{{if .UpdateStatus}}{{.UpdateStatus.State}}{{end}}' 2>/dev/null || true)"

  case "$update_state" in
    paused | updating | rollback_started | rollback_paused)
      log WARN "Recover $svc: UpdateStatus=$update_state — rollback then force"
      if docker service update --rollback --detach "$svc" 2>/dev/null; then
        log INFO "Rollback accepted for $svc"
        sleep 3
      else
        log WARN "Rollback not accepted for $svc (may already be rolling back)"
      fi
      docker service update --force --detach "$svc" \
        || die "Force update failed for $svc"
      sleep 2
      ;;
    completed | "")
      log INFO "Recover $svc: no stuck UpdateStatus; optional force reschedule"
      docker service update --force --detach "$svc" \
        || die "Force update failed for $svc"
      sleep 2
      ;;
    *)
      log WARN "Recover $svc: unknown UpdateStatus=$update_state — trying force"
      docker service update --force --detach "$svc" \
        || die "Force update failed for $svc"
      sleep 2
      ;;
  esac

  swarm_recover_if_no_running_tasks "$svc" || true
  log INFO "Post-recover task summary for $svc:"
  docker service ps "$svc" --format 'table {{.Name}}\t{{.CurrentState}}\t{{.Error}}' 2>/dev/null | head -6 || true
}

redeploy_service() {
  local svc="$1"
  [[ -n "${DOCKERHUB_USERNAME:-}" ]] || die "DOCKERHUB_USERNAME must be set for --redeploy"
  log INFO "Redeploying $svc via deploy.sh"
  "${REPO_ROOT}/s/ops/deploy.sh" "$svc"
}

main() {
  log INFO "Swarm deploy diagnose (recover=${RECOVER} redeploy=${REDEPLOY})"
  log INFO "Services: ${SERVICES[*]}"

  local blocked=0
  local svc
  for svc in "${SERVICES[@]}"; do
    diagnose_service "$svc" || blocked=$((blocked + 1)) || true
  done

  if [[ "$RECOVER" -eq 1 ]]; then
    log INFO "Beginning recovery pass"
    for svc in "${SERVICES[@]}"; do
      recover_service "$svc"
    done
    blocked=0
    for svc in "${SERVICES[@]}"; do
      diagnose_service "$svc" || blocked=$((blocked + 1)) || true
    done
  fi

  if [[ "$REDEPLOY" -eq 1 ]]; then
    for svc in "${SERVICES[@]}"; do
      redeploy_service "$svc"
    done
  fi

  echo ""
  if [[ "$blocked" -gt 0 && "$RECOVER" -eq 0 ]]; then
    log WARN "Some services look stuck. Re-run with --recover (and optionally --redeploy)."
    exit 2
  fi

  log INFO "Done."
}

main
