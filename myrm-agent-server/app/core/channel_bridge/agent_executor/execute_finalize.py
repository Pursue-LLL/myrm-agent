"""Post-stream reply assembly for channel agent execution.

[INPUT]
- app.channels.types::InboundMessage, MediaAttachment, OutboundMessage (POS: Channel message types.)
- app.core.channel_bridge.executor_helpers::StreamAccumulator, persist_assistant_message (POS: Stream accumulation for channel turns.)
- agent_executor.artifact_deep_links::build_artifact_deep_links (POS: Artifact share-link buttons for IM outbound.)

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
import os
import tempfile

from myrm_agent_harness.utils.text_utils import strip_internal_markers

from app.core.types.business import ModelConfig

from app.channels.i18n import resolve_message_locale
from app.channels.types import InboundMessage, MediaAttachment, MediaType, OutboundMessage
from app.core.channel_bridge.config_parsers import SessionPolicy
from app.core.channel_bridge.executor_helpers import (
    StreamAccumulator,
    generate_channel_title,
    persist_assistant_message,
    suggest_quick_replies,
)

from .artifact_deep_links import build_artifact_deep_links

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
    content = strip_internal_markers("".join(acc.chunks))

    if not content.strip():
        if acc.error_message:
            logger.warning(
                "ChannelAgentExecutor: agent error for %s: %s",
                msg.sender_id,
                acc.error_message,
            )
            content = f"[Error] {acc.error_message}"
        else:
            logger.warning("ChannelAgentExecutor: empty LLM response for %s", msg.sender_id)
            content = "[No response generated]"

    await persist_assistant_message(
        chat_id,
        content,
        message_id=message_id,
        timezone=msg.sent_timezone,
        extra_data={
            "costUsd": acc.cost_usd,
            "channelSenderId": msg.sender_id,
        } if acc.cost_usd > 0 else None,
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

    media_list: list[MediaAttachment] = []
    tmp_paths: list[str] = []
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

    artifact_components = await build_artifact_deep_links(
        acc, media_list, resolve_message_locale(msg),
    )

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
