"""Workspace files a cron run mentions, attached to its IM delivery message.

[INPUT]
- app.core.channel_bridge.agent_executor.deliverable::append_deliverable_notes, collect_deliverable_paths_from_text, resolve_chat_workspace_root (POS: workspace path scan to IM attachments)
- app.core.channel_bridge.locale_provider::resolve_user_locale (POS: language of the notes the user reads)
- app.remote_access.mobile_deep_link::resolve_web_handoff_components (POS: "continue in the WebUI" button)
- app.channels.core.outbound_media::discard_ephemeral_media (POS: temp attachment cleanup)

[OUTPUT]
- CronDeliverables: result text with the media and web-handoff buttons it travels with
- collect_cron_deliverables: scan a cron result for workspace files to attach

[POS]
Cron counterpart of the channel reply's deliverable assembly (``execute_finalize``). A job bound to a chat works in that
chat's workspace, so the paths its result mentions resolve there. The web-handoff button keeps the files reachable when
the delivery route can only carry text (cloud-hosted control-plane egress downgrades it to a link).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from myrm_agent_harness.toolkits.cron.types import CronJob

from app.channels.core.outbound_media import discard_ephemeral_media
from app.channels.i18n import channel_t
from app.channels.types import ComponentRow, MediaAttachment

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CronDeliverables:
    """A cron result as the delivery message carries it.

    ``locale`` is set once something was attached: it is the language of the notes the message bus
    adds when the route cannot carry the attachments.
    """

    content: str
    media: tuple[MediaAttachment, ...] = ()
    components: tuple[ComponentRow, ...] = ()
    locale: str | None = None


async def collect_cron_deliverables(job: CronJob, output: str) -> CronDeliverables:
    """Attach the workspace files ``output`` mentions; the text is returned untouched when there are none.

    Attached ``ephemeral`` files belong to the caller until the delivery message is handed to the bus.
    """
    from app.core.channel_bridge.agent_executor.deliverable import (
        append_deliverable_notes,
        collect_deliverable_paths_from_text,
        resolve_chat_workspace_root,
    )
    from app.core.channel_bridge.locale_provider import resolve_user_locale

    if not job.chat_id or not output.strip():
        return CronDeliverables(output)
    workspace_root = await resolve_chat_workspace_root(job.chat_id)
    if not workspace_root:
        return CronDeliverables(output)

    text, media, oversized_notes, compressed_notes = await asyncio.to_thread(
        collect_deliverable_paths_from_text, output, workspace_root=workspace_root
    )
    if not (media or oversized_notes or compressed_notes):
        return CronDeliverables(output)

    try:
        locale = await resolve_user_locale()
        text = append_deliverable_notes(text, locale=locale, oversized_notes=oversized_notes, compressed_notes=compressed_notes)
        if media and not text.strip():
            text = str(channel_t(locale, "deliverable_attached_only"))
        components = await _web_handoff(job.chat_id, locale) if media else ()
    except BaseException:
        discard_ephemeral_media(media)
        raise
    return CronDeliverables(text, tuple(media), components, locale)


async def _web_handoff(chat_id: str, locale: str) -> tuple[ComponentRow, ...]:
    """The "continue in the WebUI" button row; empty when no public URL is configured or the lookup fails."""
    from app.remote_access.mobile_deep_link import resolve_web_handoff_components

    try:
        return await resolve_web_handoff_components(chat_id, locale=locale)
    except Exception:
        logger.debug("Cron deliverables: web handoff unavailable for chat %s", chat_id, exc_info=True)
        return ()
