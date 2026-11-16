"""Answer the asks that wait for a person when no person can answer.

[INPUT]
- ._cron_policy::resolve_cron_ask (POS: The verdict on one ask from the capabilities the job declared.)
- .helpers::record_approval, record_denial (POS: The refusal counters and the wording of a refusal.)
- agent.security::audit.record_decision (POS: The audit trail.)

[OUTPUT]
- settle_ask: None when the job's declaration approves one ask, else the refusal the model reads
- settle_pending: the calls that would otherwise wait for a person, split into approved and refused

[POS]
A run with no approver (a scheduled job, and every agent it delegates to) cannot be paused for an answer: nothing
resumes it, so the job would end half done. The job's declared capabilities answer instead, whether the ask comes
from the job's own agent, a delegated agent, a workflow node, or a branch that lets no ask through on its own.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from langchain_core.messages import ToolCall

from myrm_agent_harness.agent.security.audit import record_decision
from myrm_agent_harness.agent.security.types import SecurityConfig

from ._cron_policy import resolve_cron_ask
from .helpers import record_approval, record_denial

logger = logging.getLogger(__name__)

type _Pending = tuple[int, ToolCall, str, str, dict[str, object] | None]
type _Approved = tuple[int, ToolCall]
type _Refused = tuple[int, ToolCall, str]


def settle_ask(
    *,
    permission_type: str,
    tool_name: str,
    tool_input: dict[str, object],
    config: SecurityConfig,
    workspace_root: str | None,
    session_key: str,
) -> str | None:
    """None when the job's declaration approves the call; otherwise the refusal text for the model."""
    verdict = resolve_cron_ask(
        permission_type=permission_type,
        tool_name=tool_name,
        tool_input=tool_input,
        config=config,
        workspace_root=workspace_root,
    )
    if verdict.denied:
        logger.warning("[CRON_POLICY] Tool %s DENIED in session %s: %s", tool_name, session_key, verdict.audit_reason)
        record_decision(tool_name, "CRON_DENY", verdict.audit_reason)
        return f"{verdict.tool_message}{record_denial(tool_name, session_key)}"
    logger.info(
        "[CRON_POLICY] Tool %s ASK promoted to ALLOW in session %s: declared capabilities act as pre-approval",
        tool_name,
        session_key,
    )
    record_decision(tool_name, "ALLOW", verdict.audit_reason)
    record_approval(session_key)
    return None


def settle_pending(
    pending: Sequence[_Pending],
    *,
    config: SecurityConfig,
    workspace_root: str | None,
    session_key: str,
) -> tuple[list[_Approved], list[_Refused]]:
    """Split *pending* into the calls the job's declaration approves and the calls it refuses."""
    approved: list[_Approved] = []
    refused: list[_Refused] = []
    for index, call, permission_type, _reason, _context in pending:
        refusal = settle_ask(
            permission_type=permission_type,
            tool_name=call.get("name", "unknown"),
            tool_input=call.get("args", {}),
            config=config,
            workspace_root=workspace_root,
            session_key=session_key,
        )
        if refusal is None:
            approved.append((index, call))
        else:
            refused.append((index, call, refusal))
    return approved, refused
