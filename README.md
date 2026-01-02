# swecc-core

Monorepo for SWECC's backend services.

## Services

| Service | Port | Description |
|---------|------|-------------|
| server | 8000 | Django API - handles auth, interviews, mentorship |
| sockets | 8004 | WebSocket server for real-time features |
| bot | - | Discord bot |
| ai | 8008 | AI/ML service (resume review, etc.) |
| chronos | 8002 | Metrics collection |
| scheduler | - | Cron job runner |

## Local Development

```bash
# Start everything
docker compose up

# Start specific services
docker compose up server bot

# With nginx reverse proxy
docker compose --profile with-nginx up
```

Needs a `.env` file in the root. Ask @elimelt for the file.

## Testing

### Setup Test Environment

**Required:** You must have a Python virtual environment with test dependencies installed.

First-time setup (creates virtual environment and installs all dependencies):

```bash
./setup_tests.sh
source venv/bin/activate
```

**Important:** Always activate the virtual environment before running tests:
```bash
source venv/bin/activate
```

### Running Tests Locally

The monorepo includes a unified test runner for all Python services:

```bash
# Run all tests
make test
# or
./run_tests.sh

# Run tests for specific services
make test-ai
make test-bot
make test-sockets
make test-server

# Run tests with coverage
make test-coverage
# or
./run_tests.sh --coverage

# Install test dependencies
make install-test-deps

# Clean test artifacts
make clean-test
```

### Individual Service Tests

Each service can also be tested independently:

```bash
# AI service
cd services/ai
pip install -r requirements-test.txt
pytest tests/ -v

# Bot service
cd services/bot
pip install -r requirements-test.txt
pytest tests/ -v

# Sockets service
cd services/sockets
pip install -r requirements-test.txt
pytest tests/ -v

# Server (Django)
cd services/server
python run_tests.py
```

### CI/CD

Tests run automatically on all pull requests. The CI pipeline:
- Runs linting checks for all services
- Runs the full test suite for all Python services
- Generates coverage reports
- Builds Docker images for changed services

## Scripts

```bash
./s/ci/build.sh <service|all> [--push]   # Build Docker images
./s/ci/lint.sh <service|all> [--fix]     # Run linters
./s/ci/test.sh <service|all>             # Run tests (legacy)
./s/ops/deploy.sh <service>              # Deploy to swarm (CI only)
./run_tests.sh [OPTIONS] [SERVICES...]   # Run tests (recommended)
```

## Deployment

Push to `main` triggers deployment for changed services. Each service deploys independently based on path filters.

To deploy everything manually: Actions → "Deploy All Services" → type `deploy-all` to confirm.

## Secrets

Managed via GitHub repository secrets. To update:

```bash
gh secret set SECRET_NAME --body "value"
```
