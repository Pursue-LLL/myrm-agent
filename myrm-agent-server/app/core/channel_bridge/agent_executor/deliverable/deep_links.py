"""Channel stream artifact deep links for IM outbound delivery.

[INPUT]
- app.core.channel_bridge.executor_helpers::StreamAccumulator, ShareableArtifact (POS: Stream accumulation for channel turns.)
- app.channels.types::MediaAttachment (POS: Channel message types.)
- deliverable.media::MAX_CHANNEL_ATTACHMENT_BYTES, compress_oversized_image, format_human_size, is_compressible_image (POS: Channel deliverable attachment cap + oversized-image fallback)
- app.services.artifacts.share.share_create (POS: sign + snapshot + register one share link, shared with the share dialog.)
- app.database.connection::get_session (POS: DB session for the share registry.)
- app.core.infra.ingress::resolve_public_link_base (POS: Public base of links opened elsewhere: running tunnel, else ingress.)
- app.core.security.share.share_links (POS: where each share token kind is served.)

[OUTPUT]
- collect_channel_artifacts: extract file artifacts from harness stream events (logs WARNING when file_path missing on disk)
- build_artifact_deep_links: ActionButton rows (one button per row, at most MAX_SHARE_BUTTONS) with registered, signed public share URLs (logs WARNING when ingress base URL missing, artifact versions unavailable or a link cannot be created)
- fetch_artifact_versions: batch DB lookup for latest artifact version IDs

[POS]
Artifact delivery helpers for ChannelAgentExecutor. Converts harness artifact
events into IM media attachments and optional share-link buttons for HTML/PDF/docs.
Oversized artifacts degrade to a user-facing note, with a share button next to it. A button never replaces
the attachment or the note: whether its link opens depends on how the instance is reached from outside.
"""

from __future__ import annotations

import logging
import mimetypes
import os
from pathlib import Path
from typing import TYPE_CHECKING

from app.channels.types import MediaAttachment, MediaType, guess_media_type
from app.core.channel_bridge.executor_helpers import (
    ShareableArtifact,
    StreamAccumulator,
)

from .media import (
    MAX_CHANNEL_ATTACHMENT_BYTES,
    compress_oversized_image,
    format_human_size,
    is_compressible_image,
)

if TYPE_CHECKING:
    from app.channels.types.components import ComponentRow

logger = logging.getLogger(__name__)

# Bounds the link rows one reply carries: past this many artifacts a reply gets no further share links
# (every file still arrives as an attachment).
MAX_SHARE_BUTTONS = 5


def collect_channel_artifacts(event: dict[str, object], acc: StreamAccumulator) -> None:
    """Extract deliverable file artifacts from an 'artifacts' event into the accumulator."""
    from app.services.artifacts.share.share_token import is_shareable_artifact

    artifacts_data = event.get("data")
    if not isinstance(artifacts_data, list):
        return
    for item in artifacts_data:
        if not isinstance(item, dict):
            continue
        file_path = item.get("file_path")
        filename = item.get("filename", "")
        content_type = item.get("content_type", "")
        artifact_id = item.get("id")
        artifact_type = item.get("type")
        if not file_path or not isinstance(file_path, str):
            continue
        if not os.path.isfile(file_path):
            logger.warning(
                "Skipping artifact with missing file_path for deliverable: %s (path=%s)",
                filename,
                file_path,
            )
            continue
        try:
            file_size = os.path.getsize(file_path)
        except OSError:
            continue
        if file_size == 0:
            continue
        fname = str(filename)
        mime = str(content_type) if content_type else (mimetypes.guess_type(fname)[0] or "application/octet-stream")

        if file_size > MAX_CHANNEL_ATTACHMENT_BYTES:
            # Oversized: compress raster images into attachments; shareable
            # artifacts get a share button next to the note; otherwise note only.
            if is_compressible_image(fname):
                compressed = compress_oversized_image(
                    file_path,
                    max_bytes=MAX_CHANNEL_ATTACHMENT_BYTES,
                )
                if compressed is not None:
                    out_mime = mimetypes.guess_type(str(compressed))[0] or "application/octet-stream"
                    acc.file_attachments.append(
                        MediaAttachment(
                            media_type=MediaType.IMAGE,
                            path=str(compressed),
                            filename=Path(fname).stem + Path(str(compressed)).suffix,
                            mime_type=out_mime,
                            ephemeral=True,
                        )
                    )
                    acc.compressed_deliverables.append((fname, format_human_size(file_size)))
                    continue
            atype = str(artifact_type) if artifact_type else None
            if isinstance(artifact_id, str) and artifact_id and is_shareable_artifact(fname, atype):
                acc.shareable_artifacts.append(
                    ShareableArtifact(artifact_id, fname, atype or ""),
                )
            acc.oversized_deliverables.append((fname, format_human_size(file_size)))
            continue

        acc.file_attachments.append(
            MediaAttachment(
                media_type=guess_media_type(fname, mime),
                path=file_path,
                filename=fname,
                mime_type=mime,
            )
        )
        if isinstance(artifact_id, str) and artifact_id:
            atype = str(artifact_type) if artifact_type else None
            if is_shareable_artifact(fname, atype):
                acc.shareable_artifacts.append(
                    ShareableArtifact(artifact_id, fname, atype or ""),
                )


