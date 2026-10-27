"""Judge the calls of one model response, once.

[INPUT]
- ..batch_processor::evaluate_tool_batch (POS: Orchestrates allowlist, YOLO and auto mode, path and taint checks, the read-only lease, cron declarations and the LLM security review into one verdict per call.)
- ..intent_ledger::extract_user_intent_ledger (POS: User intent ledger preserving task anchors and directives for reasoning-blind approval classification.)
- ..rate_limiter::get_approval_rate_limiter (POS: Sliding-window rate limiter for approval requests.)
- ..refusal::is_refusal_answer (POS: Tells the answer to a refused call from a tool result.)
- agent.security::audit.record_decision, guards.taint_tracker.get_taint_tracker, types.RecentToolCall (POS: The audit trail, the session taint labels and the compact record of a recent call the reviewer reads.)
- .record, .target

[OUTPUT]
- evaluate_target: the evaluation of the calls of a target, refused, pending and approved calls told apart

[POS]
Everything the approval stage does before it may ask a person: the security verdict of each call, the reviewer
model's opinion, the refusal counters, the approval rate limit. It has side effects, so it runs exactly once per
model response, in its own graph node; the node that asks the person only reads its result.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from langchain_core.messages import AIMessage, BaseMessage, ToolCall

from myrm_agent_harness.agent.middlewares._session_context import get_approval_user_id, get_is_shadow_agent
from myrm_agent_harness.agent.security.audit import record_decision
from myrm_agent_harness.agent.security.guards.taint_tracker import get_taint_tracker
from myrm_agent_harness.agent.security.types import RecentToolCall, SecurityConfig

from ..batch_processor import evaluate_tool_batch
from ..intent_ledger import extract_user_intent_ledger
from ..rate_limiter import get_approval_rate_limiter
from ..refusal import is_refusal_answer
from .record import ApprovalEvaluation, build_evaluation
from .target import ApprovalTarget

logger = logging.getLogger(__name__)

_INTENT_LEDGER_MAX_CHARS = 2500
_RATE_LIMIT_REFUSAL = "Too many approval requests. Rate limit exceeded. Please try again later."

type _Pending = tuple[int, ToolCall, str, str, dict[str, object] | None]
type _Refused = tuple[int, ToolCall, str]


def _recent_tool_calls(messages: Sequence[BaseMessage], config: SecurityConfig) -> tuple[RecentToolCall, ...]:
    """The latest tool calls of the conversation, for the reviewer's cross-tool context (Reasoning-Blind).

    A refused call never ran, so listing it would show the reviewer an action that did not happen. That the model
    keeps trying refused calls is counted by the denial counters, not by this window.
    """
    if not config.auto_mode_enabled:
        return ()
    window_size = config.transcript_window_size
    window = messages[-(window_size * 2) :]
    refused_ids = {message.tool_call_id for message in window if is_refusal_answer(message)}
    calls = [
        RecentToolCall(tool_name=call.get("name", "unknown"), args=call.get("args", {}))
        for message in window
        if isinstance(message, AIMessage)
        for call in message.tool_calls
        if call.get("id") not in refused_ids
    ]
    return tuple(calls[-window_size:])


def _session_taint_labels(config: SecurityConfig) -> frozenset[str] | None:
    """The taint labels of the session, for the classifier; None when auto mode is off or nothing is tainted."""
    if not config.auto_mode_enabled:
        return None
    tracker = get_taint_tracker()
    return frozenset(str(label) for label in tracker.labels) if tracker.is_tainted else None


def _refuse_over_rate_limit(pending: list[_Pending]) -> list[_Refused]:
    """Refuse every call that waits for a person when this user has asked for too many approvals."""
    refused: list[_Refused] = []
    for index, tool_call, _permission_type, _reason, _context in pending:
        refused.append((index, tool_call, _RATE_LIMIT_REFUSAL))
        record_decision(
            tool_call.get("name", "unknown"),
            "DENY",
            "Approval rate limit exceeded",
            tool_call_id=tool_call.get("id", ""),
        )
    return refused


async def evaluate_target(target: ApprovalTarget) -> ApprovalEvaluation:
    """Judge the calls of *target*: which are refused and which wait for a person."""
    config = target.config
    _approved, refused, pending = await evaluate_tool_batch(
        target.unanswered.tool_calls,
        config,
        target.is_cron,
        target.workspace_root,
        target.session_key,
        target.args_hashes,
        intent_context=extract_user_intent_ledger(target.messages, max_chars=_INTENT_LEDGER_MAX_CHARS),
        recent_tool_calls=_recent_tool_calls(target.messages, config),
        taint_labels=_session_taint_labels(config),
        is_interactive=not target.is_cron and not get_is_shadow_agent(),
    )

    user_id = get_approval_user_id()
    if pending and user_id and not get_approval_rate_limiter().check_limit(user_id):
        logger.warning("[RATE_LIMIT] Approval rate limit exceeded for user %s", user_id)
        refused = [*refused, *_refuse_over_rate_limit(pending)]
        pending = []

    return build_evaluation(target.source.id, refused, pending)
