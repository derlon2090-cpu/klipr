"""Periodic creator watchlist checks and duplicate-safe delayed recording."""
from __future__ import annotations

import json
import random
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener
from uuid import UUID

from celery import shared_task

from app.db import SessionLocal
from app.models import ArchiveBranding, Notification, Stream, StreamStatus, WatchlistSubscription
from app.storage import copy_file
from .tasks import active_key, record_stream, redis_client, task_key


def delayed_action(status: str, lock_exists: bool) -> str:
    """Pure decision helper used by the task and its regression tests."""
    if status != "pending_auto_record":
        return "skip"
    return "manual_taken_over" if lock_exists else "start"


@shared_task(name="app.worker.watcher.check_watchlist_streams")
def check_watchlist_streams() -> None:
    from app.main import _ensure_watchlist_schema
    with SessionLocal() as db:
        _ensure_watchlist_schema(db)
        subscriptions = db.query(WatchlistSubscription).filter(WatchlistSubscription.auto_record.is_(True)).all()
        for item in subscriptions:
            # EventSub channels receive push notifications and are never polled.
            if item.platform == "twitch" and item.eventsub_subscription_id:
                continue
            if not redis_client().exists(f"watcher:backoff:{item.id}"):
                check_watchlist_subscription.apply_async(args=[str(item.id)], countdown=random.randint(5, 25))


def _queue_live_notification(db, item: WatchlistSubscription, stream_marker: str | None) -> None:
    marker = str(stream_marker) if stream_marker else None
    if item.is_currently_live and (not marker or marker == item.last_stream_id):
        return
    item.is_currently_live = True
    if marker: item.last_stream_id = marker
    notification = Notification(subscription_id=item.id, title=f"{item.display_name} بدأ البث الآن",
        message=f"سيبدأ التسجيل التلقائي خلال {item.delay_seconds} ثانية ما لم تقم بالإلغاء أو تبدأ التسجيل يدوياً.",
        channel_url=item.channel_url, status="pending_auto_record",
        scheduled_for=datetime.now(timezone.utc) + timedelta(seconds=item.delay_seconds))
    db.add(notification); db.flush()
    trigger_delayed_auto_record.apply_async(args=[str(notification.id), item.channel_url], countdown=item.delay_seconds)


