"""Citation rules middleware for GeneralAgent.

Appends citation formatting rules as a transient HumanMessage (via request.override)
when the current user turn contains UNTRUSTED external sources.
Uses HumanMessage to preserve SystemMessage hash stability for prompt caching.
"""

import logging
from collections.abc import Awaitable, Callable, Sequence

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import HumanMessage, ToolMessage
from myrm_agent_harness.utils.locale import is_chinese

from app.ai_agents.prompts.general_agent_prompt import get_citation_rules_if_needed

logger = logging.getLogger(__name__)

_UNTRUSTED_DATA_MARKER = "<<<UNTRUSTED_DATA "
_CITATION_RULES_TURN_KEY = "citation_rules_injected_for_turn"


def _get_last_human_turn_index(messages: Sequence[object]) -> int:
    """Return the index of the latest HumanMessage, or -1 when absent."""
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], HumanMessage):
            return i
    return -1


def _has_external_sources_in_current_turn(messages: Sequence[object]) -> bool:
    """Check whether current turn contains UNTRUSTED_DATA boundary markers.

    Only scans messages after the last HumanMessage to avoid false positives
    from previous turns.
    """
    last_human_idx = _get_last_human_turn_index(messages)
    if last_human_idx == -1:
        logger.debug("No HumanMessage found when checking for external sources")
        return False

    for msg in messages[last_human_idx + 1 :]:
        if isinstance(msg, ToolMessage):
            content = msg.content
            if isinstance(content, str) and _UNTRUSTED_DATA_MARKER in content:
                return True

    return False


def _should_inject_citation_rules(
    messages: Sequence[object],
    ctx: dict[str, object] | None,
) -> tuple[bool, int]:
    """Return whether to inject full citation rules and the active turn index."""
    turn_idx = _get_last_human_turn_index(messages)
    if turn_idx == -1:
        return False, turn_idx

    if not _has_external_sources_in_current_turn(messages):
        return False, turn_idx

    if ctx is not None and ctx.get(_CITATION_RULES_TURN_KEY) == turn_idx:
        return False, turn_idx

    return True, turn_idx


class CitationRulesMiddleware(AgentMiddleware):  # type: ignore[type-arg]
    """Injects citation formatting rules when external sources exist in the user turn.

    Uses request.override() with HumanMessage (non-persistent, cache-safe).
    """

    name = "citation_rules_middleware"

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        return handler(request)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        ctx: dict[str, object] | None = None
        if request.runtime is not None:
            runtime_ctx = getattr(request.runtime, "context", None)
            if isinstance(runtime_ctx, dict):
                ctx = runtime_ctx
                prompt_mode = runtime_ctx.get("prompt_mode")
                if prompt_mode in ("naked", "search"):
                    return await handler(request)

        state = request.state
        raw_messages = state.get("messages", [])
        messages: list[object] = list(raw_messages) if isinstance(raw_messages, list) else []

        should_inject, turn_idx = _should_inject_citation_rules(messages, ctx)
        if should_inject:
            locale_val = ctx.get("prompt_locale") if ctx is not None else None
            locale = locale_val if isinstance(locale_val, str) else None

            # Fallback to detecting language from the current turn's HumanMessage
            if not locale or not is_chinese(locale):
                if 0 <= turn_idx < len(messages):
                    h_msg = messages[turn_idx]
                    h_content = getattr(h_msg, "content", None)
                    if isinstance(h_content, str) and is_chinese(h_content):
                        locale = "zh-CN"

            citation_content = get_citation_rules_if_needed(True, locale=locale)

            logger.info(
                "Citation rules: turn_idx=%s, has_external_sources=True, will_inject=%s, locale=%s",
                turn_idx,
                citation_content is not None,
                locale,
            )

            if citation_content:
                reminder = (
                    "\n\n【任务完整性提醒】\n你必须同时严格遵循并满足上方用户原始提问中要求的所有特定输出格式、末尾特定标记及约束条件。"
                    if is_chinese(locale)
                    else (
                        "\n\n[TASK INTEGRITY REMINDER]\n"
                        "You must also strictly fulfill all output format instructions, custom endings, "
                        "and specific constraints specified in the original user request above."
                    )
                )
                instruction_text = f"[SYSTEM INSTRUCTION]\n{citation_content}{reminder}"
                new_messages = list(request.messages)
                new_messages.append(HumanMessage(content=instruction_text))
                request = request.override(messages=new_messages)
                if ctx is not None:
                    ctx[_CITATION_RULES_TURN_KEY] = turn_idx

        return await handler(request)


citation_rules_middleware = CitationRulesMiddleware()
