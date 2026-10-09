"""Outbound message preparation: correlation lineage, capability downgrade, risk gate and delivery verdicts.

[INPUT]
- channels.i18n::channel_t, get_locale_from_metadata (POS: channel-scoped localized text)
- channels.types::OutboundMessage, ChannelCapabilities, CorrelationContext, MediaType (POS: channel message value types)
- services.risk.detection::get_detection_service (POS: stateful risk detection engine with compiled regex cache)

[OUTPUT]
- set_correlation_context / get_correlation_context: implicit routing lineage across async tasks
- apply_correlation_context: corrects drifted routes from the active lineage
- prepare_outbound: capability downgrade + risk gate, the one preparation step shared by every outbound path
- downgrade_components: interactive component and media downgrade (appends text fallback when channel lacks support)
- apply_outbound_risk_gate: content safety detection before send (reuses RiskDetectionService)
- delivery_unconfirmed: whether a ``send()`` result proves delivery on the channel's declared contract
- undelivered_part / partial_failure_note: the attachments-only remainder and in-band note after a partial delivery

[POS]
Pure message transformations shared by the outbound paths. Outbound messages are auto-downgraded
before dispatch for channels lacking interactive component support: components are rendered as
text appended to content; quick_replies only downgrade ``required=True`` items, silently dropping
non-required ones. Callers pass the capabilities of the route actually used (control-plane egress
is text-only), never the channel object, so the downgrade stays independent of provider instances.
"""

from __future__ import annotations

import asyncio
import contextvars
import dataclasses
import logging
import uuid

from app.channels.i18n import channel_t, get_locale_from_metadata
from app.channels.types import (
    ActionButton,
    ChannelCapabilities,
    ComponentRow,
    CorrelationContext,
    MediaType,
    OutboundMessage,
    SelectMenu,
    render_components_as_text,
    render_quick_replies_as_text,
)

logger = logging.getLogger(__name__)


# Global context var for implicit routing lineage across async tasks
_correlation_context_var: contextvars.ContextVar[CorrelationContext | None] = contextvars.ContextVar(
    "correlation_context", default=None
)


def set_correlation_context(
    ctx: CorrelationContext | None,
) -> contextvars.Token[CorrelationContext | None]:
    """Set the current correlation context for the async execution flow."""
    return _correlation_context_var.set(ctx)


def get_correlation_context() -> CorrelationContext | None:
    """Get the current correlation context for the async execution flow."""
    return _correlation_context_var.get()


def apply_correlation_context(msg: OutboundMessage) -> OutboundMessage:
    """Apply the active correlation context to an outbound message, correcting drifted routes."""
    ctx = msg.correlation_context or get_correlation_context()
    if not ctx:
        return msg

    # If the message already has the exact same context, no need to replace
    if msg.correlation_context == ctx and msg.channel == ctx.channel and msg.recipient_id == ctx.chat_id:
        return msg

    # Correct the routing using the immutable lineage context
    return dataclasses.replace(
        msg,
        channel=ctx.channel,
        recipient_id=ctx.chat_id or msg.recipient_id,
        correlation_context=ctx,
    )


def apply_outbound_risk_gate(msg: OutboundMessage) -> OutboundMessage:
    """Apply risk detection to outbound message content before sending to IM channels.

    Uses the global RiskDetectionService (compiled regex cache, <1ms).
    If blocked, replaces content with a safe i18n message and fires audit asynchronously.
    Returns the original message unchanged when no rules match or service has zero rules.
    """
    if not msg.content:
        return msg

    from app.services.risk.detection import get_detection_service

    service = get_detection_service()
    if service.rule_count == 0:
        return msg

    result = service.detect(msg.content)
    if not result.blocked:
        return msg

    locale = get_locale_from_metadata(msg.metadata)
    blocked_content = channel_t(locale, "risk_outbound_blocked")

    logger.info(
        "Outbound risk gate blocked message on channel '%s': rules=%s",
        msg.channel,
        [m.display_name for m in result.matches],
    )

    asyncio.ensure_future(_record_outbound_risk_hits(result.matches, msg))

    return dataclasses.replace(msg, content=blocked_content)


async def _record_outbound_risk_hits(matches: tuple[object, ...], msg: OutboundMessage) -> None:
    """Fire-and-forget: persist risk hit records for outbound blocked messages."""
    try:
        from app.platform_utils import get_session_factory
        from app.services.risk.detection import get_detection_service

        service = get_detection_service()
        session_factory = get_session_factory()
        async with session_factory() as db:
            await service.record_hits(
                db,
                matches,  # type: ignore[arg-type]
                trace_id=str(uuid.uuid4()),
                session_id=msg.recipient_id,
            )
            await db.commit()
    except Exception:
        logger.debug("Failed to record outbound risk hits (non-critical)", exc_info=True)


def prepare_outbound(msg: OutboundMessage, capabilities: ChannelCapabilities, *, channel_name: str) -> OutboundMessage:
    """Make ``msg`` safe and sendable for a route: capability downgrade, then the content risk gate."""
    return apply_outbound_risk_gate(downgrade_components(msg, capabilities, channel_name=channel_name))


