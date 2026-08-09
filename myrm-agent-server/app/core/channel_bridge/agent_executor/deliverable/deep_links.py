"""Channel stream artifact deep links for IM outbound delivery.

[INPUT]
- app.core.channel_bridge.executor_helpers::StreamAccumulator, ShareableArtifact (POS: Stream accumulation for channel turns.)
- app.channels.types::MediaAttachment (POS: Channel message types.)
- app.services.artifacts.share_token (POS: HMAC share token for artifact deep links.)
- app.core.infra.ingress::get_public_ingress_base_url (POS: Public ingress URL for share links.)
- app.remote_access.mobile_deep_link::resolve_mobile_remote_base_url (POS: Public URL resolution for deep links.)

[OUTPUT]
- collect_channel_artifacts: extract file artifacts from harness stream events
- build_artifact_deep_links: ActionButton rows with signed public share URLs
- fetch_artifact_versions: batch DB lookup for latest artifact version IDs

[POS]
Artifact delivery helpers for ChannelAgentExecutor. Converts harness artifact
events into IM media attachments and optional share-link buttons for HTML/PDF/docs.
"""

from __future__ import annotations

import logging
import mimetypes
import os
from typing import TYPE_CHECKING

from app.channels.types import MediaAttachment, guess_media_type
from app.core.channel_bridge.executor_helpers import ShareableArtifact, StreamAccumulator

if TYPE_CHECKING:
    from app.channels.types.components import ComponentRow

logger = logging.getLogger(__name__)

_MAX_CHANNEL_ARTIFACT_BYTES = 5 * 1024 * 1024  # 5MB, matches BaseArtifactProcessor limit


def collect_channel_artifacts(event: dict[str, object], acc: StreamAccumulator) -> None:
    """Extract deliverable file artifacts from an 'artifacts' event into the accumulator."""
    from app.services.artifacts.share_token import is_shareable_artifact

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
            continue
        try:
            file_size = os.path.getsize(file_path)
        except OSError:
            continue
        if file_size > _MAX_CHANNEL_ARTIFACT_BYTES or file_size == 0:
            continue
        fname = str(filename)
        mime = str(content_type) if content_type else (mimetypes.guess_type(fname)[0] or "application/octet-stream")
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
    media_list: list[MediaAttachment],
    locale: str,
) -> tuple[ComponentRow, ...]:
    """Generate public share link buttons for shareable artifacts."""
    if not acc.shareable_artifacts:
        return ()

    from app.channels.i18n import channel_t
    from app.channels.types.components import ActionButton, ButtonStyle
    from app.core.infra.ingress import get_public_ingress_base_url
    from app.remote_access.mobile_deep_link import resolve_mobile_remote_base_url
    from app.services.artifacts.share_token import create_artifact_share_token

    try:
        ingress = await get_public_ingress_base_url()
    except Exception:
        ingress = ""
    base_url = resolve_mobile_remote_base_url(public_ingress_base_url=ingress)
    if not base_url:
        return ()

    version_map = await fetch_artifact_versions(
        [aid for aid, _, _ in acc.shareable_artifacts],
    )
    if not version_map:
        return ()

    buttons: list[ActionButton] = []
    linked_filenames: set[str] = set()
    multi = len(acc.shareable_artifacts) > 1

    for artifact_id, filename, artifact_type in acc.shareable_artifacts:
        version_id = version_map.get(artifact_id)
        if not version_id:
            continue
        try:
            token, _ = create_artifact_share_token(
                artifact_id, version_id, artifact_type=artifact_type or None,
            )
        except Exception:
            logger.warning("Failed to create share token for artifact %s", artifact_id)
            continue

        share_url = f"{base_url}/public/artifact-share/{token}"
        if multi:
            label = channel_t(locale, "artifact_deep_link_named", filename=filename)
        else:
            label = channel_t(locale, "artifact_deep_link")
        buttons.append(ActionButton(
            label=str(label),
            action_id=f"artifact:share:{artifact_id}",
            style=ButtonStyle.PRIMARY,
            url=share_url,
        ))
        linked_filenames.add(filename)

    if linked_filenames:
        media_list[:] = [
            m for m in media_list
            if m.filename not in linked_filenames
        ]

    if not buttons:
        return ()
    return (tuple(buttons),)


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
