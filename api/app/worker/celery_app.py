"""Celery worker foundation. XML parsing and AI tasks are implemented in later phases."""
from celery import Celery
from app.core.config import settings

celery_app = Celery("migrapilot", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(task_serializer="json", accept_content=["json"], result_serializer="json", timezone="UTC")
