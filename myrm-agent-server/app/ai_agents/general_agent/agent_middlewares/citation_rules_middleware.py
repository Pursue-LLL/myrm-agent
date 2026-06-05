"""Citation rules middleware for GeneralAgent.

Appends citation formatting rules as a transient HumanMessage (via request.override)
during the final_answer phase when external sources are present in the current turn.
Uses HumanMessage to preserve SystemMessage hash stability for prompt caching.
"""

import logging
from collections.abc import Awaitable, Callable, Sequence

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import HumanMessage, ToolMessage

from app.ai_agents.prompts.general_agent_prompt import get_citation_rules_if_needed

logger = logging.getLogger(__name__)


def _is_final_answer_phase(messages: Sequence[object]) -> bool:
    """Return True if the last message is a request_answer_user_tool result."""
    if messages:
        last_message = messages[-1]
        if isinstance(last_message, ToolMessage) and last_message.name == "request_answer_user_tool":
            return True
    return False


_UNTRUSTED_DATA_MARKER = "<<<UNTRUSTED_DATA "


def _has_external_sources_in_current_turn(messages: Sequence[object]) -> bool:
    """Check whether current turn contains UNTRUSTED_DATA boundary markers.

    Only scans messages after the last HumanMessage to avoid false positives
    from previous turns.
    """
    last_human_idx = -1
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], HumanMessage):
            last_human_idx = i
            break

    if last_human_idx == -1:
        logger.debug("No HumanMessage found when checking for external sources")
        return False

    for msg in messages[last_human_idx + 1 :]:
        if isinstance(msg, ToolMessage):
            content = msg.content
            if isinstance(content, str) and _UNTRUSTED_DATA_MARKER in content:
                return True

    return False


class CitationRulesMiddleware(AgentMiddleware):  # type: ignore[type-arg]
    """Injects citation formatting rules during the final_answer phase.

    Uses request.override() with HumanMessage (non-persistent, cache-safe).
    """

    name = "citation_rules_middleware"

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        raise NotImplementedError("CitationRulesMiddleware does not support synchronous wrap_model_call")

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        # naked/lean 模式下跳过引用规则注入
        if request.runtime is not None:
            ctx = getattr(request.runtime, "context", None)
            if isinstance(ctx, dict) and ctx.get("prompt_mode") in ("naked", "lean", "search"):
                return await handler(request)

        state = request.state
        raw_messages = state.get("messages", [])
        messages: list[object] = list(raw_messages) if isinstance(raw_messages, list) else []

        if _is_final_answer_phase(messages):
            has_sources = _has_external_sources_in_current_turn(messages)
            citation_content = get_citation_rules_if_needed(has_sources)

            logger.info(
                "Citation rules: final_answer phase, has_external_sources=%s, will_inject=%s",
                has_sources,
                citation_content is not None,
            )

            if citation_content:
                new_messages = list(request.messages)
                new_messages.append(HumanMessage(content=f"[SYSTEM INSTRUCTION]\n{citation_content}"))
                request = request.override(messages=new_messages)

        return await handler(request)


citation_rules_middleware = CitationRulesMiddleware()
