"""Artifact share link lifecycle model.

[INPUT]
- app.database.models.base::Base (POS: SQLAlchemy Base model)

[OUTPUT]
- ArtifactShareRecord: class — Persisted registry of artifact share links.

[POS]
Server business layer. Records every share-preview link so the GUI can list
active shares and revoke compromised or unwanted links immediately. The token
is never stored in plaintext; only its SHA-256 fingerprint is kept.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, DateTime, Index, String

from app.database.models.base import Base


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class ArtifactShareRecord(Base):
    """Immutable share-link metadata plus a nullable revocation timestamp."""

    __tablename__ = "artifact_share_records"
    __table_args__ = (Index("ix_artifact_share_records_artifact_id", "artifact_id"),)

    id = Column(String(36), primary_key=True)
    token_fingerprint = Column(String(64), unique=True, nullable=False)
    artifact_id = Column(String(36), nullable=False)
    version_id = Column(String(36), nullable=False)
    artifact_type = Column(String(32), nullable=True)
    password_protected = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=_utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)
