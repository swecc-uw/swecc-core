FROM python:3.9 AS development

WORKDIR /app
COPY requirements-server.txt .
RUN pip install --no-cache-dir -r requirements-server.txt
COPY . .

FROM development AS production

WORKDIR /app/server
CMD ["bash", "-c", "python manage.py makemigrations bench --noinput && python manage.py migrate --noinput && exec gunicorn --bind 0.0.0.0:8000 server.wsgi --workers 5"]
