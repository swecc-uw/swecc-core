FROM python:3.11-slim

# git + build-essentials so user environments can pip install their own deps
# at clone-time inside this container if they need to.
RUN apt-get update && apt-get install -y --no-install-recommends git build-essential && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

COPY bench/common/ /tmp/bench-common/
RUN pip install --no-cache-dir /tmp/bench-common && rm -rf /tmp/bench-common

COPY bench/worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bench/worker/app/ /app/app/

# Django bench app — same as bench-api; schema from swecc-server migrate.
COPY server/server/bench/ /app/bench/

CMD ["python", "-m", "app.worker"]
