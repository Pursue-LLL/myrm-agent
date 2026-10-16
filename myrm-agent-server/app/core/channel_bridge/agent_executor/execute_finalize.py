"""Post-stream reply assembly for channel agent execution.

[INPUT]
- app.channels.types::InboundMessage, MediaAttachment, OutboundMessage, SessionPolicy (POS: Channel message types.)
- app.channels.core.outbound_media::discard_ephemeral_media (POS: temp attachment cleanup)
- app.core.channel_bridge.executor_helpers::StreamAccumulator, persist_assistant_message (POS: Stream accumulation for channel turns.)
- agent_executor.deliverable::build_artifact_deep_links (POS: Artifact delivery helpers for ChannelAgentExecutor.)
- agent_executor.deliverable::append_deliverable_notes, collect_deliverable_paths_from_text, resolve_chat_workspace_root (POS: Channel deliverable attachment mode (Hermes parity). Complements artifact event collection in deliverable.deep_links.collect_channel_artifacts.)
- app.channels.i18n::channel_t, resolve_message_locale (POS: Channel i18n message catalog and locale resolution)
- app.channels.routing.friendly_errors::ERROR_TYPE_METADATA_KEY, friendly_error_text (POS: member-safe error wording with reference id)
[OUTPUT]
- finalize_channel_stream_reply: persist assistant turn and build OutboundMessage reply (temp files ride along
  as ``ephemeral`` attachments; the message bus deletes them once delivery is final)

[POS]
Finalizes a completed harness stream into a channel OutboundMessage: content cleanup,
cost recording, metadata, media attachments, and artifact deep-link buttons. A failed turn
replies with the member-safe wording of its error kind and a reference id (after any text that had
already streamed, so a cut-off answer is never presented as complete); the raw error text only
goes to the operator log under the same id.
"""

from __future__ import annotations

import asyncio
import base64 as b64
import logging
import tempfile

from myrm_agent_harness.utils.text_utils import strip_internal_markers

from app.channels.core.outbound_media import discard_ephemeral_media
from app.channels.routing.friendly_errors import ERROR_TYPE_METADATA_KEY, friendly_error_text
from app.channels.types import (
    InboundMessage,
    MediaAttachment,
    MediaType,
    OutboundMessage,
    SessionPolicy,
)
from app.core.channel_bridge.executor_helpers import (
    StreamAccumulator,
    generate_channel_title,
    persist_assistant_message,
    suggest_quick_replies,
)
from app.core.types.business import ModelConfig

from .deliverable import (
    append_deliverable_notes,
    build_artifact_deep_links,
    collect_deliverable_paths_from_text,
    resolve_chat_workspace_root,
)

logger = logging.getLogger(__name__)


def _failed_turn_wording(
    acc: StreamAccumulator,
    msg: InboundMessage,
    *,
    account_guidance: bool,
) -> tuple[str, str]:
    """Member-safe wording of a failed turn and its error type; the raw error text goes to the log under the same reference id."""
    wording, ref_id = friendly_error_text(acc.error_kind, msg, account_guidance=account_guidance)
    logger.warning(
        "ChannelAgentExecutor: agent error for %s [ref: %s]: %s",
        msg.sender_id,
        ref_id,
        acc.error_message,
    )
    return wording, acc.error_kind.value


