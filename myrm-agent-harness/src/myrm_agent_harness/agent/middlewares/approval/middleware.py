"""Tool approval middleware — asks the person about the tool calls that require confirmation.

Uses ``after_model`` hook to intercept AIMessage with tool_calls *before* execution. Two graph nodes share the work:

1. ``ApprovalEvaluationMiddleware`` (``evaluation/``) judges the calls once: ALLOW / ASK / DENY per call, the reviewer
   model, the refusal counters, the approval rate limit. Its verdicts are stored in the graph state.
2. This middleware reads those verdicts. ALLOW needs nothing more. DENY answers the call with an error ToolMessage.
   ASK goes to the person: allowlist → cron policy (cron sessions) → skill hooks → domain HITL runtime check → one
   batch interrupt().

The split exists because LangGraph resumes an interrupted node by running it again from its first line: whatever this
node does before ``interrupt()`` is repeated once the person has answered. Judging a call has side effects (a reviewer
model call, refusal counters), so it happens in the node before; this node only reads.

Batch approval: When multiple tools require approval in a single turn, all are
collected and presented in one interrupt() call. Users decide for all tools at once.

Domain HITL: When ``domain_hitl_enabled`` is True, URL-bearing tools (web_fetch,
browser_navigate) whose hostname is not in ``network_allowlist`` trigger ASK.
Users can approve per-request or "always allow this domain" (session-scoped).

Cron sessions (session_key starts with "cron:") have nobody to answer an ASK, so
``_cron_policy.resolve_cron_ask`` settles it: the declared capability set acts as
pre-approval, except for credential egress, out-of-zone paths and integration writes.
An undeclared capability set is denied fail-closed.

Uses LangGraph's native ``interrupt()`` mechanism for Human-in-the-Loop:
- First call: interrupt() raises GraphInterrupt, stream ends
- Resume: interrupt() returns resume_value (user decisions list), execution continues

Every decision is recorded via security.audit.record_decision() for post-hoc auditing.

[INPUT]
- approval.evaluation::APPROVAL_EVALUATION_KEY, evaluate_target, evaluation_matches, pending_calls, refused_calls, resolve_approval_target (POS: The verdicts the evaluation node stored for the latest model response, and the target they are about.)
- approval.refusal::DenialCause, kept_tool_calls, refusal_answer (POS: Which calls the AI message keeps once some were approved, edited or refused, and the marked answer to a refused call.)
- middlewares._session_context::get_is_shadow_agent, get_is_subagent, get_subagent_task_id (POS: Middleware session context — shared ContextVars for the middleware chain.)
- security.session_access::drop_once_grants (POS: Closes the files an approved call opened for itself when the next model response arrives.)
- langgraph.types::interrupt (POS: Pauses the node until the person answers.)

[OUTPUT]
- ToolApprovalMiddleware: after_model middleware that puts the pending calls to the person and applies the answers

[POS]
Bridges the Permission Engine with the LangGraph tool pipeline. Runs right after ``ApprovalEvaluationMiddleware``.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, ToolCall
from langgraph.types import interrupt

from myrm_agent_harness.agent.middlewares._session_context import (
    get_is_shadow_agent,
    get_is_subagent,
)
from myrm_agent_harness.agent.security.session_access import drop_once_grants

from .batch_processor import (
    apply_approval_decisions,
    build_interrupt_payload,
)
from .evaluation import (
    APPROVAL_EVALUATION_KEY,
    evaluate_target,
    evaluation_matches,
    pending_calls,
    refused_calls,
    resolve_approval_target,
)
from .helpers import reset_denial_counter
from .refusal import DenialCause, kept_tool_calls, refusal_answer

logger = logging.getLogger(__name__)


class ToolApprovalMiddleware(AgentMiddleware[Any, Any, Any]):
    """Tool approval middleware using after_model hook for batch approval."""

    async def aafter_model(self, state: dict[str, Any], runtime: Any) -> dict[str, Any] | None:
        """Put the calls the evaluation left pending to the person, then apply the answers.

        Orchestrates batch approval flow: read verdicts → interrupt → apply decisions. This node is run again from
        its first line when the person has answered, so everything before ``interrupt()`` only reads.
        """
        # A new model response has arrived: the files an earlier approval opened for its one call close again.
        drop_once_grants()
        stored = state.get(APPROVAL_EVALUATION_KEY)
        # The verdicts are spent once this node finishes; they must not linger in every later checkpoint.
        spent: dict[str, Any] = {APPROVAL_EVALUATION_KEY: None} if stored is not None else {}

        target = resolve_approval_target(state, runtime)
        if target is None:
            return spent or None

        config = target.config
        session_key = target.session_key
        workspace_root = target.workspace_root
        last_ai_msg = target.unanswered
        source_msg = target.source

        evaluation = stored if evaluation_matches(stored, source_msg.id) else None
        if evaluation is None:
            logger.warning(
                "[APPROVAL] No stored evaluation for this model response; judging it here, "
                "which an approval pause would repeat (session=%s)",
                session_key,
            )
            evaluation = await evaluate_target(target)
        auto_denied = refused_calls(evaluation)
        pending_approval = pending_calls(evaluation)

        if not pending_approval:
            if auto_denied:
                refusals = sorted(auto_denied, key=lambda denied: denied[0])
                return {
                    **spent,
                    "messages": [
                        refusal_answer(tool_call, content, DenialCause.POLICY) for _, tool_call, content in refusals
                    ],
                }
            return spent or None

        # We use LangGraph's native interrupt() mechanism for ALL agents, including subagents.
        # Subagents must have a checkpointer configured for this to work.
        # The executor catches the GraphInterrupt and delegates it to the parent agent.

        payload, interrupt_indices = build_interrupt_payload(
            pending_approval,
            session_key,
            approval_timeout_seconds=config.approval_timeout_seconds,
            timeout_behavior=config.approval_timeout_behavior,
            workspace_root=workspace_root,
            path_policy=config.path_policy,
        )

        # Determine the action type based on agent context
        action_type = "subagent_approval" if get_is_subagent() else "tool_approval"

        # Inject action_type and subagent_task_id into payload so the UI knows how to render it
        # and the server knows how to route the approval resolution.
        if get_is_subagent():
            from myrm_agent_harness.agent.middlewares._session_context import (
                get_subagent_task_id,
            )

            task_id = get_subagent_task_id()
            if not task_id:
                logger.warning("Subagent context active but no task_id found. Falling back to auto-deny.")
                return {**spent, **self._fallback_auto_deny(last_ai_msg, pending_approval, auto_denied, session_key)}
            payload["action_type"] = action_type
            payload["subagent_task_id"] = task_id

        # Shadow agents have no UI channel — auto-deny to prevent deadlocks.
        if get_is_shadow_agent():
            logger.warning(
                "[SHADOW_AGENT_APPROVAL_BLOCKED] Shadow agent attempted high-risk operation "
                "requiring user approval — auto-denying. session_key=%s",
                session_key,
            )
            return {**spent, **self._fallback_auto_deny(last_ai_msg, pending_approval, auto_denied, session_key)}

        batch_response = interrupt(payload)
        decisions = self._normalize_batch_decisions(
            batch_response,
            expected_count=len(pending_approval),
            phase="primary",
        )

        logger.info(
            "[BATCH_APPROVAL] Batch interrupt resolved with %d decisions",
            len(decisions),
        )

        revised_tool_calls, artificial_tool_messages, guidance_messages = await apply_approval_decisions(
            decisions,
            last_ai_msg,
            auto_denied,
            pending_approval,
            interrupt_indices,
            target.args_hashes,
            config=config,
        )

        # Fire APPROVAL_CORRECTION hook for edit decisions so user-defined hooks can react
        await self._fire_correction_hook(decisions, pending_approval, session_key)

        answered_ids = set(target.answered_ids) | {message.tool_call_id for message in artificial_tool_messages}
        source_msg.tool_calls = kept_tool_calls(source_msg.tool_calls, revised_tool_calls, answered_ids)
        return {**spent, "messages": [source_msg, *artificial_tool_messages, *guidance_messages]}

    @staticmethod
    def _normalize_batch_decisions(
        batch_response: object,
        *,
        expected_count: int,
        phase: str,
    ) -> list[dict[str, object]]:
        if not isinstance(batch_response, dict):
            logger.error(
                "[BATCH_APPROVAL] (%s) Invalid batch response type: %s",
                phase,
                type(batch_response),
            )
            return [{"type": "reject", "feedback": "Invalid batch response"} for _ in range(expected_count)]

        if "decision" in batch_response and "decisions" not in batch_response:
            global_decision = batch_response["decision"]
            global_feedback = batch_response.get("feedback")
            timed_out = bool(batch_response.get("timed_out"))
            normalized = [
                {"type": global_decision, "feedback": global_feedback, "timed_out": timed_out}
                for _ in range(expected_count)
            ]
        else:
            raw = batch_response.get("decisions", [])
            normalized = raw if isinstance(raw, list) else []

        if len(normalized) != expected_count:
            logger.error(
                "[BATCH_APPROVAL] (%s) Decision count mismatch: expected %d, got %d",
                phase,
                expected_count,
                len(normalized),
            )
            return [{"type": "reject", "feedback": "Decision count mismatch"} for _ in range(expected_count)]
        return normalized

    @staticmethod
    async def _fire_correction_hook(
        decisions: list[dict[str, Any]],
        pending_approval: Sequence[tuple[int, ToolCall, str, str, Mapping[str, object] | None]],
        session_key: str,
    ) -> None:
        """Fire APPROVAL_CORRECTION hook for decisions where the user edited tool arguments.

        A rejection carries no corrected value and is not reported; it stays visible
        through the audit trail. No built-in handler is registered: the event is an
        extension point for user-defined hooks.
        """
        corrections: list[dict[str, object]] = []

        for i, decision in enumerate(decisions):
            if i >= len(pending_approval):
                break
            edited_args = decision.get("args")
            if decision.get("type") != "edit" or not isinstance(edited_args, dict):
                continue

            _idx, tool_call, *_ = pending_approval[i]
            original_args = tool_call.get("args")
            corrections.append(
                {
                    "tool_name": tool_call.get("name", "unknown"),
                    "original_args": dict(original_args) if isinstance(original_args, dict) else {},
                    "edited_args": dict(edited_args),
                }
            )

        if not corrections:
            return

        try:
            from myrm_agent_harness.agent.hooks import fire_hook
            from myrm_agent_harness.core.hooks.types import HookEvent

            await fire_hook(
                HookEvent.APPROVAL_CORRECTION,
                {"session_id": session_key, "corrections": tuple(corrections)},
            )
        except Exception as e:
            logger.warning("[APPROVAL] Failed to fire correction hook: %s", e)

    def _fallback_auto_deny(
        self,
        last_ai_msg: AIMessage,
        pending_approval: Sequence[tuple[int, ToolCall, str, str, Mapping[str, object] | None]],
        auto_denied: Sequence[tuple[int, ToolCall, str]],
        session_key: str,
    ) -> dict[str, Any]:
        """Auto-deny tools when task_id is missing to prevent deadlock."""
        logger.warning(
            "[SUBAGENT_APPROVAL_BLOCKED] Autonomous subagent attempted high-risk operation "
            "requiring user approval — auto-denying to prevent deadlock. "
            f"session_key={session_key}, pending_tools={[tc.get('name') for _, tc, _, _, _ in pending_approval]}"
        )

        try:
            from myrm_agent_harness.observability.metrics.registry import (
                metrics_registry,
            )

            if metrics_registry and metrics_registry.enabled:
                for _, tool_call, _, _, _ in pending_approval:
                    metrics_registry.record_approval_denied(
                        agent_id="base_agent",
                        tool_name=tool_call.get("name", "unknown"),
                        reason="subagent_auto_deny",
                    )
        except ImportError:
            pass

        artificial_tool_messages = []

        for idx, tool_call in enumerate(last_ai_msg.tool_calls):
            if not any(p_idx == idx for p_idx, _, _, _, _ in pending_approval):
                continue

            artificial_tool_messages.append(
                refusal_answer(
                    tool_call,
                    "[SYSTEM_ENFORCED] High-risk operations requiring user UI approval "
                    "are strictly forbidden for autonomous Subagents when task_id is missing. "
                    "This safeguard prevents deadlocks since Subagents have no frontend channel. "
                    "Please use a safe alternative or delegate this operation to the parent agent.",
                    DenialCause.POLICY,
                )
            )

            from myrm_agent_harness.agent.security.audit import record_decision

            record_decision(
                tool_call.get("name", "unknown"),
                "SUBAGENT_AUTO_DENY",
                "Autonomous subagent blocked from triggering UI approval flow (missing task_id)",
                tool_call_id=tool_call.get("id", ""),
            )

        artificial_tool_messages.extend(
            refusal_answer(tool_call, content, DenialCause.POLICY) for _, tool_call, content in auto_denied
        )
        return {"messages": artificial_tool_messages}


__all__ = [
    "ToolApprovalMiddleware",
    "reset_denial_counter",
]
