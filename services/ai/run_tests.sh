#!/bin/bash

# AI Service Test Runner
# This script runs the test suite for the AI service

set -e

echo "================================"
echo "AI Service Test Suite"
echo "================================"
echo ""

# Check if we're in the right directory
if [ ! -f "requirements-test.txt" ]; then
    echo "Error: Must be run from services/ai directory"
    exit 1
fi

# Check if pytest is installed
if ! python3 -m pytest --version > /dev/null 2>&1; then
    echo "pytest not found. Installing test dependencies..."
    python3 -m pip install -r requirements-test.txt
fi

echo "Running tests..."
echo ""

# Run tests with coverage
python3 -m pytest tests/ -v \
    --cov=app \
    --cov-report=term-missing \
    --cov-report=html \
    --tb=short

echo ""
echo "================================"
echo "Test run complete!"
echo "================================"
echo ""
echo "Coverage report generated in htmlcov/index.html"
echo ""
