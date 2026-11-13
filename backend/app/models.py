import enum
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, String, Text, func
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
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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
