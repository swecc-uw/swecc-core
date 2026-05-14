#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
. "${REPO_ROOT}/s/lib.sh"

PUSH=false
TAG="latest"
SERVICE=""

usage() {
  cat <<EOF
Usage: $0 <service|all> [options]

Services: ${SERVICES[*]}

Options:
  --push        Push images to Docker Hub after building
  --tag <tag>   Tag for the image (default: latest)
  -h, --help    Show this help message

Examples:
  $0 server                    # Build server image
  $0 all --push                # Build and push all images
  $0 bot --tag v1.0.0 --push   # Build and push bot with specific tag
EOF
  exit 1
}

build_service() {
  local svc="$1"
  local svc_dir context dockerfile
  svc_dir="$(service_dir "$svc")"
  context="$(build_context "$svc")"
  dockerfile="$(build_dockerfile "$svc")"

  log INFO "Building Docker image for $svc"

  [[ -d "$svc_dir" ]] || die "Service directory not found: $svc_dir"
  [[ -f "${context}/${dockerfile}" ]] || die "Dockerfile not found at ${context}/${dockerfile}"

  local image
  image="$(docker_image "$svc" "$TAG")"
  local image_sha
  image_sha="$(docker_image "$svc" "$(git_sha_full)")"

  log INFO "Image: $image"
  log INFO "Build context: $context"
  log INFO "Dockerfile: $dockerfile"

  docker build -t "$image" -t "$image_sha" -f "${context}/${dockerfile}" "$context"

  if [[ "$PUSH" == "true" ]]; then
    log INFO "Pushing $image to Docker Hub"
    docker push "$image"
    docker push "$image_sha"
  fi

  log INFO "Successfully built $svc"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --push)
      PUSH=true
      shift
      ;;
    --tag)
      TAG="$2"
      shift 2
      ;;
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

log INFO "Starting build process"
log INFO "Push enabled: $PUSH"
log INFO "Tag: $TAG"

case "$SERVICE" in
  all)
    log INFO "Building all services"
    for svc in "${SERVICES[@]}"; do
      build_service "$svc"
    done
    ;;
  *)
    validate_service "$SERVICE"
    build_service "$SERVICE"
    ;;
esac

log INFO "Build complete"
