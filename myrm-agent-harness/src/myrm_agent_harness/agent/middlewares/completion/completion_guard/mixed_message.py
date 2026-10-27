"""Mixed Message Guard: a finished answer that still carries read-only tool calls ends the turn at once.

When a model outputs both a substantive final response and read-only tool calls in the same message, the calls only
cost tool rounds and an extra model call. They are stripped so the agent terminates. A call is kept when it is
effectful (``is_mutating_tool``) or carries an interaction/UI function (``INTERACTION_UI_TOOLS``): dropping either
would lose a user-visible side effect or break the interaction chain. When the user request demands external evidence
(freshness/citation), or the answer claims what this run's records do not support, the calls are kept too, so the
agent gathers real data instead of letting unverified content reach the user.

[INPUT]
- agent.middlewares.completion.completion_guard.external_evidence::build_external_evidence_reason (POS: whether the request needs outside evidence this run lacks)
- agent.middlewares.completion.completion_guard.safety::INTERACTION_UI_TOOLS, is_mutating_tool, is_substantive_final_response (POS: which calls must be kept and whether the content is a finished answer)
- agent.middlewares.completion.execution_claim_verifier::check_execution_claim (POS: completion-claim grounding against this run's tool records)
- agent.middlewares.completion.query_grounding_verifier::check_query_grounding_claim (POS: entity query grounding)
- agent.security.guards.loop_guard::CallRecord (POS: one recorded tool call)

[OUTPUT]
- strip_readonly_calls_beside_answer(): the state update that replaces the message with a copy without tool calls, or None

[POS]
The early-termination half of CompletionGuard: it runs when the message is not a completion attempt but already holds
a complete answer.
"""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any

from langchain_core.messages import AIMessage

from myrm_agent_harness.agent.middlewares.completion.completion_guard.external_evidence import (
    build_external_evidence_reason,
)
from myrm_agent_harness.agent.middlewares.completion.completion_guard.safety import (
    INTERACTION_UI_TOOLS,
    is_mutating_tool,
    is_substantive_final_response,
)
from myrm_agent_harness.agent.middlewares.completion.execution_claim_verifier import check_execution_claim
from myrm_agent_harness.agent.middlewares.completion.query_grounding_verifier import check_query_grounding_claim
from myrm_agent_harness.agent.security.guards.loop_guard import CallRecord

logger = logging.getLogger(__name__)


def strip_readonly_calls_beside_answer(
    message: AIMessage,
    *,
    messages: list[object],
    records: list[CallRecord],
    user_text: str | None,
) -> dict[str, Any] | None:
    """Replace ``message`` with a copy that has no tool calls when it already is a complete answer."""
    if not (message.content and message.tool_calls):
        return None
    content = message.content if isinstance(message.content, str) else str(message.content)
    if not is_substantive_final_response(content):
        return None
    has_non_strippable = any(
        is_mutating_tool(str(tc.get("name", ""))) or str(tc.get("name", "")) in INTERACTION_UI_TOOLS
        for tc in message.tool_calls
        if isinstance(tc, dict)
    )
    if has_non_strippable:
        return None
    # 防假完成：用户请求外部/新鲜数据但会话中尚无成功证据时，
    # 保留只读工具调用让 Agent 真正获取数据，避免未核实内容直接到达用户。
    requires_evidence = build_external_evidence_reason(messages=messages, records=records) is not None
    query_grounding_reason = check_query_grounding_claim(user_text=user_text, assistant_text=content, records=records)
    execution_claim_reason = check_execution_claim(user_text=user_text, assistant_text=content, records=records)
    if requires_evidence or query_grounding_reason is not None or execution_claim_reason is not None:
        return None
    logger.info(
        "[CompletionGuard] Mixed message detected: content is substantive "
        "final response with %d read-only tool_calls — stripping to terminate early.",
        len(message.tool_calls),
    )
    patched = deepcopy(message)
    patched.tool_calls = []
    return {"messages": [patched]}


__all__ = ["strip_readonly_calls_beside_answer"]
