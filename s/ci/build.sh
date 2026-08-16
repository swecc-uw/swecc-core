#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
. "${REPO_ROOT}/s/lib.sh"

PUSH=false
TAG="latest"
SERVICE=""
PLATFORMS=""

usage() {
  cat <<EOF
Usage: $0 <service|all> [options]

Services: ${SERVICES[*]}

Options:
  --push        Push images to Docker Hub after building
  --tag <tag>   Tag for the image (default: latest)
  --platforms <list>
                Target platforms (default: host for local builds, amd64+arm64 with --push)
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

  local target_platforms="$PLATFORMS"
  if [[ -z "$target_platforms" ]]; then
    if [[ "$PUSH" == "true" ]]; then
      target_platforms="linux/amd64,linux/arm64"
    else
      target_platforms="$(docker info --format '{{.OSType}}/{{.Architecture}}')" \
        || die "Unable to determine the local Docker platform; pass --platforms explicitly"
    fi
  fi

  local -a build_args=(
    buildx build
    --platform "$target_platforms"
    -t "$image"
    -t "$image_sha"
    -f "${context}/${dockerfile}"
  )

  if [[ "$PUSH" == "true" ]]; then
    build_args+=(--push)
  else
    # A multi-platform image cannot be loaded into the local Docker image
    # store.
    if [[ "$target_platforms" == *,* ]]; then
      die "Local multi-platform builds require --push; use --platforms linux/amd64 (or linux/arm64) for --load"
    fi
    build_args+=(--load)
  fi

  build_args+=("${context}")
  docker "${build_args[@]}"

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
    --platforms)
      PLATFORMS="$2"
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
