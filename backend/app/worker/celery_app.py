from celery import Celery
from celery.signals import heartbeat_sent, worker_ready, worker_shutdown
from app.config import get_settings

settings = get_settings()
celery_app = Celery("klipr", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(task_track_started=True, task_serializer="json", accept_content=["json"], result_serializer="json")
celery_app.conf.imports = ("app.worker.tasks", "app.worker.highlights", "app.worker.watcher")
celery_app.conf.beat_schedule = {
    "check-creator-watchlist-every-minute": {
        "task": "app.worker.watcher.check_watchlist_streams",
        "schedule": 45.0,
    }
}
celery_app.autodiscover_tasks(["app.worker"])

WORKER_HEARTBEAT_KEY = "klipr:worker:online"


def _publish_worker_heartbeat(**_kwargs) -> None:
    """Expose worker liveness to the API without slow Celery inspect calls."""
    from app.worker.tasks import redis_client
    redis_client().set(WORKER_HEARTBEAT_KEY, "1", ex=30)


@worker_ready.connect
@heartbeat_sent.connect
def publish_worker_heartbeat(**kwargs) -> None:
    _publish_worker_heartbeat(**kwargs)


@worker_shutdown.connect
def clear_worker_heartbeat(**_kwargs) -> None:
    from app.worker.tasks import redis_client
    redis_client().delete(WORKER_HEARTBEAT_KEY)
