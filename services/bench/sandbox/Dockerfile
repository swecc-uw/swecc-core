FROM python:3.11-slim

# git is required to clone environment repos.
RUN apt-get update && apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    ENVS_DIR=/envs \
    SANDBOX_HOST=swecc-bench-sandbox

COPY common/ /tmp/bench-common/
RUN pip install --no-cache-dir /tmp/bench-common && rm -rf /tmp/bench-common

COPY sandbox/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY sandbox/app/ /app/app/

RUN mkdir -p /envs

EXPOSE 8001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