def downgrade_components(msg: OutboundMessage, capabilities: ChannelCapabilities, *, channel_name: str) -> OutboundMessage:
    """Downgrade interactive components to text when the route lacks native support.

    Returns the original message unchanged if no downgrade is needed.

    Per-row granularity: a row containing SelectMenu items is downgraded
    independently from rows containing only ActionButton items, allowing
    channels that support buttons but not select menus to keep the buttons.

    For quick_replies, only ``required=True`` items are rendered as text
    fallback (e.g. approval prompts). Non-required items (e.g. suggestions)
    are silently dropped to avoid cluttering text-only channels.

    **Locale support**: Reads ``msg.metadata["locale"]`` (default: "en" for framework
    internationalization compliance). Business layer should inject user's preferred
    locale via metadata (e.g., from UserConfig or browser Accept-Language header).
    Fallback messages are rendered in the specified language:
    - "zh": "item", "reply countselect"
    - "en": "Options", "Reply with a number to select"

    **Logging**: When components are downgraded, an INFO-level log is emitted:
    ``Downgrading components for channel 'whatsapp': buttons, quick_replies(2) → text fallback``

    **Example**::

        # Original message with buttons
        msg = OutboundMessage(
            channel="whatsapp",
            recipient_id="user123",
            content="Choose an option:",
            components=(
                (ActionButton(label="Approve", action_id="approve"),),
            ),
        )

        # After downgrade (WhatsApp doesn't support buttons)
        result = downgrade_components(msg, whatsapp_channel.capabilities, channel_name="whatsapp")
        # result.content = "Choose an option:\\n\\n• Approve → /approve"
        # result.components = ()
    """
    if not msg.components and not msg.quick_replies and not msg.media:
        return msg

    caps = capabilities
    locale = get_locale_from_metadata(msg.metadata)
    changed = False
    fallback_parts: list[str] = []
    kept_rows: list[ComponentRow] = []
    downgraded_types: list[str] = []

    for row in msg.components:
        has_select = any(isinstance(c, SelectMenu) for c in row)
        has_button = any(isinstance(c, ActionButton) for c in row)

        if has_select and not caps.select_menus:
            text = render_components_as_text((row,), locale=locale)
            if text:
                fallback_parts.append(text)
            changed = True
            if "select_menus" not in downgraded_types:
                downgraded_types.append("select_menus")
        elif has_button and not caps.buttons:
            text = render_components_as_text((row,), locale=locale)
            if text:
                fallback_parts.append(text)
            changed = True
            if "buttons" not in downgraded_types:
                downgraded_types.append("buttons")
        else:
            kept_rows.append(row)

    keep_quick_replies = msg.quick_replies
    if msg.quick_replies and not caps.quick_replies:
        required_qrs = tuple(qr for qr in msg.quick_replies if qr.required)
        if required_qrs:
            text = render_quick_replies_as_text(required_qrs, locale=locale)
            if text:
                fallback_parts.append(text)
            downgraded_types.append(f"quick_replies({len(required_qrs)})")
        keep_quick_replies = ()
        changed = True

    keep_media = msg.media
    if msg.media:
        media_fallback_parts = []
        keep_media_list = []

        for m in msg.media:
            is_document = m.media_type == MediaType.DOCUMENT
            should_strip = (is_document and not caps.file_upload) or (not is_document and not caps.media)

            if should_strip:
                if m.url:
                    media_fallback_parts.append(f"[{m.media_type.value.capitalize()}: {m.url}]")
                elif m.path:
                    media_fallback_parts.append(str(channel_t(locale, "attachment_omitted_note", name=m.display_name)))
            else:
                keep_media_list.append(m)

        if media_fallback_parts:
            fallback_parts.extend(media_fallback_parts)
            downgraded_types.append(f"media({len(media_fallback_parts)})")
            changed = True

        keep_media = tuple(keep_media_list)

    if not changed:
        return msg

    logger.info(
        "Downgrading components/media for channel '%s': %s → text fallback",
        channel_name,
        ", ".join(downgraded_types),
    )

    suffix = "\n\n" + "\n".join(fallback_parts) if fallback_parts else ""
    return dataclasses.replace(
        msg,
        content=msg.content + suffix,
        components=tuple(kept_rows),
        quick_replies=keep_quick_replies,
        media=keep_media,
    )


def delivery_unconfirmed(capabilities: ChannelCapabilities, msg: OutboundMessage, result: str | None) -> bool:
    """True when ``send()`` returned nothing although the channel promises ids for this message.

    Channels declaring ``message_ids=False`` never return ids, so ``None`` is their success.
    Media-only sends are exempt: providers such as Slack and Telegram return no id for them.
    """
    return result is None and capabilities.message_ids and bool(msg.content)


def undelivered_part(msg: OutboundMessage, failed_names: tuple[str, ...]) -> OutboundMessage:
    """Attachments-only remainder of ``msg`` after a partial delivery.

    Selects the attachments reported as failed (all of them when none of the names matches) so a
    later re-send never duplicates text or attachments the recipient already received.
    """
    failed = tuple(m for m in msg.media if m.display_name in failed_names) or msg.media
    return dataclasses.replace(msg, content="", media=failed, components=(), quick_replies=())


def partial_failure_note(msg: OutboundMessage, failed_names: tuple[str, ...]) -> OutboundMessage:
    """In-band note telling the recipient which attachments did not arrive."""
    locale = get_locale_from_metadata(msg.metadata)
    note = str(channel_t(locale, "attachment_failed_note", names=", ".join(failed_names)))
    metadata = {"locale": msg.metadata["locale"]} if msg.metadata and "locale" in msg.metadata else None
    return OutboundMessage(
        channel=msg.channel,
        recipient_id=msg.recipient_id,
        content=note,
        user_id=msg.user_id,
        metadata=metadata,
        reply_to_id=msg.reply_to_id,
        thread_id=msg.thread_id,
        priority=msg.priority,
    )
