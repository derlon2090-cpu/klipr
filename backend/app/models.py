import enum
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import BigInteger, Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


class StreamStatus(str, enum.Enum):
    queued = "queued"
    recording = "recording"
    reconnecting = "reconnecting"
    processing = "processing"
    ready = "ready"
    failed = "failed"


class VodStatus(str, enum.Enum):
    fetching_metadata = "fetching_metadata"
    downloading = "downloading"
    remuxing = "remuxing"
    ready = "ready"
    failed = "failed"


class User(Base):
    __tablename__ = "users"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Channel(Base):
    __tablename__ = "channels"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String(32))
    handle: Mapped[str] = mapped_column(String(255))
    stream_url: Mapped[str] = mapped_column(Text)
    auto_record: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class ArchiveBranding(Base):
    __tablename__ = "archive_branding"
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    enable_end_screen: Mapped[bool] = mapped_column(Boolean, default=True)
    remove_music: Mapped[bool] = mapped_column(Boolean, default=False)
    outro_duration_seconds: Mapped[int] = mapped_column(default=15)
    archive_channel_name: Mapped[str | None] = mapped_column(String(120))
    archive_tagline: Mapped[str | None] = mapped_column(String(240))
    archive_logo_key: Mapped[str | None] = mapped_column(Text)
    default_thumbnail_key: Mapped[str | None] = mapped_column(Text)
    default_short_thumbnail_key: Mapped[str | None] = mapped_column(Text)
    use_default_thumbnail: Mapped[bool] = mapped_column(Boolean, default=True)
    default_left_vod_id: Mapped[UUID | None] = mapped_column(nullable=True)
    default_right_vod_id: Mapped[UUID | None] = mapped_column(nullable=True)
    auto_trim_ads: Mapped[bool] = mapped_column(Boolean, default=False)
    overlay_logo_key: Mapped[str | None] = mapped_column(Text)
    overlay_creator_name: Mapped[str | None] = mapped_column(String(120))
    overlay_position: Mapped[str] = mapped_column(String(24), default="top-right")
    auto_merge_branding: Mapped[bool] = mapped_column(Boolean, default=True)
    default_intro_key: Mapped[str | None] = mapped_column(Text)
    default_outro_key: Mapped[str | None] = mapped_column(Text)
    ai_music_removal: Mapped[bool] = mapped_column(Boolean, default=False)
    channel_banner_key: Mapped[str | None] = mapped_column(Text)


