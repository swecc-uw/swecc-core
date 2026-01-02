#!/bin/bash
# Script to run MQ tests with coverage reporting

set -e

echo "========================================="
echo "Running MQ Test Suite"
echo "========================================="
echo ""

# Build the test image
echo "Building test Docker image..."
docker build -t ai-service-test -f Dockerfile.test . -q

echo ""
echo "Running tests..."
echo ""

# Run tests with coverage
docker run --rm ai-service-test pytest \
  tests/test_mq_core.py \
  tests/test_mq_consumers.py \
  tests/test_mq_producers.py \
  --cov=app.mq \
  --cov-report=term-missing \
  --cov-branch \
  -v

echo ""
echo "========================================="
echo "Test Summary"
echo "========================================="
echo "✅ All MQ tests completed"
echo ""
echo "To run specific test files:"
echo "  docker run --rm ai-service-test pytest tests/test_mq_core.py -v"
echo "  docker run --rm ai-service-test pytest tests/test_mq_consumers.py -v"
echo "  docker run --rm ai-service-test pytest tests/test_mq_producers.py -v"
echo ""
echo "To run with detailed coverage:"
echo "  docker run --rm ai-service-test pytest tests/test_mq_*.py --cov=app.mq --cov-report=html"
echo ""