async def build_artifact_deep_links(
    acc: StreamAccumulator,
    locale: str,
    workspace_root: str | None,
) -> tuple[ComponentRow, ...]:
    """Create registered share links for shareable artifacts and return them as buttons, one row each; empty when none can be made.

    Links are created like the share dialog creates them (signed, bundle snapshot, registered), so each one is listed
    in the share manager and can be revoked. ``workspace_root`` is the chat's workspace; artifacts that belong to a chat
    are read from that chat's own workspace regardless. Each button is a row of its own (the outbound pipeline walks a
    message's rows, and the buttons of one row share its width), and only the first ``MAX_SHARE_BUTTONS`` artifacts get one.
    """
    if not acc.shareable_artifacts:
        return ()
    shareable = acc.shareable_artifacts[:MAX_SHARE_BUTTONS]
    if len(shareable) < len(acc.shareable_artifacts):
        logger.info(
            "Share buttons limited to %d of %d artifact(s); the others are delivered as attachments only",
            len(shareable),
            len(acc.shareable_artifacts),
        )

    from app.channels.i18n import channel_t
    from app.channels.types.components import ActionButton, ButtonStyle
    from app.core.infra.ingress import resolve_public_link_base
    from app.core.security.share.share_links import ShareKind, share_link_url
    from app.database.connection import get_session
    from app.platform_utils.workspace_root import get_workspace_root
    from app.services.artifacts.share.share_create import create_artifact_share
    from app.services.audit.share_events import ShareSource

    base_url = await resolve_public_link_base()
    if not base_url:
        logger.warning(
            "Skipping artifact deep links: no public ingress base URL configured",
        )
        return ()

    artifact_ids = [aid for aid, _, _ in shareable]
    version_map = await fetch_artifact_versions(artifact_ids)
    if not version_map:
        logger.warning(
            "Skipping artifact deep links: no artifact versions found for %d artifact(s)",
            len(artifact_ids),
        )
        return ()

    root = workspace_root or str(get_workspace_root())
    buttons: list[ActionButton] = []
    multi = len(shareable) > 1

    try:
        async with get_session() as db:
            for artifact_id, filename, artifact_type in shareable:
                version_id = version_map.get(artifact_id)
                if not version_id:
                    logger.warning(
                        "Skipping deep link for artifact %s (%s): no version_id in DB",
                        artifact_id,
                        filename,
                    )
                    continue
                try:
                    created = await create_artifact_share(
                        db,
                        root,
                        artifact_id=artifact_id,
                        version_id=version_id,
                        artifact_type=artifact_type or None,
                        source=ShareSource.IM,
                    )
                except Exception:
                    logger.warning("Failed to create share link for artifact %s", artifact_id, exc_info=True)
                    continue

                if multi:
                    label = channel_t(locale, "artifact_deep_link_named", filename=filename)
                else:
                    label = channel_t(locale, "artifact_deep_link")
                buttons.append(
                    ActionButton(
                        label=str(label),
                        action_id=f"artifact:share:{artifact_id}",
                        style=ButtonStyle.PRIMARY,
                        url=share_link_url(ShareKind.ARTIFACT, created.token, base_url),
                    )
                )
    except Exception:
        logger.warning("Failed to create artifact share links", exc_info=True)

    return tuple((button,) for button in buttons)


async def fetch_artifact_versions(artifact_ids: list[str]) -> dict[str, str]:
    """Batch-fetch latest version_id for each artifact_id from DB."""
    if not artifact_ids:
        return {}
    try:
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        from app.database.connection import get_session
        from app.database.models.artifact import Artifact

        async with get_session() as db:
            stmt = (
                select(Artifact)
                .where(Artifact.id.in_(artifact_ids), Artifact.is_deleted.is_(False))
                .options(selectinload(Artifact.versions))
            )
            result = await db.execute(stmt)
            artifacts = result.scalars().all()
            version_map: dict[str, str] = {}
            for artifact in artifacts:
                if artifact.versions:
                    latest = max(artifact.versions, key=lambda v: v.created_at)
                    version_map[artifact.id] = latest.id
            return version_map
    except Exception:
        logger.warning("Failed to fetch artifact versions for deep links", exc_info=True)
        return {}
