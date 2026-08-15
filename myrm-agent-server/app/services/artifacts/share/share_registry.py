"""Persistent registry for artifact share-link lifecycle.

[INPUT]
- app.database.models::ArtifactShareRecord (POS: share-link registry row)
- app.database.models::Artifact (POS: artifact metadata for display)
- app.core.security.share.share_hmac::token_fingerprint (POS: shared share-lookup key)
- app.services.artifacts.share.share_bundle (POS: bundle materialization + TTL purge)
- app.services.artifacts.share.share_token::ArtifactShareClaims (POS: HMAC claims)

[OUTPUT]
- register_share / list_active_shares / revoke_share / purge_expired_shares
- is_token_revoked: public-access gate check

[POS]
Server business layer. Gives share links a manual lifecycle on top of the
stateless HMAC token: register on create, list active links, revoke on demand.
Revocation commits ``revoked_at`` (logged for audit) then deletes the on-disk
bundle, so the public gate refuses both existing files and any re-materialization
attempt. ``list_active_shares`` also exposes ``version_id`` so the API layer can
rebuild unprotected share paths; password-protected rows persist their
``share_path`` at register time (the token cannot be rebuilt because the
password is never stored).
"""

from __future__ import annotations

import logging
import shutil
import uuid
from calendar import timegm
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.share.share_hmac import token_fingerprint
from app.database.models import Artifact, ArtifactShareRecord
from .share_bundle import bundle_dir_for_claims
from .share_token import ArtifactShareClaims

logger = logging.getLogger(__name__)

MAX_RECORD_AGE_SECONDS = 60 * 24 * 3600  # 60-day audit window before hard delete


def _utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _from_unix(value: int) -> datetime:
    """Naive UTC datetime for SQLite storage (matches project convention)."""
    return datetime.fromtimestamp(value, tz=UTC).replace(tzinfo=None)


def _to_unix(value: datetime) -> int:
    """Explicit UTC epoch conversion for naive datetimes."""
    return timegm(value.timetuple())


async def _find_by_fingerprint(
    db: AsyncSession, fingerprint: str
) -> ArtifactShareRecord | None:
    """Look up a registry row by its token fingerprint."""
    return (
        (
            await db.execute(
                select(ArtifactShareRecord).where(
                    ArtifactShareRecord.token_fingerprint == fingerprint
                )
            )
        )
        .scalars()
        .first()
    )


@dataclass(frozen=True)
class ActiveShareRow:
    """Active share-link row for the management GUI."""

    id: str
    artifact_id: str
    version_id: str
    artifact_name: str
    artifact_type: str | None
    password_protected: bool
    created_at: datetime
    expires_at: datetime
    share_path: str | None = None


def _claims_from_record(record: ArtifactShareRecord) -> ArtifactShareClaims:
    """Rebuild claims from a persisted record (needed to delete its bundle)."""
    return ArtifactShareClaims(
        artifact_id=record.artifact_id,
        version_id=record.version_id,
        exp=_to_unix(record.expires_at),
        artifact_type=record.artifact_type,
    )


async def register_share(
    db: AsyncSession,
    *,
    token: str,
    artifact_id: str,
    version_id: str,
    artifact_type: str | None,
    password_protected: bool,
    expires_at_unix: int,
    share_path: str | None = None,
) -> ArtifactShareRecord:
    """Persist a share-link registry row. Idempotent on token fingerprint.

    Tokens are deterministic (same artifact + TTL in the same second produce an
    identical token), so a concurrent duplicate insert is resolved by returning
    the existing row instead of surfacing a unique-constraint error.

    ``share_path`` is stored only for password-protected shares whose token
    cannot be rebuilt (the password is never persisted); unprotected rows leave
    it NULL and rebuild the path on demand.
    """
    fingerprint = token_fingerprint(token)

    existing = await _find_by_fingerprint(db, fingerprint)
    if existing is not None:
        return existing

    record = ArtifactShareRecord(
        id=str(uuid.uuid4()),
        token_fingerprint=fingerprint,
        artifact_id=artifact_id,
        version_id=version_id,
        artifact_type=artifact_type,
        password_protected=password_protected,
        expires_at=_from_unix(expires_at_unix),
        share_path=share_path,
    )
    db.add(record)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await _find_by_fingerprint(db, fingerprint)
        if existing is not None:
            return existing
        raise
    await db.refresh(record)
    return record


async def list_active_shares(db: AsyncSession) -> list[ActiveShareRow]:
    """Return unrevoked, unexpired share links joined with artifact names."""
    now = _utcnow_naive()
    rows = (
        await db.execute(
            select(ArtifactShareRecord, Artifact.name)
            .join(Artifact, Artifact.id == ArtifactShareRecord.artifact_id)
            .where(
                ArtifactShareRecord.revoked_at.is_(None),
                ArtifactShareRecord.expires_at > now,
            )
            .order_by(ArtifactShareRecord.created_at.desc())
        )
    ).all()
    return [
        ActiveShareRow(
            id=record.id,
            artifact_id=record.artifact_id,
            version_id=record.version_id,
            artifact_name=name,
            artifact_type=record.artifact_type,
            password_protected=record.password_protected,
            created_at=record.created_at,
            expires_at=record.expires_at,
            share_path=record.share_path,
        )
        for record, name in rows
    ]


async def revoke_share(db: AsyncSession, record_id: str) -> bool:
    """Revoke a share by record id. Idempotent: returns False when unknown.

    Commits ``revoked_at`` first (with an INFO audit log), then deletes the
    on-disk bundle, so the public URL can neither serve existing files nor
    re-materialize content even if the filesystem cleanup fails.
    """
    record = (
        (
            await db.execute(
                select(ArtifactShareRecord).where(ArtifactShareRecord.id == record_id)
            )
        )
        .scalars()
        .first()
    )
    if record is None:
        return False

    if record.revoked_at is None:
        claims = _claims_from_record(record)
        record.revoked_at = _utcnow_naive()
        await db.commit()
        logger.info(
            "Revoked artifact share link: record=%s artifact=%s version=%s",
            record.id,
            record.artifact_id,
            record.version_id,
        )
        shutil.rmtree(bundle_dir_for_claims(claims), ignore_errors=True)
    return True


async def is_token_revoked(db: AsyncSession, token: str) -> bool:
    """Gate check: ``True`` when a registered token has been manually revoked.

    Unknown tokens (created before the registry shipped, or never persisted)
    return ``False`` so legacy share links keep working.
    """
    record = await _find_by_fingerprint(db, token_fingerprint(token))
    return record is not None and record.revoked_at is not None


async def purge_expired_shares(db: AsyncSession) -> int:
    """Delete registry rows past their TTL plus a retention grace period.

    Runs alongside ``purge_expired_share_bundles``: bundles are removed once
    their TTL lapses, while registry rows are kept for the audit window
    (expires_at + 60 days) and then deleted here. Returns the number removed.
    """
    cutoff = _utcnow_naive() - timedelta(seconds=MAX_RECORD_AGE_SECONDS)
    stale = (
        (
            await db.execute(
                select(ArtifactShareRecord).where(
                    ArtifactShareRecord.expires_at < cutoff
                )
            )
        )
        .scalars()
        .all()
    )
    if not stale:
        return 0
    for record in stale:
        await db.delete(record)
    await db.commit()
    return len(stale)
