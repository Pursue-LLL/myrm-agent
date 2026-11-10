"""Citation rules middleware for GeneralAgent.

Shows the citation formatting rules as a transient runtime HumanMessage (via request.override) once the current
turn holds UNTRUSTED external sources. Uses a HumanMessage to preserve SystemMessage hash stability for prompt caching.

The notice is a pure function of the history: it stands right behind the tool results that first brought a source
into the turn, on that request and on every later one. A request therefore always extends the one before it, which
keeps the provider's cached prefix and the reasoning blocks written under it valid for the rest of the run.
"""

import logging
from collections.abc import Awaitable, Callable, Sequence

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import BaseMessage, ToolMessage
from myrm_agent_harness.api import last_user_authored_index, runtime_human_message
from myrm_agent_harness.utils.locale import is_chinese

from app.ai_agents.prompts.general_agent_prompt import get_citation_rules_if_needed

logger = logging.getLogger(__name__)

_UNTRUSTED_DATA_MARKER = "<<<UNTRUSTED_DATA "
_SKIPPED_PROMPT_MODES = ("naked", "search")

_REMINDER_ZH = (
    "\n\n【任务完整性提醒】\n你必须同时严格遵循并满足上方用户原始提问中要求的所有特定输出格式、末尾特定标记及约束条件。"
)
_REMINDER_EN = (
    "\n\n[TASK INTEGRITY REMINDER]\n"
    "You must also strictly fulfill all output format instructions, custom endings, "
    "and specific constraints specified in the original user request above."
)


def _end_of_first_source_group(messages: Sequence[BaseMessage]) -> int:
    """Index of the last tool result of the group that first brought an external source into the current turn.

    Only the messages behind the user's latest one are scanned, so sources of earlier turns never trigger the
    rules. A group is the run of tool results one assistant message asked for; the notice may only follow all of
    them, since a message between two results of one call is rejected by the providers. Returns -1 when there is no
    turn or the turn holds no source.
    """
    turn_start = last_user_authored_index(messages)
    if turn_start == -1:
        return -1
    for i in range(turn_start + 1, len(messages)):
        message = messages[i]
        if isinstance(message, ToolMessage) and isinstance(message.content, str) and _UNTRUSTED_DATA_MARKER in message.content:
            end = i
            while end + 1 < len(messages) and isinstance(messages[end + 1], ToolMessage):
                end += 1
            return end
    return -1


def _rules_notice(prompt_locale: object) -> str | None:
    """The citation rules in the language of the run, with the reminder that the user's own format rules still hold."""
    locale = prompt_locale if isinstance(prompt_locale, str) else None
    rules = get_citation_rules_if_needed(True, locale=locale)
    if not rules:
        return None
    return f"[SYSTEM INSTRUCTION]\n{rules}{_REMINDER_ZH if is_chinese(locale) else _REMINDER_EN}"


class CitationRulesMiddleware(AgentMiddleware):
    """Shows citation formatting rules when external sources exist in the user turn.

    Uses request.override() with a runtime-written HumanMessage (non-persistent, cache-safe).
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
        run_context = getattr(request.runtime, "context", None) if request.runtime is not None else None
        ctx: dict[str, object] = run_context if isinstance(run_context, dict) else {}
        if ctx.get("prompt_mode") in _SKIPPED_PROMPT_MODES:
            return await handler(request)

        group_end = _end_of_first_source_group(request.messages)
        if group_end == -1:
            return await handler(request)
        notice = _rules_notice(ctx.get("prompt_locale"))
        if notice is None:
            return await handler(request)

        logger.debug("Citation rules placed behind message %d of %d", group_end, len(request.messages))
        messages = list(request.messages)
        messages.insert(group_end + 1, runtime_human_message(notice))
        return await handler(request.override(messages=messages))


citation_rules_middleware = CitationRulesMiddleware()
