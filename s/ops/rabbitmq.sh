#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
. "${REPO_ROOT}/s/lib.sh"

RABBITMQ_SERVICE="${RABBITMQ_SERVICE:-rabbitmq-host}"

usage() {
  cat <<EOF
Usage: $0 <command> [service]

Commands:
  create-user <service>   Create/update RabbitMQ user for a service
  list-users              List all RabbitMQ users

Services that use RabbitMQ: server, bot, ai, sockets

Examples:
  $0 create-user bot    # Create RabbitMQ user for bot service
  $0 list-users         # List all RabbitMQ users
EOF
  exit 1
}

get_rabbitmq_container() {
  log INFO "Finding RabbitMQ container"

  local container_id
  container_id=$(docker ps --filter "name=${RABBITMQ_SERVICE}" --format "{{.ID}}" | head -1)

  [[ -n "$container_id" ]] || die "RabbitMQ container not found"

  echo "$container_id"
}

create_user() {
  local svc="$1"
  validate_service "$svc"

  log INFO "Creating RabbitMQ user for service: $svc"

  local config_name="${svc}_env"
  local container_id
  container_id=$(get_rabbitmq_container)

  log INFO "Loading credentials from Docker config: $config_name"
  docker config inspect "$config_name" --format '{{.Spec.Data}}' | base64 -d > /tmp/${svc}_env.tmp

  local rabbit_user rabbit_pass rabbit_vhost

  case "$svc" in
    bot)
      rabbit_user=$(grep "BOT_RABBIT_USER" /tmp/${svc}_env.tmp | cut -d= -f2)
      rabbit_pass=$(grep "BOT_RABBIT_PASS" /tmp/${svc}_env.tmp | cut -d= -f2)
      ;;
    server)
      rabbit_user=$(grep "SERVER_RABBIT_USER" /tmp/${svc}_env.tmp | cut -d= -f2)
      rabbit_pass=$(grep "SERVER_RABBIT_PASS" /tmp/${svc}_env.tmp | cut -d= -f2)
      ;;
    ai)
      rabbit_user=$(grep "AI_RABBIT_USER" /tmp/${svc}_env.tmp | cut -d= -f2)
      rabbit_pass=$(grep "AI_RABBIT_PASS" /tmp/${svc}_env.tmp | cut -d= -f2)
      ;;
    sockets)
      rabbit_user=$(grep "SOCKET_RABBIT_USER" /tmp/${svc}_env.tmp | cut -d= -f2)
      rabbit_pass=$(grep "SOCKET_RABBIT_PASS" /tmp/${svc}_env.tmp | cut -d= -f2)
      ;;
    *)
      rm -f /tmp/${svc}_env.tmp
      die "Service $svc does not use RabbitMQ"
      ;;
  esac

  rabbit_vhost=$(grep "RABBIT_VHOST" /tmp/${svc}_env.tmp | cut -d= -f2)
  rabbit_vhost="${rabbit_vhost:-/}"

  rm -f /tmp/${svc}_env.tmp

  [[ -n "$rabbit_user" ]] || die "Could not find RabbitMQ user in config"
  [[ -n "$rabbit_pass" ]] || die "Could not find RabbitMQ password in config"

  log INFO "Creating/updating user: $rabbit_user"

  docker exec "$container_id" rabbitmqctl add_user "$rabbit_user" "$rabbit_pass" 2>/dev/null || \
    docker exec "$container_id" rabbitmqctl change_password "$rabbit_user" "$rabbit_pass"

  docker exec "$container_id" rabbitmqctl set_permissions -p "$rabbit_vhost" "$rabbit_user" ".*" ".*" ".*"

  log INFO "Successfully created/updated RabbitMQ user: $rabbit_user"
}

list_users() {
  log INFO "Listing RabbitMQ users"

  local container_id
  container_id=$(get_rabbitmq_container)

  docker exec "$container_id" rabbitmqctl list_users
}

COMMAND="${1:-}"
shift || true

case "$COMMAND" in
  create-user)
    [[ -n "${1:-}" ]] || die "Service name required"
    create_user "$1"
    ;;
  list-users)
    list_users
    ;;
  -h|--help|"")
    usage
    ;;
  *)
    die "Unknown command: $COMMAND"
    ;;
esac
