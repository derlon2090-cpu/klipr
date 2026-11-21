from celery import Celery
from celery.signals import heartbeat_sent, worker_ready, worker_shutdown
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.config import get_settings

settings = get_settings()


def celery_redis_url(url: str) -> str:
    """Require certificate verification for managed TLS Redis connections."""
    if not url.startswith("rediss://"):
        return url
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.setdefault("ssl_cert_reqs", "required")
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


broker_url = celery_redis_url(settings.redis_url)
celery_app = Celery("klipr", broker=broker_url, backend=broker_url)
celery_app.conf.update(
    task_track_started=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    # VOD downloads can run for many minutes. Keep them recoverable when a
    # worker is rebuilt or restarted; yt-dlp resumes from its .ytdl state.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
)
celery_app.conf.imports = ("app.worker.tasks", "app.worker.highlights", "app.worker.vods", "app.worker.watcher", "app.worker.studio", "app.worker.smart_thumbnails")
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
