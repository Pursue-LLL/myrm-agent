"""Post-stream reply assembly for channel agent execution.

[INPUT]
- app.channels.types::InboundMessage, MediaAttachment, OutboundMessage (POS: Channel message types.)
- app.core.channel_bridge.executor_helpers::StreamAccumulator, persist_assistant_message (POS: Stream accumulation for channel turns.)
- agent_executor.deliverable::build_artifact_deep_links (POS: Artifact delivery helpers for ChannelAgentExecutor.)
- agent_executor.deliverable::collect_deliverable_paths_from_text, resolve_chat_workspace_root (POS: Channel deliverable attachment mode (Hermes parity). Complements artifact event collection in deliverable.deep_links.collect_channel_artifacts.)
- app.channels.i18n::channel_t, resolve_message_locale (POS: Channel i18n message catalog and locale resolution)

[OUTPUT]
- finalize_channel_stream_reply: persist assistant turn and build OutboundMessage reply

[POS]
Finalizes a completed harness stream into a channel OutboundMessage: content cleanup,
cost recording, metadata, media attachments, and artifact deep-link buttons.
"""

from __future__ import annotations

import asyncio
import base64 as b64
import logging
import tempfile

from myrm_agent_harness.utils.text_utils import strip_internal_markers

from app.channels.types import (
    InboundMessage,
    MediaAttachment,
    MediaType,
    OutboundMessage,
)
from app.core.channel_bridge.config_parsers import SessionPolicy
from app.core.channel_bridge.executor_helpers import (
    StreamAccumulator,
    generate_channel_title,
    persist_assistant_message,
    suggest_quick_replies,
)
from app.core.types.business import ModelConfig

from .deliverable import (
    build_artifact_deep_links,
    collect_deliverable_paths_from_text,
    resolve_chat_workspace_root,
)

logger = logging.getLogger(__name__)


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
) -> tuple[OutboundMessage, list[str]]:
    """Build the final channel reply after stream accumulation."""
    from app.channels.i18n import channel_t, resolve_message_locale

    content = strip_internal_markers("".join(acc.chunks))

    workspace_root = await resolve_chat_workspace_root(chat_id)
    scanned_attachments: list[MediaAttachment] = []
    scanned_oversized: list[tuple[str, str]] = []
    scanned_compressed: list[tuple[str, str]] = []
    scanned_tmp_paths: list[str] = []
    if content.strip() and workspace_root:
        (
            content,
            scanned_attachments,
            scanned_oversized,
            scanned_compressed,
            scanned_tmp_paths,
        ) = await asyncio.to_thread(
            collect_deliverable_paths_from_text,
            content,
            workspace_root=workspace_root,
            existing_filenames={m.filename for m in acc.file_attachments},
        )

    oversized_raw = list(dict.fromkeys(scanned_oversized + acc.oversized_deliverables))
    compressed_raw = list(dict.fromkeys(scanned_compressed + acc.compressed_deliverables))

    media_list: list[MediaAttachment] = []
    tmp_paths: list[str] = list(acc.pending_tmp_paths)
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
            tmp_paths.append(tmp.name)
            media_list.append(
                MediaAttachment(
                    media_type=MediaType.IMAGE,
                    path=tmp.name,
                    filename=f"screenshot.{ext}",
                    mime_type=acc.last_image_mime,
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
    tmp_paths.extend(scanned_tmp_paths)

    artifact_components, linked_filenames = await build_artifact_deep_links(
        acc,
        resolve_message_locale(msg),
    )

    # Deep-linked artifacts get buttons, so their duplicate attachment and
    # fallback note are suppressed.
    media_list = [m for m in media_list if m.filename not in linked_filenames]
    oversized_notes = [(fname, size) for fname, size in oversized_raw if fname not in linked_filenames]
    compressed_notes = compressed_raw

    if not content.strip() and not oversized_notes and not compressed_notes:
        if artifact_components or media_list:
            locale = resolve_message_locale(msg)
            content = str(channel_t(locale, "deliverable_attached_only"))
        elif acc.error_message:
            logger.warning(
                "ChannelAgentExecutor: agent error for %s: %s",
                msg.sender_id,
                acc.error_message,
            )
            content = f"[Error] {acc.error_message}"
        else:
            logger.warning("ChannelAgentExecutor: empty LLM response for %s", msg.sender_id)
            content = "[No response generated]"

    if oversized_notes or compressed_notes:
        locale = resolve_message_locale(msg)
        note_lines = [
            str(channel_t(locale, "deliverable_oversized_note", filename=fname, size=size)) for fname, size in oversized_notes
        ]
        note_lines.extend(
            str(channel_t(locale, "deliverable_compressed_note", filename=fname, size=size)) for fname, size in compressed_notes
        )
        if content.strip():
            content = f"{content.strip()}\n\n" + "\n".join(note_lines)
        else:
            content = "\n".join(note_lines)

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

    metadata: dict[str, object] | None = None
    if acc.sources:

        def _sort_key(s: dict[str, object]) -> int:
            v = s.get("index")
            return int(v) if isinstance(v, (int, float)) else 0

        metadata = {"sources": sorted(acc.sources, key=_sort_key)}

    if session_was_auto_reset:
        if metadata is None:
            metadata = {}
        metadata["session_auto_reset"] = {
            "reason": session_policy.mode.value,
            "idle_minutes": session_policy.idle_minutes,
            "daily_reset_hour": session_policy.daily_reset_hour,
        }

    if acc.cost_usd > 0 and memory_settings.get("enableCostEstimation"):
        if metadata is None:
            metadata = {}
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
        metadata=metadata,
        media=tuple(media_list),
        reasoning=reasoning,
        tool_steps=tool_steps,
        components=artifact_components,
        quick_replies=quick_replies,
    )
    return reply, tmp_paths
