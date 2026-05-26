#!/usr/bin/env bash
# Resolve Docker build context and Dockerfile for a service (CI + prod deploy).
# Usage: resolve-docker-build.sh <service> [context_override] [dockerfile_override]
set -euo pipefail

svc="${1:?service name required}"
context_override="${2:-}"
dockerfile_override="${3:-}"

CONTEXT=""
FILE=""

if [[ -n "$context_override" ]]; then
  CONTEXT="$context_override"
  FILE="${dockerfile_override:-Dockerfile}"
  if [[ "$FILE" != /* && "$FILE" != ./* ]]; then
    FILE="${CONTEXT%/}/${FILE}"
  fi
else
  case "$svc" in
    bench-api)
      CONTEXT="."
      FILE="./services/bench/api/Dockerfile"
      ;;
    sockets)
      CONTEXT="."
      FILE="./services/sockets/Dockerfile"
      ;;
    bench-sandbox)
      CONTEXT="./services/bench"
      FILE="./services/bench/sandbox/Dockerfile"
      ;;
    bench-worker)
      CONTEXT="./services"
      FILE="./services/bench/worker/Dockerfile"
      ;;
    *)
      CONTEXT="./services/${svc}"
      FILE="./services/${svc}/Dockerfile"
      ;;
  esac
fi

if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  {
    echo "context=${CONTEXT}"
    echo "file=${FILE}"
  } >>"$GITHUB_OUTPUT"
else
  echo "context=${CONTEXT}"
  echo "file=${FILE}"
fi
