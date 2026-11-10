"""Goal focus middleware — inject active goal objective into the user's latest message.

[INPUT]
- agent.goals.goal_prompt_prefixes::GOAL_CONTINUATION_PREFIX, GOAL_WRAPUP_PREFIX (POS: skip-detection SSOT)
- agent.goals.types::Goal, GoalStatus (POS: ACTIVE gate + focus line fields)
- agent.middlewares._session_context::get_goal_provider (POS: per-run GoalProvider ContextVar)
- core.message_origin::last_user_authored_index, runtime_human_message (POS: Message-provenance primitives shared by the approval, security, memory-context and context-management layers.)
- core.message_tail::append_block_to_last_user_message (POS: Tail-of-turn injection primitive.)
- langchain.agents.middleware::ModelRequest, wrap_model_call (POS: LC middleware)

[OUTPUT]
- goal_focus_middleware: Non-persistent active-goal reminder on user-initiated turns

[POS]
Cache-safe injection for ACTIVE goals on user-initiated turns: the line sits on the user's own message, so a notice
the runtime appends behind it neither takes the line nor moves it between the requests of a run. The goal's usage
counters are settled when a run ends, so the line is the same on every request of one run. Skips turns that already
carry continuation or wrap-up goal prompts.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from langchain.agents.middleware import ModelRequest, ModelResponse, wrap_model_call
from langchain_core.messages import AnyMessage, HumanMessage

from myrm_agent_harness.agent.goals.goal_prompt_prefixes import (
    GOAL_CONTINUATION_PREFIX,
    GOAL_WRAPUP_PREFIX,
)
from myrm_agent_harness.agent.goals.types import Goal, GoalStatus
from myrm_agent_harness.agent.middlewares._session_context import get_goal_provider
from myrm_agent_harness.core.message_origin import last_user_authored_index, runtime_human_message
from myrm_agent_harness.core.message_tail import append_block_to_last_user_message

logger = logging.getLogger(__name__)

_MAX_OBJECTIVE_CHARS = 200


def _truncate_objective(objective: str) -> str:
    text = " ".join(objective.split())
    if len(text) <= _MAX_OBJECTIVE_CHARS:
        return text
    return f"{text[: _MAX_OBJECTIVE_CHARS - 1].rstrip()}…"


def _format_budget_hint(goal: Goal) -> str:
    if goal.budget is None:
        return f"tokens used: {goal.tokens_used}"
    parts: list[str] = []
    if goal.budget.max_tokens is not None:
        parts.append(f"tokens {goal.tokens_used}/{goal.budget.max_tokens}")
    elif goal.tokens_used:
        parts.append(f"tokens used: {goal.tokens_used}")
    if goal.budget.max_turns is not None:
        parts.append(f"turns {goal.turns_used}/{goal.budget.max_turns}")
    return ", ".join(parts) if parts else "no budget limits"


def _build_goal_focus_line(goal: Goal) -> str:
    objective = _truncate_objective(goal.objective)
    budget_hint = _format_budget_hint(goal)
    return (
        f"Active goal: {objective} ({budget_hint}) — "
        "advance it; completion is detected by the judge, or call complete_goal_tool when fully done."
    )


def _has_goal_continuation_prompt(messages: list[object]) -> bool:
    for msg in messages:
        if not isinstance(msg, HumanMessage):
            continue
        content = msg.content
        if isinstance(content, str):
            if content.startswith(GOAL_CONTINUATION_PREFIX) or content.startswith(GOAL_WRAPUP_PREFIX):
                return True
        elif isinstance(content, list):
            joined = " ".join(
                block.get("text", "") for block in content if isinstance(block, dict) and block.get("type") == "text"
            )
            if joined.startswith(GOAL_CONTINUATION_PREFIX) or joined.startswith(GOAL_WRAPUP_PREFIX):
                return True
    return False


def _with_goal_focus(messages: Sequence[AnyMessage], injection_text: str) -> list[AnyMessage]:
    """``messages`` with the focus line on the user's latest message, or behind them all when the user wrote none."""
    if last_user_authored_index(messages) == -1:
        return [*messages, runtime_human_message(injection_text)]
    return append_block_to_last_user_message(messages, injection_text)


def goal_focus_middleware() -> Any:
    """Inject active goal focus into the user's last message (non-persistent)."""

    @wrap_model_call(name="goal_focus_middleware")
    async def _middleware(
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        if _has_goal_continuation_prompt(list(request.messages)):
            return await handler(request)

        goal_provider = get_goal_provider()
        if goal_provider is None:
            return await handler(request)

        context = getattr(request.runtime, "context", None) if hasattr(request, "runtime") and request.runtime else None
        if not isinstance(context, dict):
            return await handler(request)

        session_id = str(context.get("chat_id") or context.get("session_id") or "")
        if not session_id:
            return await handler(request)

        try:
            goal = await goal_provider.get_active_goal(session_id)
        except Exception as exc:
            logger.warning("goal_focus_middleware: failed to load active goal: %s", exc)
            return await handler(request)

        if goal is None or goal.status != GoalStatus.ACTIVE:
            return await handler(request)

        injection_text = _build_goal_focus_line(goal)
        return await handler(request.override(messages=_with_goal_focus(request.messages, injection_text)))

    return _middleware


__all__ = [
    "_build_goal_focus_line",
    "_has_goal_continuation_prompt",
    "goal_focus_middleware",
]
