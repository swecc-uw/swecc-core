#!/usr/bin/env bash
# Production: apply Django migrations (including bench schema) before serving traffic.
set -euo pipefail

python manage.py migrate --noinput

exec "$@"
