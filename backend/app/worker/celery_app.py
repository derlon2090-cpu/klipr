from celery import Celery
from app.config import get_settings

settings = get_settings()
celery_app = Celery("klipr", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(task_track_started=True, task_serializer="json", accept_content=["json"], result_serializer="json")
celery_app.conf.imports = ("app.worker.tasks", "app.worker.highlights", "app.worker.watcher")
celery_app.conf.beat_schedule = {
    "check-creator-watchlist-every-minute": {
        "task": "app.worker.watcher.check_watchlist_streams",
        "schedule": 60.0,
    }
}
celery_app.autodiscover_tasks(["app.worker"])