def _kick_metadata(channel_slug: str) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", channel_slug):
        raise ValueError("Invalid Kick channel slug")
    from app.config import get_settings
    settings = get_settings()
    handlers = [ProxyHandler({"https": settings.watcher_proxy_url})] if settings.watcher_proxy_url else []
    opener = build_opener(*handlers)
    request = Request(f"https://kick.com/api/v2/channels/{channel_slug}", headers={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36","Accept":"application/json","Accept-Language":"en-US,en;q=0.9"})
    with opener.open(request, timeout=10) as response:
        data = json.loads(response.read(1_000_000))
    live = data.get("livestream") or {}
    return {"live":bool(live),"stream_id":str(live.get("id")) if live.get("id") else None}


@shared_task(name="app.worker.watcher.check_watchlist_subscription")
def check_watchlist_subscription(subscription_id: str) -> None:
    client = redis_client()
    with SessionLocal() as db:
        item = db.get(WatchlistSubscription, UUID(subscription_id))
        if item is None or not item.auto_record or (item.platform == "twitch" and item.eventsub_subscription_id): return
        try:
            if item.platform == "kick": metadata = _kick_metadata(item.channel_slug)
            else:
                from app.main import preview_stream
                metadata = preview_stream(item.platform, item.channel_url)
            client.delete(f"watcher:failures:{item.id}", f"watcher:backoff:{item.id}")
        except HTTPError as error:
            failures = client.incr(f"watcher:failures:{item.id}"); client.expire(f"watcher:failures:{item.id}", 3600)
            if error.code in {403, 429}: client.set(f"watcher:backoff:{item.id}", "1", ex=min(1800, 120 * (2 ** min(failures - 1, 4))))
            return
        except Exception:
            return
        if not metadata.get("live"):
            item.is_currently_live = False; item.last_stream_id = None; db.commit(); return
        _queue_live_notification(db, item, metadata.get("stream_id")); db.commit()


@shared_task(name="app.worker.watcher.handle_twitch_stream_online")
def handle_twitch_stream_online(event: dict) -> None:
    broadcaster_id = str(event.get("broadcaster_user_id") or "")
    if not broadcaster_id: return
    with SessionLocal() as db:
        item = db.query(WatchlistSubscription).filter(WatchlistSubscription.twitch_user_id == broadcaster_id).first()
        if item is None: return
        if event.get("broadcaster_user_name"): item.display_name = str(event["broadcaster_user_name"])[:120]
        if item.auto_record: _queue_live_notification(db, item, str(event.get("id") or event.get("started_at") or ""))
        else: item.is_currently_live = True
        db.commit()


def _reserve_auto_slot(stream_id: str) -> bool:
    return bool(redis_client().eval(
        """if redis.call('SCARD', KEYS[1]) >= 2 then return 0 end
        redis.call('SADD', KEYS[1], ARGV[1]); redis.call('EXPIRE', KEYS[1], 43200); return 1""",
        1, "klipr:auto-record:active", stream_id,
    ))


@shared_task(name="app.worker.watcher.trigger_delayed_auto_record")
def trigger_delayed_auto_record(notification_id: str, channel_url: str) -> None:
    client, lock = redis_client(), active_key(channel_url)
    with SessionLocal() as db:
        notification = db.get(Notification, UUID(notification_id))
        if notification is None:
            return
        action = delayed_action(notification.status, bool(client.exists(lock)))
        if action == "skip":
            return
        if action == "manual_taken_over":
            notification.status = "manual_taken_over"; db.commit(); return
        if not client.set(lock, "pending-auto", nx=True, ex=43200):
            notification.status = "manual_taken_over"; db.commit(); return
        try:
            branding = db.get(ArchiveBranding, 1)
            if branding is None:
                branding = ArchiveBranding(id=1); db.add(branding); db.flush()
            subscription = db.get(WatchlistSubscription, notification.subscription_id) if notification.subscription_id else None
            platform = subscription.platform if subscription else ("twitch" if "twitch.tv" in channel_url else "kick")
            stream = Stream(channel_id=None, source_url=channel_url, platform=platform, status=StreamStatus.queued,
                layout_mode="center", enable_end_screen=branding.enable_end_screen, remove_music=branding.remove_music,
                archive_channel_name=branding.archive_channel_name, archive_tagline=branding.archive_tagline,
                outro_duration_seconds=branding.outro_duration_seconds, left_vod_id=branding.default_left_vod_id,
                right_vod_id=branding.default_right_vod_id)
            db.add(stream); db.flush()
            if branding.default_thumbnail_key and branding.use_default_thumbnail:
                suffix = Path(branding.default_thumbnail_key).suffix or ".png"; stream.thumbnail_key = f"streams/{stream.id}/custom-thumbnail{suffix}"; copy_file(branding.default_thumbnail_key, stream.thumbnail_key)
            if branding.archive_logo_key:
                suffix = Path(branding.archive_logo_key).suffix or ".png"; stream.archive_logo_key = f"streams/{stream.id}/archive-logo{suffix}"; copy_file(branding.archive_logo_key, stream.archive_logo_key)
            if branding.default_short_thumbnail_key:
                suffix = Path(branding.default_short_thumbnail_key).suffix or ".png"; stream.short_thumbnail_key = f"streams/{stream.id}/short-thumbnail{suffix}"; copy_file(branding.default_short_thumbnail_key, stream.short_thumbnail_key)
            if not _reserve_auto_slot(str(stream.id)):
                db.rollback(); client.delete(lock); notification = db.get(Notification, UUID(notification_id)); notification.status = "cancelled"; notification.message = "تعذر بدء التسجيل: الحد الأقصى للتسجيلات النشطة مستخدم."; db.commit(); return
            notification.status = "auto_started"; db.commit()
            client.set(lock, str(stream.id), xx=True, ex=43200)
            task = record_stream.delay(str(stream.id), channel_url, "klipr:auto-record:active")
            client.sadd(task_key(str(stream.id)), task.id); client.expire(task_key(str(stream.id)), 43200)
        except Exception:
            db.rollback(); client.delete(lock)
            if "stream" in locals(): client.srem("klipr:auto-record:active", str(stream.id))
            notification = db.get(Notification, UUID(notification_id))
            if notification: notification.status = "cancelled"; notification.message = "تعذر بدء التسجيل التلقائي."; db.commit()
            raise