class SessionCredential(Base):
    """One encrypted, global capture session per supported platform."""
    __tablename__ = "session_credentials"
    platform: Mapped[str] = mapped_column(String(16), primary_key=True)
    session_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="unset", nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SavedThumbnail(Base):
    __tablename__ = "saved_thumbnails"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    kind: Mapped[str] = mapped_column(String(16), index=True)
    storage_key: Mapped[str] = mapped_column(Text, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WatchlistSubscription(Base):
    __tablename__ = "watchlist_subscriptions"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    platform: Mapped[str] = mapped_column(String(16), index=True)
    channel_slug: Mapped[str] = mapped_column(String(100))
    channel_url: Mapped[str] = mapped_column(Text, unique=True)
    display_name: Mapped[str] = mapped_column(String(120))
    avatar_url: Mapped[str | None] = mapped_column(Text)
    auto_record: Mapped[bool] = mapped_column(Boolean, default=True)
    delay_seconds: Mapped[int] = mapped_column(default=30)
    is_currently_live: Mapped[bool] = mapped_column(Boolean, default=False)
    last_stream_id: Mapped[str | None] = mapped_column(String(255))
    twitch_user_id: Mapped[str | None] = mapped_column(String(64))
    eventsub_subscription_id: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    subscription_id: Mapped[UUID | None] = mapped_column(ForeignKey("watchlist_subscriptions.id", ondelete="SET NULL"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)
    channel_url: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), index=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CreatorSuggestion(Base):
    __tablename__ = "creator_suggestions"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    creator_name: Mapped[str] = mapped_column(String(120), index=True)
    platform: Mapped[str] = mapped_column(String(16), index=True)
    channel_url: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="new", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Stream(Base):
    __tablename__ = "streams"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    channel_id: Mapped[UUID | None] = mapped_column(ForeignKey("channels.id", ondelete="SET NULL"), index=True, nullable=True)
    source_url: Mapped[str] = mapped_column(Text)
    platform: Mapped[str] = mapped_column(String(32), default="direct")
    status: Mapped[StreamStatus] = mapped_column(Enum(StreamStatus), default=StreamStatus.queued, index=True)
    master_key: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    stop_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    layout_mode: Mapped[str] = mapped_column(String(16), default="center")
    discord_webhook_url: Mapped[str | None] = mapped_column(Text)
    thumbnail_key: Mapped[str | None] = mapped_column(Text)
    short_thumbnail_key: Mapped[str | None] = mapped_column(Text)
    custom_headline: Mapped[str | None] = mapped_column(String(160))
    target_clip_duration: Mapped[int] = mapped_column(default=45)
    embed_intro_cover: Mapped[bool] = mapped_column(Boolean, default=True)
    enable_end_screen: Mapped[bool] = mapped_column(Boolean, default=True)
    remove_music: Mapped[bool] = mapped_column(Boolean, default=False)
    archive_logo_key: Mapped[str | None] = mapped_column(Text)
    archive_tagline: Mapped[str | None] = mapped_column(String(240))
    archive_channel_name: Mapped[str | None] = mapped_column(String(120))
    outro_duration_seconds: Mapped[int] = mapped_column(default=15)
    left_vod_id: Mapped[UUID | None] = mapped_column(nullable=True)
    right_vod_id: Mapped[UUID | None] = mapped_column(nullable=True)
    overlay_logo_key: Mapped[str | None] = mapped_column(Text)
    overlay_creator_name: Mapped[str | None] = mapped_column(String(120))
    overlay_position: Mapped[str] = mapped_column(String(24), default="top-right")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Vod(Base):
    """An imported, finite Kick or Twitch broadcast kept in object storage."""
    __tablename__ = "vods"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    source_url: Mapped[str] = mapped_column(Text, unique=True)
    platform: Mapped[str] = mapped_column(String(16), index=True)
    quality: Mapped[str] = mapped_column(String(32), default="best")
    status: Mapped[VodStatus] = mapped_column(Enum(VodStatus), default=VodStatus.fetching_metadata, index=True)
    title: Mapped[str | None] = mapped_column(String(500))
    streamer_name: Mapped[str | None] = mapped_column(String(160))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    thumbnail_url: Mapped[str | None] = mapped_column(Text)
    local_path: Mapped[str | None] = mapped_column(Text)
    thumbnail_path: Mapped[str | None] = mapped_column(Text)
    storage_key: Mapped[str | None] = mapped_column(Text)
    thumbnail_key: Mapped[str | None] = mapped_column(Text)
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    fps: Mapped[float | None] = mapped_column(Float)
    bitrate: Mapped[int | None] = mapped_column(BigInteger)
    progress: Mapped[float] = mapped_column(Float, default=0)
    download_speed: Mapped[str | None] = mapped_column(String(64))
    eta_seconds: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class StudioRender(Base):
    """A durable Production Studio render backed by the shared media volume."""
    __tablename__ = "studio_renders"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    vod_id: Mapped[UUID] = mapped_column(ForeignKey("vods.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    progress: Mapped[float] = mapped_column(Float, default=0)
    export_quality: Mapped[str] = mapped_column(String(24), default="original")
    start_seconds: Mapped[float | None] = mapped_column(Float)
    end_seconds: Mapped[float | None] = mapped_column(Float)
    thumbnail_path: Mapped[str | None] = mapped_column(Text)
    intro_path: Mapped[str | None] = mapped_column(Text)
    outro_path: Mapped[str | None] = mapped_column(Text)
    output_path: Mapped[str | None] = mapped_column(Text)
    storage_key: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SmartThumbnail(Base):
    """One AI-selected frame and caption for a VOD."""
    __tablename__ = "smart_thumbnails"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    vod_id: Mapped[UUID] = mapped_column(ForeignKey("vods.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    progress: Mapped[float] = mapped_column(Float, default=0)
    platform: Mapped[str] = mapped_column(String(24), default="youtube")
    frame_style: Mapped[str] = mapped_column(String(24), default="bold")
    timestamp_seconds: Mapped[float | None] = mapped_column(Float)
    headline: Mapped[str | None] = mapped_column(String(160))
    context: Mapped[str | None] = mapped_column(Text)
    output_path: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Clip(Base):
    __tablename__ = "clips"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    stream_id: Mapped[UUID] = mapped_column(ForeignKey("streams.id", ondelete="CASCADE"), index=True)
    start_seconds: Mapped[float] = mapped_column(Float)
    end_seconds: Mapped[float] = mapped_column(Float)
    score: Mapped[float] = mapped_column(Float)
    vertical_key: Mapped[str | None] = mapped_column(Text)
    captions_key: Mapped[str | None] = mapped_column(Text)
    transcript: Mapped[str | None] = mapped_column(Text)
    thumbnail_key: Mapped[str | None] = mapped_column(Text)
    viral_score: Mapped[int] = mapped_column(Integer, default=0)
    hook_title: Mapped[str | None] = mapped_column(String(160))
    highlight_reason: Mapped[str | None] = mapped_column(String(120))
    transcript_snippet: Mapped[str | None] = mapped_column(Text)
