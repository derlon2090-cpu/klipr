from celery import Celery
from app.config import get_settings

settings = get_settings()
celery_app = Celery("klipr", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(task_track_started=True, task_serializer="json", accept_content=["json"], result_serializer="json")
celery_app.autodiscover_tasks(["app.worker"])
