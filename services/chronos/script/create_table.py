import logging

from app.services.dynamodb_service import db

try:
    db.create_health_metric_table()
except Exception as e:
    logging.error(f"Failed to create table: {e}")

try:
    db.create_docker_events_table()
except Exception as e:
    logging.error(f"Failed to create table: {e}")
