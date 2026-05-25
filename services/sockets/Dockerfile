FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

COPY packages/swecc-jwt /tmp/swecc-jwt/
RUN pip install --no-cache-dir /tmp/swecc-jwt && rm -rf /tmp/swecc-jwt

COPY services/sockets/socket.requirements.txt .
RUN pip install --no-cache-dir -r socket.requirements.txt

COPY services/sockets/app/ /app/app/

EXPOSE 8004

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8004"]
