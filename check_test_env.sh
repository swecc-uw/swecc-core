#!/bin/bash
# Check if the test environment is properly set up

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "Checking test environment setup..."
echo ""

# Check if virtual environment exists
if [ -d "venv" ]; then
  echo -e "${GREEN}✓${NC} Virtual environment exists"
else
  echo -e "${RED}✗${NC} Virtual environment not found"
  echo "  Run: ./setup_tests.sh"
  exit 1
fi

# Check if virtual environment is activated
if [ -z "$VIRTUAL_ENV" ]; then
  echo -e "${YELLOW}⚠${NC} Virtual environment not activated"
  echo "  Run: source venv/bin/activate"
  exit 1
else
  echo -e "${GREEN}✓${NC} Virtual environment activated: $VIRTUAL_ENV"
fi

# Check if pytest is available
if python3 -m pytest --version &>/dev/null; then
  version=$(python3 -m pytest --version 2>&1 | head -1)
  echo -e "${GREEN}✓${NC} pytest is available: $version"
else
  echo -e "${RED}✗${NC} pytest not found"
  echo "  Run: pip install pytest"
  exit 1
fi

# Check if pytest-asyncio is available
if python3 -c "import pytest_asyncio" 2>/dev/null; then
  echo -e "${GREEN}✓${NC} pytest-asyncio is available"
else
  echo -e "${YELLOW}⚠${NC} pytest-asyncio not found (needed for async tests)"
fi

# Check if pytest-cov is available
if python3 -c "import pytest_cov" 2>/dev/null; then
  echo -e "${GREEN}✓${NC} pytest-cov is available"
else
  echo -e "${YELLOW}⚠${NC} pytest-cov not found (needed for coverage reports)"
fi

echo ""
echo -e "${GREEN}Test environment is ready!${NC}"
echo ""
echo "You can now run tests:"
echo "  ./run_tests.sh"
echo "  make test"
echo "  make test-ai"
