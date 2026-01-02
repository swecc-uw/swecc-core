#!/bin/bash
# Unified test runner for swecc-core monorepo
# Runs Python tests for all services or specific services

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
COVERAGE=false
VERBOSE=false
SERVICES=()
ALL_SERVICES=(ai bot sockets server)
FAILED_SERVICES=()

usage() {
  cat <<EOF
Usage: $0 [OPTIONS] [SERVICES...]

Run tests for Python services in the monorepo.

OPTIONS:
  -c, --coverage    Generate coverage reports
  -v, --verbose     Verbose output
  -h, --help        Show this help message

SERVICES:
  ai                Run AI service tests
  bot               Run bot service tests
  sockets           Run sockets service tests
  server            Run server (Django) tests
  all               Run all service tests (default)

EXAMPLES:
  $0                    # Run all tests
  $0 ai bot             # Run tests for ai and bot services
  $0 --coverage server  # Run server tests with coverage
  $0 -v all             # Run all tests with verbose output

EOF
  exit 0
}

log() {
  local level=$1
  shift
  case $level in
    INFO)  echo -e "${BLUE}[INFO]${NC} $*" ;;
    WARN)  echo -e "${YELLOW}[WARN]${NC} $*" ;;
    ERROR) echo -e "${RED}[ERROR]${NC} $*" ;;
    SUCCESS) echo -e "${GREEN}[SUCCESS]${NC} $*" ;;
  esac
}

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    -c|--coverage)
      COVERAGE=true
      shift
      ;;
    -v|--verbose)
      VERBOSE=true
      shift
      ;;
    -h|--help)
      usage
      ;;
    all)
      SERVICES=("${ALL_SERVICES[@]}")
      shift
      ;;
    ai|bot|sockets|server)
      SERVICES+=("$1")
      shift
      ;;
    *)
      log ERROR "Unknown option or service: $1"
      usage
      ;;
  esac
done

# Default to all services if none specified
if [ ${#SERVICES[@]} -eq 0 ]; then
  SERVICES=("${ALL_SERVICES[@]}")
fi

# Function to test AI service
test_ai() {
  log INFO "Testing AI service..."
  cd services/ai

  # Check if pytest is available
  if ! python3 -m pytest --version &>/dev/null; then
    log ERROR "pytest not found. Please install test dependencies:"
    log ERROR "  pip install -r services/ai/requirements-test.txt"
    log ERROR "Or run: ./setup_tests.sh && source venv/bin/activate"
    return 1
  fi

  # Install/update service dependencies
  log INFO "Installing service dependencies..."
  python3 -m pip install -q -r requirements-test.txt 2>&1 | grep -v "Requirement already satisfied" || true

  local pytest_args=("tests/" "-v")
  if [ "$COVERAGE" = true ]; then
    pytest_args+=("--cov=app" "--cov-report=term-missing" "--cov-report=html:htmlcov/ai")
  fi

  python3 -m pytest "${pytest_args[@]}"
  local exit_code=$?
  cd "$SCRIPT_DIR"
  return $exit_code
}

# Function to test bot service
test_bot() {
  log INFO "Testing bot service..."
  cd services/bot

  # Check if pytest is available
  if ! python3 -m pytest --version &>/dev/null; then
    log ERROR "pytest not found. Please install test dependencies:"
    log ERROR "  pip install -r services/bot/requirements-test.txt"
    log ERROR "Or run: ./setup_tests.sh && source venv/bin/activate"
    return 1
  fi

  # Install/update service dependencies
  log INFO "Installing service dependencies..."
  python3 -m pip install -q -r requirements-test.txt 2>&1 | grep -v "Requirement already satisfied" || true

  local pytest_args=("tests/" "-v")
  if [ "$COVERAGE" = true ]; then
    pytest_args+=("--cov=." "--cov-report=term-missing" "--cov-report=html:htmlcov/bot" "--cov-branch")
  fi

  python3 -m pytest "${pytest_args[@]}"
  local exit_code=$?
  cd "$SCRIPT_DIR"
  return $exit_code
}

# Function to test sockets service
test_sockets() {
  log INFO "Testing sockets service..."
  cd services/sockets

  # Check if pytest is available
  if ! python3 -m pytest --version &>/dev/null; then
    log ERROR "pytest not found. Please install test dependencies:"
    log ERROR "  pip install -r services/sockets/requirements-test.txt"
    log ERROR "Or run: ./setup_tests.sh && source venv/bin/activate"
    return 1
  fi

  # Install/update service dependencies
  log INFO "Installing service dependencies..."
  python3 -m pip install -q -r requirements-test.txt 2>&1 | grep -v "Requirement already satisfied" || true

  local pytest_args=("tests/" "-v")
  if [ "$COVERAGE" = true ]; then
    pytest_args+=("--cov=app" "--cov-report=term-missing" "--cov-report=html:htmlcov/sockets")
  fi

  python3 -m pytest "${pytest_args[@]}"
  local exit_code=$?
  cd "$SCRIPT_DIR"
  return $exit_code
}

# Function to test server (Django)
test_server() {
  log INFO "Testing server (Django)..."
  cd services/server

  # Use the existing run_tests.py script which handles Django setup
  if [ "$COVERAGE" = true ]; then
    log WARN "Coverage not yet implemented for Django tests"
  fi

  python3 run_tests.py
  local exit_code=$?
  cd "$SCRIPT_DIR"
  return $exit_code
}

# Main test execution
log INFO "Starting test run for services: ${SERVICES[*]}"
echo ""

for service in "${SERVICES[@]}"; do
  echo ""
  log INFO "========================================="
  log INFO "Testing: $service"
  log INFO "========================================="

  # Run test and capture exit code
  set +e  # Temporarily disable exit on error
  test_"$service"
  exit_code=$?
  set -e  # Re-enable exit on error

  if [ $exit_code -eq 0 ]; then
    log SUCCESS "✓ $service tests passed"
  else
    log ERROR "✗ $service tests failed (exit code: $exit_code)"
    FAILED_SERVICES+=("$service")
  fi
done

echo ""
log INFO "========================================="
log INFO "Test Summary"
log INFO "========================================="

if [ ${#FAILED_SERVICES[@]} -eq 0 ]; then
  log SUCCESS "All tests passed! ✓"
  exit 0
else
  log ERROR "Failed services: ${FAILED_SERVICES[*]}"
  exit 1
fi
