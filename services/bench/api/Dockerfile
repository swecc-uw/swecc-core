FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Install the shared kernel first so its (heavier) deps cache between rebuilds.
# Build context for this image is ./services (not ./services/bench) so we can
# also COPY in the Django bench app from services/server/server/bench/ below.
COPY bench/common/ /tmp/bench-common/
RUN pip install --no-cache-dir /tmp/bench-common && rm -rf /tmp/bench-common

COPY bench/api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bench/api/app/ /app/app/

# The bench Django app lives in services/server/server/bench/ — bench-api
# imports its models in standalone mode via django.setup(). The schema itself
# is provisioned by swecc-server's `manage.py migrate` on startup, so this
# copy is only here so `from bench.models import ...` resolves at runtime.
COPY server/server/bench/ /app/bench/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
