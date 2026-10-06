"""ORM models (ARCHITECTURE.md §10). Change only together with a migration."""

from datetime import datetime
from typing import Any, ClassVar

from sqlalchemy import (
    JSON,
    Boolean,
    Enum,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from reelhaven.db.types import UTCDateTime, utcnow

# Stable constraint names so Alembic migrations work on SQLite (batch mode).
NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)
    type_annotation_map: ClassVar[dict[Any, Any]] = {
        datetime: UTCDateTime(),
        dict[str, Any]: JSON(),
    }


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Stored lower-cased; usernames are case-insensitive.
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    totp_secret: Mapped[str | None] = mapped_column(Text, default=None)  # encrypted (phase 0.7)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    password_changed_at: Mapped[datetime] = mapped_column(default=utcnow)


class AuthSession(Base):
    """A login session. Only the SHA-256 of the session ID is stored."""

    __tablename__ = "sessions"

    id_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(index=True)
    ip: Mapped[str | None] = mapped_column(String(45), default=None)
    user_agent: Mapped[str | None] = mapped_column(String(512), default=None)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column()
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_at", "at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[datetime] = mapped_column(default=utcnow)
    actor: Mapped[str] = mapped_column(String(128))  # username, "api-key", "system" or an IP
    action: Mapped[str] = mapped_column(String(64))
    target: Mapped[str | None] = mapped_column(String(512), default=None)
    detail: Mapped[dict[str, Any] | None] = mapped_column(default=None)


LIBRARY_TYPES = ("movies", "tv", "other")


class Library(Base):
    __tablename__ = "libraries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    type: Mapped[str] = mapped_column(
        Enum(*LIBRARY_TYPES, name="library_type", native_enum=False, create_constraint=True)
    )
    # Absolute, symlink-resolved path inside the media root.
    path: Mapped[str] = mapped_column(String(4096), unique=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
    last_scan_at: Mapped[datetime | None] = mapped_column(default=None)
    last_scan_error: Mapped[str | None] = mapped_column(Text, default=None)


LANGUAGE_SOURCES = ("sonarr", "radarr", "tmdb", "manual", "unknown")


class Title(Base):
    """A movie or series folder, with its original production language (ADR-0007)."""

    __tablename__ = "titles"
    __table_args__ = (UniqueConstraint("library_id", "folder"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    library_id: Mapped[int] = mapped_column(
        ForeignKey("libraries.id", ondelete="CASCADE"), index=True
    )
    # Relative to the library root; "" for files directly in the root.
    folder: Mapped[str] = mapped_column(String(4096))
    name: Mapped[str] = mapped_column(String(512))
    year: Mapped[int | None] = mapped_column(Integer, default=None)
    original_language: Mapped[str | None] = mapped_column(String(32), default=None)
    language_source: Mapped[str] = mapped_column(
        Enum(*LANGUAGE_SOURCES, name="language_source", native_enum=False, create_constraint=True),
        default="unknown",
    )
    # Where the answer came from, e.g. "Sonarr: Breaking Bad" or "TMDB movie 603".
    source_detail: Mapped[str | None] = mapped_column(String(512), default=None)
    resolved_at: Mapped[datetime | None] = mapped_column(default=None)


FILE_STATUSES = ("ok", "probe_failed")


class MediaFile(Base):
    __tablename__ = "media_files"
    __table_args__ = (Index("ix_media_files_library_fingerprint", "library_id", "fingerprint"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    library_id: Mapped[int] = mapped_column(
        ForeignKey("libraries.id", ondelete="CASCADE"), index=True
    )
    # Absolute real path; relative_path is shown in the UI.
    path: Mapped[str] = mapped_column(String(4096), unique=True)
    relative_path: Mapped[str] = mapped_column(String(4096))
    # The title (movie or series) folder this file belongs to; see titles.py.
    title_id: Mapped[int | None] = mapped_column(
        ForeignKey("titles.id", ondelete="SET NULL"), index=True, default=None
    )
    size: Mapped[int] = mapped_column(Integer)
    mtime_ns: Mapped[int] = mapped_column(Integer)
    fingerprint: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(
        Enum(*FILE_STATUSES, name="media_file_status", native_enum=False, create_constraint=True)
    )
    probe: Mapped[dict[str, Any] | None] = mapped_column(default=None)
    probe_error: Mapped[str | None] = mapped_column(Text, default=None)
    first_seen_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(default=utcnow)
    probed_at: Mapped[datetime | None] = mapped_column(default=None)


INTEGRATION_KINDS = ("sonarr", "radarr", "tmdb")


class Integration(Base):
    __tablename__ = "integrations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(
        Enum(*INTEGRATION_KINDS, name="integration_kind", native_enum=False, create_constraint=True)
    )
    name: Mapped[str] = mapped_column(String(100), unique=True)
    base_url: Mapped[str] = mapped_column(String(2048))
    api_key_encrypted: Mapped[str] = mapped_column(Text)  # secretbox.SecretBox
    verify_tls: Mapped[bool] = mapped_column(Boolean, default=True)
    # [{"remote": "/tv", "local": "/media/TV"}]: how this service names our paths.
    path_mappings: Mapped[list[dict[str, str]]] = mapped_column(JSON, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
