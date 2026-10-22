"""Channel execution error replies for ChannelAgentExecutor.

[INPUT]
- app.channels.types::InboundMessage, OutboundMessage (POS: Channel message types.)
- app.channels.routing.friendly_errors::ERROR_TYPE_METADATA_KEY, friendly_error_text (POS: member-safe error wording with reference id)
- myrm_agent_harness.toolkits.llms.errors::MyrmLLMError (POS: LLM error with diagnostics.)

[OUTPUT]
- build_config_incomplete_reply / build_llm_error_reply / build_generic_error_reply

[POS]
Maps harness and config exceptions to channel-friendly OutboundMessage replies.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.api.config import ConfigIncompleteError
from myrm_agent_harness.toolkits.llms.errors import MyrmLLMError
from myrm_agent_harness.toolkits.llms.errors.classifier import classify_error
from myrm_agent_harness.utils.locale import is_chinese

from app.channels.i18n import get_text, resolve_message_locale
from app.channels.routing.friendly_errors import ERROR_TYPE_METADATA_KEY, friendly_error_text
from app.channels.types import ActionButton, ComponentRow, InboundMessage, OutboundMessage

logger = logging.getLogger(__name__)


def build_config_incomplete_reply(msg: InboundMessage, exc: ConfigIncompleteError) -> OutboundMessage:
    locale = resolve_message_locale(msg)
    lang_key = "zh" if is_chinese(locale) else "en"
    friendly_msg = exc.user_friendly_message.get(lang_key) or exc.user_friendly_message.get("en", str(exc))
    error_metadata: dict[str, object] = {
        ERROR_TYPE_METADATA_KEY: exc.error_code,
        "resolution_steps": exc.resolution_steps,
    }
    steps_text = "\n".join(f"• {step}" for step in exc.resolution_steps[:3])
    return msg.get_or_create_correlation_context().create_reply(
        content=f"{friendly_msg}{get_text(msg, 'config_next_steps', steps=steps_text)}",
        metadata=error_metadata,
    )


def build_llm_error_reply(msg: InboundMessage, exc: MyrmLLMError) -> OutboundMessage:
    locale = resolve_message_locale(msg)
    lang_key = "zh" if is_chinese(locale) else "en"
    diagnostic_result = exc.diagnostic_result or {}
    user_message = diagnostic_result.get("user_message", str(exc))
    raw_steps = diagnostic_result.get("resolution_steps")
    resolution_steps = [str(step) for step in raw_steps[:3]] if isinstance(raw_steps, list) else []
    friendly_msg = f"❌ {user_message}"

    if resolution_steps:
        steps_text = "\n".join(f"• {step}" for step in resolution_steps)
        friendly_msg += get_text(msg, "config_next_steps", steps=steps_text)

    from app.core.errors.llm_errors import generate_recovery_actions

    recovery_actions = generate_recovery_actions(exc.error_code, lang_key)
    components: list[ComponentRow] = []
    if msg.channel_capabilities and msg.channel_capabilities.buttons and recovery_actions:
        action_buttons = [
            ActionButton(
                label=action["label"],
                action_id=action["id"],
                value=action["id"],
            )
            for action in recovery_actions
        ]
        if action_buttons:
            components.append(tuple(action_buttons))

    error_metadata = {
        ERROR_TYPE_METADATA_KEY: exc.error_code,
        "recovery_actions": recovery_actions,
    }
    return msg.get_or_create_correlation_context().create_reply(
        content=friendly_msg,
        components=tuple(components) if components else (),
        metadata=error_metadata,
    )


def build_generic_error_reply(msg: InboundMessage, exc: Exception, *, account_guidance: bool) -> OutboundMessage:
    """Member-safe reply for an unexpected executor failure; the raw error goes to the log under the reference id."""
    kind = classify_error(exc)
    content, ref_id = friendly_error_text(kind, msg, account_guidance=account_guidance)
    logger.error("ChannelAgentExecutor: agent failed for %s [ref: %s]: %s", msg.sender_id, ref_id, exc, exc_info=exc)
    return msg.get_or_create_correlation_context().create_reply(
        content=content,
        metadata={ERROR_TYPE_METADATA_KEY: kind.value},
    )
