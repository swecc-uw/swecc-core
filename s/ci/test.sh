#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
. "${REPO_ROOT}/s/lib.sh"

COVERAGE=false
SERVICE=""

usage() {
  cat <<EOF
Usage: $0 <service|all> [options]

Services: ${SERVICES[*]}

Options:
  --coverage    Generate coverage report
  -h, --help    Show this help message

Examples:
  $0 server              # Run server tests
  $0 all                 # Run all tests
  $0 server --coverage   # Run server tests with coverage
EOF
  exit 1
}

test_python_service() {
  local svc="$1"
  local svc_dir
  svc_dir="$(service_dir "$svc")"
  
  log INFO "Testing Python service: $svc"
  
  cd "$svc_dir" || die "Cannot cd to $svc_dir"
  
  if [[ -f "requirements-dev.txt" ]]; then
    log INFO "Installing dev dependencies"
    pip install -q -r requirements-dev.txt 2>/dev/null || true
  elif [[ -f "requirements.txt" ]]; then
    log INFO "Installing dependencies"
    pip install -q -r requirements.txt 2>/dev/null || true
  fi
  
  if [[ "$svc" == "server" ]] && [[ -d "server" ]]; then
    cd server || die "Cannot cd to server subdirectory"
    
    log INFO "Running Django tests"
    if [[ "$COVERAGE" == "true" ]] && command -v coverage &>/dev/null; then
      coverage run manage.py test
      coverage report
    else
      python manage.py test
    fi
  elif command -v pytest &>/dev/null; then
    log INFO "Running pytest"
    if [[ "$COVERAGE" == "true" ]]; then
      pytest --cov=. --cov-report=term-missing
    else
      pytest
    fi
  else
    log WARN "No test runner found for $svc"
    return 0
  fi
}

test_service() {
  local svc="$1"
  local svc_dir
  svc_dir="$(service_dir "$svc")"
  
  [[ -d "$svc_dir" ]] || die "Service directory not found: $svc_dir"
  
  if [[ -f "$svc_dir/requirements.txt" ]] || [[ -f "$svc_dir/requirements-server.txt" ]]; then
    test_python_service "$svc"
  else
    log WARN "No tests configured for $svc"
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --coverage)
      COVERAGE=true
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

log INFO "Starting test process"
log INFO "Coverage enabled: $COVERAGE"

FAILED=()

case "$SERVICE" in
  all)
    log INFO "Testing all services"
    for svc in "${SERVICES[@]}"; do
      if ! test_service "$svc"; then
        FAILED+=("$svc")
      fi
    done
    ;;
  *)
    validate_service "$SERVICE"
    if ! test_service "$SERVICE"; then
      FAILED+=("$SERVICE")
    fi
    ;;
esac

if [[ ${#FAILED[@]} -gt 0 ]]; then
  die "Tests failed for: ${FAILED[*]}"
fi

log INFO "All tests passed"

