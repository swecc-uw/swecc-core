#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
. "${REPO_ROOT}/s/lib.sh"

FIX=false
SERVICE=""

usage() {
  cat <<EOF
Usage: $0 <service|all> [options]

Services: ${SERVICES[*]}

Options:
  --fix         Attempt to auto-fix issues where possible
  -h, --help    Show this help message

Examples:
  $0 server           # Lint server service
  $0 all              # Lint all services
  $0 server --fix     # Lint and auto-fix server
EOF
  exit 1
}

lint_python_service() {
  local svc="$1"
  local svc_dir
  svc_dir="$(service_dir "$svc")"

  log INFO "Linting Python service: $svc"

  cd "$svc_dir" || die "Cannot cd to $svc_dir"

  if [[ -f "requirements-dev.txt" ]]; then
    log INFO "Installing dev dependencies"
    pip install -q -r requirements-dev.txt 2>/dev/null || true
  fi

  local exit_code=0
  local pyproject=""
  if [[ -f "pyproject.toml" ]]; then
    pyproject="pyproject.toml"
  elif [[ -f "../pyproject.toml" ]]; then
    pyproject="../pyproject.toml"
  fi

  if command -v black &>/dev/null; then
    log INFO "Running black"
    local black_args=()
    [[ -n "$pyproject" ]] && black_args+=(--config "$pyproject")
    if [[ "$FIX" == "true" ]]; then
      black "${black_args[@]}" . || exit_code=$?
    else
      black --check "${black_args[@]}" . || exit_code=$?
    fi
  fi

  if command -v pre-commit &>/dev/null && [[ -f "${REPO_ROOT}/.pre-commit-config.yaml" ]]; then
    log INFO "Running isort (pre-commit)"
    local -a py_files=()
    while IFS= read -r -d '' f; do
      py_files+=("${f#${REPO_ROOT}/}")
    done < <(find "$svc_dir" -name '*.py' -not -path '*/.venv/*' -print0)
    if ((${#py_files[@]} > 0)); then
      (cd "$REPO_ROOT" && pre-commit run isort --files "${py_files[@]}") || exit_code=$?
    fi
  elif command -v isort &>/dev/null; then
    log INFO "Running isort"
    local isort_args=()
    [[ -n "$pyproject" ]] && isort_args+=(--settings-path "$pyproject")
    if [[ "$FIX" == "true" ]]; then
      isort "${isort_args[@]}" . || exit_code=$?
    else
      isort --check-only "${isort_args[@]}" . || exit_code=$?
    fi
  fi

  if command -v flake8 &>/dev/null; then
    log INFO "Running flake8"
    flake8 . || exit_code=$?
  fi

  if command -v mypy &>/dev/null && [[ -f "setup.cfg" || -f "mypy.ini" || -f "pyproject.toml" ]]; then
    log INFO "Running mypy"
    mypy . || exit_code=$?
  fi

  return $exit_code
}

lint_service() {
  local svc="$1"
  local svc_dir
  svc_dir="$(service_dir "$svc")"

  [[ -d "$svc_dir" ]] || die "Service directory not found: $svc_dir"

  if [[ -f "$svc_dir/requirements.txt" ]] || [[ -f "$svc_dir/requirements-server.txt" ]]; then
    lint_python_service "$svc"
  else
    log WARN "No linting configured for $svc"
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --fix)
      FIX=true
      shift
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

log INFO "Starting lint process"
log INFO "Auto-fix enabled: $FIX"

FAILED=()

case "$SERVICE" in
  all)
    log INFO "Linting all services"
    for svc in "${SERVICES[@]}"; do
      if ! lint_service "$svc"; then
        FAILED+=("$svc")
      fi
    done
    ;;
  *)
    validate_service "$SERVICE"
    if ! lint_service "$SERVICE"; then
      FAILED+=("$SERVICE")
    fi
    ;;
esac

if [[ ${#FAILED[@]} -gt 0 ]]; then
  die "Linting failed for: ${FAILED[*]}"
fi

log INFO "Linting complete - all checks passed"
