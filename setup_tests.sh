#!/bin/bash
# Setup script for test environment
# Creates a virtual environment and installs all test dependencies

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}Setting up test environment for swecc-core${NC}"
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv venv
  echo -e "${GREEN}✓ Virtual environment created${NC}"
else
  echo "Virtual environment already exists"
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip -q

# Install test dependencies for each service
echo ""
echo "Installing test dependencies..."

echo "  - AI service..."
pip install -q -r services/ai/requirements-test.txt

echo "  - Bot service..."
pip install -q -r services/bot/requirements-test.txt

echo "  - Sockets service..."
pip install -q -r services/sockets/requirements-test.txt

echo "  - Server service..."
pip install -q -r services/server/requirements-dev.txt

echo ""
echo -e "${GREEN}✓ All test dependencies installed!${NC}"
echo ""
echo "To run tests:"
echo "  1. Activate the virtual environment: source venv/bin/activate"
echo "  2. Run tests: ./run_tests.sh"
echo "  3. Or use make: make test"
echo ""
echo "To deactivate the virtual environment when done:"
echo "  deactivate"
