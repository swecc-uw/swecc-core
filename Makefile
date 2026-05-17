.PHONY: help test test-all test-ai test-bot test-sockets test-server test-bench test-bench-api test-bench-sandbox test-bench-worker test-coverage install-test-deps clean-test

# Default target
help:
	@echo "SWECC Core - Test Commands"
	@echo ""
	@echo "Available targets:"
	@echo "  make test                - Run all tests"
	@echo "  make test-ai             - Run AI service tests"
	@echo "  make test-bot            - Run bot service tests"
	@echo "  make test-sockets        - Run sockets service tests"
	@echo "  make test-server         - Run server (Django) tests"
	@echo "  make test-bench          - Run all bench-* service tests"
	@echo "  make test-bench-api      - Run bench-api smoke tests"
	@echo "  make test-bench-sandbox  - Run bench-sandbox smoke tests"
	@echo "  make test-bench-worker   - Run bench-worker smoke tests"
	@echo "  make test-coverage       - Run all tests with coverage"
	@echo "  make install-test-deps   - Install test dependencies for all services"
	@echo "  make clean-test          - Clean test artifacts and cache"
	@echo ""

# Run all tests
test:
	./run_tests.sh

test-all: test

# Run individual service tests
test-ai:
	./run_tests.sh ai

test-bot:
	./run_tests.sh bot

test-sockets:
	./run_tests.sh sockets

test-server:
	./run_tests.sh server

test-bench: test-bench-api test-bench-sandbox test-bench-worker

test-bench-api:
	./run_tests.sh bench-api

test-bench-sandbox:
	./run_tests.sh bench-sandbox

test-bench-worker:
	./run_tests.sh bench-worker

# Run tests with coverage
test-coverage:
	./run_tests.sh --coverage

# Install test dependencies
install-test-deps:
	@echo "Installing test dependencies for all services..."
	@cd services/ai && python3 -m pip install -q -r requirements-test.txt
	@cd services/bot && python3 -m pip install -q -r requirements-test.txt
	@cd services/sockets && python3 -m pip install -q -r requirements-test.txt
	@cd services/server && python3 -m pip install -q -r requirements-dev.txt
	@python3 -m pip install -q -e ./services/bench/common
	@cd services/bench/api && python3 -m pip install -q -r requirements-test.txt
	@cd services/bench/sandbox && python3 -m pip install -q -r requirements-test.txt
	@cd services/bench/worker && python3 -m pip install -q -r requirements-test.txt
	@echo "Test dependencies installed!"

# Clean test artifacts
clean-test:
	@echo "Cleaning test artifacts..."
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name ".coverage" -delete 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "Test artifacts cleaned!"
