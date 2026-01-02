#!/bin/bash

# Bot Service Test Runner
# This script runs the test suite for the Discord bot service

set -e

echo "=========================================="
echo "Bot Service Test Suite"
echo "=========================================="
echo ""

# Check if we're in the right directory
if [ ! -f "main.py" ]; then
    echo "Error: Please run this script from the services/bot directory"
    exit 1
fi

# Check if pytest is installed
if ! python3 -c "import pytest" 2>/dev/null; then
    echo "Installing test dependencies..."
    pip install -r requirements-test.txt
    echo ""
fi

# Run tests
echo "Running tests..."
echo ""

# Run with coverage
python3 -m pytest tests/ -v --cov=. --cov-report=term-missing --cov-report=html --cov-branch

echo ""
echo "=========================================="
echo "Test run complete!"
echo "=========================================="
echo ""
echo "Coverage report saved to htmlcov/index.html"
echo ""
