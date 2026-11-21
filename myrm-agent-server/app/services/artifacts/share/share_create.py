"""Create a registered, ready-to-open artifact share link: one path for the share dialog and the IM share buttons.

[INPUT]
- app.core.security.share.share_links::ShareKind, share_link_path (POS: where each share token kind is served)
- app.services.artifacts.share.share_token (POS: HMAC token signing + claims)
- app.services.artifacts.share.share_bundle::materialize_share_bundle (POS: pinned-version bundle snapshot)
- app.services.artifacts.share.share_registry::register_share (POS: share-link lifecycle registry)
- app.services.audit.share_events::ShareSource, report_share_created (POS: share events in the server log)

[OUTPUT]
- CreatedArtifactShare: token and expiry of a registered link
- ShareRegistrationError: the registry row could not be saved
- create_artifact_share: sign, snapshot the bundle, register, log the creation with its source

[POS]
Server business layer. Every artifact link that leaves the machine is created here, so it is listed in the share manager
and can be revoked: the public gate refuses a token the registry does not know. Registration is committed before the
token is returned.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.share.share_links import ShareKind, share_link_path
from app.services.audit.share_events import ShareSource, report_share_created

from .share_bundle import materialize_share_bundle
from .share_registry import register_share
from .share_token import DEFAULT_TTL_SECONDS, ArtifactShareClaims, create_artifact_share_token

logger = logging.getLogger(__name__)


class ShareRegistrationError(RuntimeError):
    """The link was signed and its bundle written, but the registry row could not be saved."""


@dataclass(frozen=True)
class CreatedArtifactShare:
    token: str
    expires_at: int


async def create_artifact_share(
    db: AsyncSession,
    workspace_root: str,
    *,
    artifact_id: str,
    version_id: str,
    artifact_type: str | None,
    source: ShareSource,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    password: str | None = None,
) -> CreatedArtifactShare:
    """Sign a share token for one artifact version, snapshot its bundle and register it.

    Raises ``ValueError``, ``LookupError`` or ``FileNotFoundError`` when the version has nothing to share (from the
    bundle snapshot) and ``ShareRegistrationError`` when the registry write fails.
    """
    token, expires_at = create_artifact_share_token(
        artifact_id,
        version_id,
        ttl_seconds=ttl_seconds,
        artifact_type=artifact_type,
        password=password,
    )
    claims = ArtifactShareClaims(artifact_id=artifact_id, version_id=version_id, exp=expires_at, artifact_type=artifact_type)
    await materialize_share_bundle(db, workspace_root, claims)
    try:
        await register_share(
            db,
            token=token,
            artifact_id=artifact_id,
            version_id=version_id,
            artifact_type=artifact_type,
            password_protected=password is not None,
            expires_at_unix=expires_at,
            share_path=share_link_path(ShareKind.ARTIFACT, token) if password is not None else None,
        )
    except Exception as exc:
        logger.error("Failed to register share link: %s", exc)
        raise ShareRegistrationError("Failed to register share link") from exc
    report_share_created(ShareKind.ARTIFACT, source, token)
    return CreatedArtifactShare(token=token, expires_at=expires_at)
