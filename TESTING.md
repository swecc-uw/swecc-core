# Testing Guide

This document describes the testing infrastructure for the swecc-core monorepo.

## Overview

The monorepo contains Python tests for the following services:
- **AI Service** (`services/ai`) - FastAPI service with pytest
- **Bot Service** (`services/bot`) - Discord bot with pytest
- **Sockets Service** (`services/sockets`) - WebSocket service with pytest
- **Server Service** (`services/server`) - Django application with Django test framework

## Quick Start

### Prerequisites

- Python 3.9 or higher
- pip (Python package installer)

### First-Time Setup

1. Run the setup script to create a virtual environment and install all test dependencies:

```bash
./setup_tests.sh
```

This script will:
- Create a Python virtual environment in `venv/`
- Install all test dependencies for all services
- Set up the environment for running tests

2. Activate the virtual environment:

```bash
source venv/bin/activate
```

**Important:** You must activate the virtual environment every time you want to run tests in a new terminal session.

### Running Tests

Once your environment is set up, you can run tests using either the Makefile or the test runner script:

```bash
# Run all tests
make test

# Run tests for specific services
make test-ai
make test-bot
make test-sockets
make test-server

# Run tests with coverage
make test-coverage

# Using the test runner directly
./run_tests.sh              # All services
./run_tests.sh ai bot       # Specific services
./run_tests.sh --coverage   # With coverage
./run_tests.sh -v ai        # Verbose output
```

## Service-Specific Testing

### AI Service

```bash
cd services/ai
pip install -r requirements-test.txt
pytest tests/ -v
```

**Test Configuration:** `services/ai/pytest.ini`

**Coverage:** Configured to cover the `app` module

### Bot Service

```bash
cd services/bot
pip install -r requirements-test.txt
pytest tests/ -v
```

**Test Configuration:** `services/bot/pytest.ini`

**Coverage:** Configured with branch coverage enabled

### Sockets Service

```bash
cd services/sockets
pip install -r requirements-test.txt
pytest tests/ -v
```

**Test Configuration:** `services/sockets/pytest.ini`

**Coverage:** Configured to cover the `app` module

### Server Service (Django)

```bash
cd services/server
python run_tests.py
```

The server uses a custom test runner (`run_tests.py`) that:
- Configures Django to use SQLite in-memory database for testing
- Sets up required environment variables
- Runs tests for `resume_review` and `contentManage` apps

## Continuous Integration

Tests run automatically on all pull requests via GitHub Actions (`.github/workflows/ci.yml`).

### CI Pipeline

The CI pipeline includes:

1. **Lint Job** - Runs pre-commit hooks on all services
2. **Test Job** - Runs the full test suite for all Python services in parallel
3. **Build Job** - Builds Docker images for changed services

### Test Job Details

- Runs on: `ubuntu-latest`
- Python version: `3.11`
- Strategy: Matrix build for each service (parallel execution)
- Coverage: Generates coverage reports and uploads to Codecov (optional)

## Test Structure

Each service follows this structure:

```
services/<service>/
├── tests/
│   ├── __init__.py
│   ├── conftest.py          # Pytest fixtures and configuration
│   └── test_*.py            # Test files
├── pytest.ini               # Pytest configuration (for pytest-based services)
├── requirements-test.txt    # Test dependencies
└── run_tests.sh            # Optional service-specific test runner
```

## Writing Tests

### Pytest-based Services (AI, Bot, Sockets)

Tests should follow pytest conventions:
- Test files: `test_*.py`
- Test functions: `test_*`
- Test classes: `Test*`

Example:

```python
def test_example():
    assert True

class TestExample:
    def test_method(self):
        assert True
```

### Django Service (Server)

Tests should follow Django conventions:
- Test files: `tests.py` or `tests/` directory in each app
- Test classes: Inherit from `django.test.TestCase`

## Makefile Targets

- `make test` - Run all tests
- `make test-ai` - Run AI service tests
- `make test-bot` - Run bot service tests
- `make test-sockets` - Run sockets service tests
- `make test-server` - Run server tests
- `make test-coverage` - Run all tests with coverage
- `make install-test-deps` - Install test dependencies for all services
- `make clean-test` - Clean test artifacts and cache

## Troubleshooting

### "No module named pytest" or "No module named <package>"

This means you haven't activated the virtual environment or haven't installed dependencies.

**Solution:**
1. Make sure you've run the setup script:
   ```bash
   ./setup_tests.sh
   ```

2. Activate the virtual environment:
   ```bash
   source venv/bin/activate
   ```

3. Verify pytest is available:
   ```bash
   python3 -m pytest --version
   ```

If you see a version number, you're good to go!

### "pip: command not found"

Use the setup script which handles this:
```bash
./setup_tests.sh
```

### Tests fail locally but pass in CI

Ensure you have the latest dependencies:
```bash
source venv/bin/activate
make install-test-deps
```

### Coverage reports not generated

Make sure pytest-cov is installed:
```bash
pip install pytest-cov
```

## Best Practices

1. **Always run tests before pushing** - Use `make test` to verify all tests pass
2. **Write tests for new features** - Maintain or improve code coverage
3. **Use fixtures** - Define reusable test fixtures in `conftest.py`
4. **Mock external dependencies** - Don't make real API calls or database connections in tests
5. **Keep tests fast** - Tests should run quickly to encourage frequent execution
6. **Use descriptive test names** - Test names should clearly describe what they test

## Additional Resources

- [pytest documentation](https://docs.pytest.org/)
- [Django testing documentation](https://docs.djangoproject.com/en/stable/topics/testing/)
- [pytest-asyncio documentation](https://pytest-asyncio.readthedocs.io/)
- [Coverage.py documentation](https://coverage.readthedocs.io/)