async def finalize_channel_stream_reply(
    msg: InboundMessage,
    *,
    acc: StreamAccumulator,
    chat_id: str,
    message_id: str | None = None,
    channel_budget_key: str | None,
    memory_settings: dict[str, object],
    lite_model_cfg: ModelConfig | None,
    chat_history: list[object],
    session_was_auto_reset: bool,
    session_policy: SessionPolicy,
    account_guidance: bool,
) -> OutboundMessage:
    """Build the final channel reply after stream accumulation.

    A failed turn is flagged with ``ERROR_TYPE_METADATA_KEY`` so hosts that run the turn for someone else
    (the delegation coordinator) can tell it from an answer. ``account_guidance`` lets the owner's direct
    chat name the account state to fix.
    """
    from app.channels.i18n import channel_t, resolve_message_locale

    content = strip_internal_markers(acc.draft.text)

    workspace_root = await resolve_chat_workspace_root(chat_id)
    scanned_attachments: list[MediaAttachment] = []
    scanned_oversized: list[tuple[str, str]] = []
    scanned_compressed: list[tuple[str, str]] = []
    if content.strip() and workspace_root:
        (
            content,
            scanned_attachments,
            scanned_oversized,
            scanned_compressed,
        ) = await asyncio.to_thread(
            collect_deliverable_paths_from_text,
            content,
            workspace_root=workspace_root,
            existing_filenames={m.filename for m in acc.file_attachments if m.filename},
        )

    oversized_raw = list(dict.fromkeys(scanned_oversized + acc.oversized_deliverables))
    compressed_raw = list(dict.fromkeys(scanned_compressed + acc.compressed_deliverables))

    media_list: list[MediaAttachment] = []
    if acc.last_image_base64:
        ext = "jpg" if "jpeg" in acc.last_image_mime else "png"
        try:
            img_bytes = b64.b64decode(acc.last_image_base64)
            tmp = tempfile.NamedTemporaryFile(
                suffix=f".{ext}",
                prefix="screenshot_",
                delete=False,
            )
            tmp.write(img_bytes)
            tmp.close()
            media_list.append(
                MediaAttachment(
                    media_type=MediaType.IMAGE,
                    path=tmp.name,
                    filename=f"screenshot.{ext}",
                    mime_type=acc.last_image_mime,
                    ephemeral=True,
                ),
            )
        except Exception:
            logger.warning("Failed to save screenshot image for channel reply")
    elif acc.last_image_url:
        ext = "jpg" if "jpeg" in acc.last_image_mime else "png"
        media_list.append(
            MediaAttachment(
                media_type=MediaType.IMAGE,
                url=acc.last_image_url,
                filename=f"screenshot.{ext}",
                mime_type=acc.last_image_mime,
            ),
        )

    media_list.extend(acc.file_attachments)
    media_list.extend(scanned_attachments)

    artifact_components, linked_filenames = await build_artifact_deep_links(
        acc,
        resolve_message_locale(msg),
    )

    # Deep-linked artifacts get buttons, so their duplicate attachment and
    # fallback note are suppressed.
    discard_ephemeral_media(m for m in media_list if m.filename in linked_filenames)
    media_list = [m for m in media_list if m.filename not in linked_filenames]
    oversized_notes = [(fname, size) for fname, size in oversized_raw if fname not in linked_filenames]
    compressed_notes = compressed_raw

    error_type: str | None = None
    if not content.strip() and not oversized_notes and not compressed_notes:
        if artifact_components or media_list:
            locale = resolve_message_locale(msg)
            content = str(channel_t(locale, "deliverable_attached_only"))
        elif acc.error_message:
            content, error_type = _failed_turn_wording(acc, msg, account_guidance=account_guidance)
        else:
            logger.warning("ChannelAgentExecutor: empty LLM response for %s", msg.sender_id)
            content = "[No response generated]"
    elif acc.error_message:
        # The stream broke after text had gone out: keep that text, but say it is incomplete.
        notice, error_type = _failed_turn_wording(acc, msg, account_guidance=account_guidance)
        content = f"{content.strip()}\n\n{notice}" if content.strip() else notice

    content = append_deliverable_notes(
        content,
        locale=resolve_message_locale(msg),
        oversized_notes=oversized_notes,
        compressed_notes=compressed_notes,
    )

    await persist_assistant_message(
        chat_id,
        content,
        message_id=message_id,
        timezone=msg.sent_timezone,
        extra_data=(
            {
                "costUsd": acc.cost_usd,
                "channelSenderId": msg.sender_id,
            }
            if acc.cost_usd > 0
            else None
        ),
    )

    if channel_budget_key and acc.cost_usd > 0:
        from app.services.budget.channel_budget import record_channel_cost

        record_channel_cost(channel_budget_key, acc.cost_usd)

    if not chat_history:
        auto_title = bool(memory_settings.get("enableAutoTitleGeneration", True))
        asyncio.create_task(
            generate_channel_title(
                chat_id,
                msg.content,
                lite_model_cfg if auto_title else None,
            )
        )

    metadata: dict[str, object] = {}
    if error_type:
        metadata[ERROR_TYPE_METADATA_KEY] = error_type
    if acc.sources:

        def _sort_key(s: dict[str, object]) -> int:
            v = s.get("index")
            return int(v) if isinstance(v, (int, float)) else 0

        metadata["sources"] = sorted(acc.sources, key=_sort_key)

    if session_was_auto_reset:
        metadata["session_auto_reset"] = {
            "reason": session_policy.mode.value,
            "idle_minutes": session_policy.idle_minutes,
            "daily_reset_hour": session_policy.daily_reset_hour,
        }

    if acc.cost_usd > 0 and memory_settings.get("enableCostEstimation"):
        metadata["cost_metadata"] = {
            "cost_usd": acc.cost_usd,
            "model_name": acc.model_name,
            "total_tokens": acc.total_tokens,
        }

    reasoning = "".join(acc.reasoning_chunks) or None
    tool_steps = tuple(acc.tool_steps)
    quick_replies = suggest_quick_replies(is_first_message=not chat_history)

    reply = msg.get_or_create_correlation_context().create_reply(
        content=content,
        metadata=metadata or None,
        media=tuple(media_list),
        reasoning=reasoning,
        tool_steps=tool_steps,
        components=artifact_components,
        quick_replies=quick_replies,
    )
    return reply
