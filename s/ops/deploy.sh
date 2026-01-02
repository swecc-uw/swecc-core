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
1. Creates a staging service with the new image
2. Waits for staging to be healthy
3. Promotes staging to production
4. Removes the old production service

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
  
  log INFO "Deploying service: $svc"
  
  require_cmd docker
  
  local image
  image="$(docker_image "$svc" "latest")"
  local config_name="${svc}_env"
  local staging_name="${svc}-staging"
  
  eval "$(get_resource_limits "$svc")"
  
  log INFO "Image: $image"
  log INFO "Config: $config_name"
  log INFO "Resources: CPU=$CPU_LIMIT/$CPU_RESERVE, Memory=$MEMORY_LIMIT/$MEMORY_RESERVE"
  
  log INFO "Pulling latest image"
  docker pull "$image"
  
  log INFO "Preparing environment from Docker config"
  docker config inspect "$config_name" --format '{{.Spec.Data}}' | base64 -d > /tmp/${svc}_env.tmp || true
  
  local service_exists=false
  if docker service inspect "$svc" &>/dev/null; then
    service_exists=true
    log INFO "Service $svc exists, performing zero-downtime update"
  fi
  
  if [[ "$service_exists" == "true" ]]; then
    log INFO "Creating staging service: $staging_name"
    
    docker service create \
      --name "$staging_name" \
      --network "$SWARM_NETWORK" \
      --env-file /tmp/${svc}_env.tmp \
      --limit-cpu "$CPU_LIMIT" \
      --limit-memory "$MEMORY_LIMIT" \
      --reserve-cpu "$CPU_RESERVE" \
      --reserve-memory "$MEMORY_RESERVE" \
      --restart-condition any \
      --with-registry-auth \
      "$image" || die "Failed to create staging service"
    
    wait_for_service "$staging_name"
    
    log INFO "Promoting staging to production"
    docker service update --hostname "$svc" "$staging_name"
    
    log INFO "Removing old production service"
    docker service rm "$svc" || true
  fi
  
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
  
  docker service create \
    --name "$svc" \
    --network "$SWARM_NETWORK" \
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
  
  log INFO "Cleaning up"
  docker service rm "$staging_name" 2>/dev/null || true
  rm -f /tmp/${svc}_env.tmp
  
  wait_for_service "$svc"
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

