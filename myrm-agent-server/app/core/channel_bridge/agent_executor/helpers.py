"""Channel agent executor helpers.

[INPUT]
- app.channels.types::InboundMessage, ReplyContext (POS: Ingress messages from providers or Control Plane.)
- agent.security.detection.content_boundary.sanitize (POS: Untrusted text folding.)
- app.core.utils.delivery_provenance::prepend_plain_banner, ingress_from_channel_metadata (POS: Shared LLM-visible delivery banners.)

[OUTPUT]
- build_channel_inbound_query: Multimodal or plain-text query with delivery provenance banner.
- _resolve_inbound_memory_identity: Resolved memory identifiers for inbound messages.

[POS]
Business-layer assembly for IM/channel turns headed to the SkillAgent runtime.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.channels.types import ContextEntry, InboundMessage, ReplyContext
from app.core.utils.delivery_provenance import (
    ingress_from_channel_metadata,
    prepend_plain_banner,
)

_REPLY_CONTENT_MAX_LEN = 500


@dataclass(frozen=True, slots=True)
class _InboundMemoryIdentity:
    channel_id: str
    conversation_id: str
    task_id: str


def invalidate_agent_overrides_cache(agent_id: str) -> None:
    """Backward-compatible shim — delegates to AgentProfileResolver.invalidate()."""
    from app.services.agent.profile_resolver import get_agent_profile_resolver

    get_agent_profile_resolver().invalidate(agent_id)


def _extract_code_exec_network(ps: dict[str, object]) -> bool | None:
    """Extract code execution network permission from personalSettings dict."""
    value = ps.get("codeExecutionAllowNetwork")
    return value if isinstance(value, bool) else None


def _resolve_inbound_memory_identity(
    msg: InboundMessage,
    *,
    fallback_chat_id: str,
    fallback_task_id: str,
) -> _InboundMemoryIdentity:
    """Resolve Control Plane-provided memory identity or fall back to local runtime values."""
    resolved = msg.metadata.get("resolved_identity")
    if isinstance(resolved, dict):
        channel_id = resolved.get("channel_id")
        conversation_id = resolved.get("conversation_id")
        task_id = resolved.get("task_id")
        if (
            isinstance(channel_id, str)
            and channel_id
            and isinstance(conversation_id, str)
            and conversation_id
            and isinstance(task_id, str)
            and task_id
        ):
            return _InboundMemoryIdentity(
                channel_id=channel_id,
                conversation_id=conversation_id,
                task_id=task_id,
            )

    return _InboundMemoryIdentity(
        channel_id=msg.channel,
        conversation_id=fallback_chat_id,
        task_id=fallback_task_id,
    )


def _format_reply_context(reply_to: ReplyContext) -> str:
    """Format structured reply context into an LLM-readable disambiguation prefix.

    Tells the LLM which prior message the user is referencing so it can
    respond precisely rather than guessing from ambiguous pronouns.
    """
    from myrm_agent_harness.agent.security.detection.content_boundary import sanitize

    sender = reply_to.sender_name or reply_to.sender_id or "someone"
    content = reply_to.content.strip() if reply_to.content else ""

    if content:
        if len(content) > _REPLY_CONTENT_MAX_LEN:
            content = content[:_REPLY_CONTENT_MAX_LEN] + "..."
        content = sanitize(content)

    parts: list[str] = [f'[Replying to {sender}]']
    if content:
        parts.append(f': "{content}"')
    if reply_to.media:
        parts.append(f" [{len(reply_to.media)} attachment(s)]")

    return "".join(parts)


def _format_group_context_section(context_messages: tuple[ContextEntry, ...], user_trigger_line: str) -> str:
    """Accumulate recent group snippets plus the trigger message (sanitized)."""
    from myrm_agent_harness.agent.security.detection.content_boundary import sanitize

    lines = [f"{e.sender_id}: {sanitize(e.content)}" for e in context_messages]
    context_block = "\n".join(lines)
    return f"[Recent group chat messages for context]\n{context_block}\n---\n{user_trigger_line}"


def build_channel_inbound_query(msg: InboundMessage) -> str | list[dict[str, object]]:
    """Assemble the channel user payload as plain text or multimodal query.

    When ``msg.metadata["image_data_list"]`` is present (populated by Harness
    image enrichment), constructs an OpenAI Vision-compatible multimodal
    content list. Otherwise returns plain text with a delivery banner.

    When ``msg.reply_to`` is present, prepends structured reply context so the
    LLM can disambiguate which prior message the user is referencing.
    """
    meta = msg.metadata if isinstance(msg.metadata, dict) else None
    ingress = ingress_from_channel_metadata(meta)

    user_text = msg.content
    if msg.reply_to:
        reply_prefix = _format_reply_context(msg.reply_to)
        user_text = f"{reply_prefix}\n---\n{user_text}"

    if msg.context_messages:
        body = _format_group_context_section(msg.context_messages, user_text)
    else:
        body = user_text

    text = prepend_plain_banner(channel_label=msg.channel, ingress_label=ingress, body=body)

    image_data_list = msg.metadata.get("image_data_list") if isinstance(msg.metadata, dict) else None
    if not image_data_list or not isinstance(image_data_list, list):
        return text

    parts: list[dict[str, object]] = [{"type": "text", "text": text}]
    for item in image_data_list:
        if isinstance(item, dict) and "data_url" in item:
            parts.append({
                "type": "image_url",
                "image_url": {"url": item["data_url"], "detail": "auto"},
            })

    if len(parts) == 1:
        return text

    return parts
