"""Channel execution error replies for ChannelAgentExecutor.

[INPUT]
- app.channels.types::InboundMessage, OutboundMessage (POS: Channel message types.)
- myrm_agent_harness.toolkits.llms.errors::MyrmLLMError (POS: LLM error with diagnostics.)

[OUTPUT]
- build_config_incomplete_reply / build_llm_error_reply / build_generic_error_reply

[POS]
Maps harness and config exceptions to channel-friendly OutboundMessage replies.
"""

from __future__ import annotations

from myrm_agent_harness.api import ConfigIncompleteError
from myrm_agent_harness.toolkits.llms.errors import MyrmLLMError
from myrm_agent_harness.utils.locale import is_chinese

from app.channels.i18n import get_text, resolve_message_locale
from app.channels.types import InboundMessage, OutboundMessage


def build_config_incomplete_reply(msg: InboundMessage, exc: ConfigIncompleteError) -> OutboundMessage:
    locale = resolve_message_locale(msg)
    lang_key = "zh" if is_chinese(locale) else "en"
    friendly_msg = exc.user_friendly_message.get(lang_key) or exc.user_friendly_message.get("en", str(exc))
    error_metadata = {
        "error_type": exc.error_code,
        "resolution_steps": exc.resolution_steps,
        "config_url": "/settings/model-service",
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
    resolution_steps = diagnostic_result.get("resolution_steps", [])
    friendly_msg = f"❌ {user_message}"

    if exc.context and "cooldown_remaining_ms" in exc.context:
        retry_after_seconds = int(exc.context["cooldown_remaining_ms"]) / 1000
        friendly_msg += get_text(msg, "cooldown_retry", seconds=retry_after_seconds)

    if resolution_steps:
        steps_text = "\n".join(f"• {step}" for step in resolution_steps[:3])
        friendly_msg += get_text(msg, "config_next_steps", steps=steps_text)

    from app.core.errors.llm_errors import generate_recovery_actions

    recovery_actions = generate_recovery_actions(exc.error_code, lang_key)
    components: list[tuple[object, ...]] = []
    if msg.channel_capabilities and msg.channel_capabilities.buttons and recovery_actions:
        from app.channels.types.messages import ActionButton

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
        "error_type": exc.error_code,
        "recovery_actions": recovery_actions,
    }
    return msg.get_or_create_correlation_context().create_reply(
        content=friendly_msg,
        components=tuple(components) if components else (),
        metadata=error_metadata,
    )


def build_generic_error_reply(msg: InboundMessage, exc: Exception) -> OutboundMessage:
    return msg.get_or_create_correlation_context().create_reply(
        content=f"[Error] Agent execution failed: {exc}",
    )
