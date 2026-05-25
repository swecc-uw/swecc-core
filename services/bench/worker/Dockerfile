FROM python:3.11-slim

# git + build-essentials so user environments can pip install their own deps
# at clone-time inside this container if they need to.
RUN apt-get update && apt-get install -y --no-install-recommends git build-essential && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

COPY worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY worker/app/ /app/app/

CMD ["python", "-m", "app.worker"]
