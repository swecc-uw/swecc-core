#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
. "${REPO_ROOT}/s/lib.sh"

SERVICE=""

usage() {
  cat <<EOF
Usage: $0 <service|all>

Services: ${SERVICES[*]}

This script performs a zero-downtime deployment to Docker Swarm:
1. (server only) Runs \`manage.py migrate\` once via \`docker run\` on prod_swecc-network
   before updating the service (bench-api depends on bench_* schema)
2. (Existing service) Rolls production forward with \`docker service update\`
   (stop-first; staging skipped on single-node swarm to avoid memory exhaustion)
3. (New service) Creates the production service on prod_swecc-network with
   --network-alias swecc_stack_<service>

Required environment:
  - DOCKERHUB_USERNAME: Docker Hub username
  - DOCKERHUB_TOKEN: Docker Hub token (for registry auth)

Examples:
  $0 server     # Deploy server service
  $0 all        # Deploy all services
EOF
  exit 1
}

deploy_service() {
  local svc="$1"
  local gateway_alias
  gateway_alias="$(swarm_gateway_dns "$svc")"

  log INFO "Deploying service: $svc"

  require_cmd docker

  local image
  image="$(docker_image "$svc" "latest")"
  local config_name
  config_name="$(swarm_env_config "$svc")"
  local staging_name="${svc}-staging"

  eval "$(get_resource_limits "$svc")"

  log INFO "Image: $image"
  log INFO "Env config: $config_name"
  log INFO "Gateway DNS alias: ${gateway_alias}"
  log INFO "Resources: CPU=$CPU_LIMIT/$CPU_RESERVE, Memory=$MEMORY_LIMIT/$MEMORY_RESERVE"

  swarm_remove_orphan_staging_services

  log INFO "Pulling latest image"
  docker pull "$image"

  log INFO "Preparing environment from Docker config"
  swarm_config_to_env_file "$config_name" "/tmp/${svc}_env.tmp"

  if [[ "$svc" == "bench-api" || "$svc" == "bench-worker" ]]; then
    if ! grep -qE '^ANTHROPIC_API_KEY=.+$' "/tmp/${svc}_env.tmp"; then
      log WARN "ANTHROPIC_API_KEY missing or empty in ${config_name}; Anthropic LLM will fail until config is fixed"
    fi
  fi

  if [[ "$svc" == "server" ]]; then
    swarm_run_django_migrate "$image" "/tmp/${svc}_env.tmp"
  fi

  local service_exists=false
  if docker service inspect "$svc" &>/dev/null; then
    service_exists=true
    log INFO "Service $svc exists, performing zero-downtime update"
  fi

  if [[ "$service_exists" == "true" ]]; then
    swarm_recover_if_no_running_tasks "$svc"

    if docker service inspect "$staging_name" &>/dev/null; then
      log WARN "Removing leftover staging service: $staging_name"
      docker service rm "$staging_name" || die "Failed to remove existing staging service"
      local rm_wait=0
      while docker service inspect "$staging_name" &>/dev/null && [[ $rm_wait -lt 30 ]]; do
        sleep 1
        rm_wait=$((rm_wait + 1))
      done
    fi

    local update_order="start-first"
    if [[ "$svc" == "bench-sandbox" || "$svc" == "server" ]]; then
      update_order="stop-first"
    fi
    log INFO "Rolling update $svc (${update_order}; staging skipped on single-node swarm)"
    local -a update_args=(
      --image "$image"
      --limit-cpu "$CPU_LIMIT"
      --limit-memory "$MEMORY_LIMIT"
      --reserve-cpu "$CPU_RESERVE"
      --reserve-memory "$MEMORY_RESERVE"
      --update-order "$update_order"
      --update-delay 30s
      --update-failure-action rollback
      --with-registry-auth
    )
    swarm_service_update_with_env "$svc" "/tmp/${svc}_env.tmp" "${update_args[@]}" \
      || die "Failed to update service $svc"

    if [[ "$svc" == "bench-api" || "$svc" == "bench-worker" ]]; then
      local llm_key llm_line llm_val
      for llm_key in ANTHROPIC_API_KEY OPENAI_API_KEY; do
        llm_line="$(grep -E "^${llm_key}=" "/tmp/${svc}_env.tmp" | tail -1 || true)"
        [[ -z "$llm_line" ]] && continue
        llm_val="${llm_line#${llm_key}=}"
        [[ -z "$llm_val" ]] && continue
        log INFO "Refreshing ${llm_key} on ${svc} (strip duplicates, set from config)"
        swarm_force_env_var "$svc" "$llm_key" "$llm_val"
      done
    fi

    if [[ "$svc" == "bench-api" ]]; then
      local cors_line cors_val
      cors_line="$(grep -E '^BENCH_CORS_ORIGINS=' "/tmp/${svc}_env.tmp" | tail -1 || true)"
      cors_val=""
      if [[ -n "$cors_line" ]]; then
        cors_val="${cors_line#BENCH_CORS_ORIGINS=}"
      fi
      if [[ -z "$cors_val" ]]; then
        cors_val="https://mesocosm.swecc.org,https://swecc-uw.github.io"
        log INFO "BENCH_CORS_ORIGINS missing or empty in ${config_name}; using prod Mesocosm default"
      fi
      log INFO "Refreshing BENCH_CORS_ORIGINS on ${svc} (strip duplicates, set for Mesocosm CORS)"
      swarm_force_env_var "$svc" "BENCH_CORS_ORIGINS" "$cors_val"
    fi

    wait_for_service_rollout "$svc"
  else
    log INFO "Creating production service: $svc"

    local extra_args=()

    case "$svc" in
      chronos|sockets)
        extra_args+=(--mount "type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock")
        ;;
      chronos)
        extra_args+=(--mount "type=volume,source=chronos_data,target=/app")
        ;;
    esac

    swarm_service_create_detached \
      --name "$svc" \
      --network "$SWARM_NETWORK" \
      --network-alias "$gateway_alias" \
      --env-file /tmp/${svc}_env.tmp \
      --limit-cpu "$CPU_LIMIT" \
      --limit-memory "$MEMORY_LIMIT" \
      --reserve-cpu "$CPU_RESERVE" \
      --reserve-memory "$MEMORY_RESERVE" \
      --restart-condition any \
      --update-order start-first \
      --update-delay 30s \
      --with-registry-auth \
      "${extra_args[@]}" \
      "$image"
  fi

  rm -f /tmp/${svc}_env.tmp
  wait_for_service "$svc"
  swarm_ensure_gateway_alias "$svc"

  log INFO "Successfully deployed $svc"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      ;;
    -*)
      die "Unknown option: $1"
      ;;
    *)
      SERVICE="$1"
      shift
      ;;
  esac
done

[[ -n "$SERVICE" ]] || usage

log INFO "Starting deployment"

case "$SERVICE" in
  all)
    log INFO "Deploying all services"
    for svc in "${SERVICES[@]}"; do
      deploy_service "$svc"
    done
    ;;
  *)
    validate_service "$SERVICE"
    deploy_service "$SERVICE"
    ;;
esac

log INFO "Deployment complete"
