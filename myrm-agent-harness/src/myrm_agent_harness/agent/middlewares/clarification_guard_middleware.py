"""Clarification guard — enforces ask_question_tool single-call semantics.

When the model emits ``ask_question_tool`` in a turn:
- Only the first call runs (batch all questions in one call).
- Every other tool call in the same turn stays in the AI message and is answered by an error ToolMessage, so the
  model reads why it did not run.

[INPUT]
- langchain_core.messages::AIMessage, ToolMessage (POS: LangGraph message types)

[OUTPUT]
- ClarificationGuardMiddleware: after_model guard for ask_question_tool batching rules
- ASK_QUESTION_TOOL_NAME: canonical tool name constant

[POS]
Pre-execution guard aligned with Hermes ``NEVER_PARALLEL`` clarify semantics.
Runs before ToolApprovalMiddleware, which skips a call that already has an answer, so blocked tools never reach
approval/HITL.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, ToolMessage

logger = logging.getLogger(__name__)

ASK_QUESTION_TOOL_NAME = "ask_question_tool"

_DUPLICATE_ERROR = (
    "Error: ask_question_tool allows only one call per turn. "
    "Put every clarifying question in the `questions` array of a single tool call."
)

_COEXISTENCE_ERROR = (
    "Error: ask_question_tool must be the only tool in this turn. "
    "Run other tools after the user answers the clarification."
)


class ClarificationGuardMiddleware(AgentMiddleware[Any, Any, Any]):
    """Strip invalid ask_question_tool batching before tool execution."""

    async def aafter_model(self, state: dict[str, Any], runtime: Any) -> dict[str, Any] | None:
        messages = state.get("messages", [])
        if not messages:
            return None

        last_ai_msg = next((msg for msg in reversed(messages) if isinstance(msg, AIMessage)), None)
        if last_ai_msg is None or not last_ai_msg.tool_calls:
            return None

        ask_indices = [
            idx
            for idx, tool_call in enumerate(last_ai_msg.tool_calls)
            if tool_call.get("name") == ASK_QUESTION_TOOL_NAME
        ]
        if not ask_indices:
            return None

        primary_index = ask_indices[0]
        artificial_tool_messages: list[ToolMessage] = []

        for idx, tool_call in enumerate(last_ai_msg.tool_calls):
            tool_name = tool_call.get("name", "unknown")
            tool_call_id = tool_call.get("id", "")

            if idx == primary_index:
                continue

            if tool_name == ASK_QUESTION_TOOL_NAME:
                error_content = _DUPLICATE_ERROR
            else:
                error_content = _COEXISTENCE_ERROR

            artificial_tool_messages.append(
                ToolMessage(
                    content=error_content,
                    name=tool_name,
                    tool_call_id=tool_call_id,
                    status="error",
                )
            )

            from myrm_agent_harness.agent.security.audit import record_decision

            record_decision(
                tool_name,
                "CLARIFICATION_GUARD_BLOCKED",
                "Duplicate or coexisting ask_question_tool call blocked",
            )

        if not artificial_tool_messages:
            return None

        logger.info(
            "ClarificationGuard: kept 1 ask_question_tool call, blocked %d other tool call(s)",
            len(artificial_tool_messages),
        )
        return {"messages": artificial_tool_messages}


__all__ = [
    "ASK_QUESTION_TOOL_NAME",
    "ClarificationGuardMiddleware",
]
