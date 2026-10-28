"""Completion verification guard middleware.

Intercepts the Agent's final answer attempt and holds it back when the run's tool records do not support it,
up to max_rejections before a forced finish.

Task-type-aware strictness:
  - **Work that wrote files**: CRITICAL when code was written and nothing after the last such write proved it
    (tests, lint, type-check), when a verification category's latest run failed, or when a failure after the
    last write still stands (see ``checklist``).
  - **Freshness-sensitive query tasks**: when user asks for latest/current data
    but no successful web/search/browser evidence exists, block completion and
    request evidence collection before finishing.
  - **Other query/non-code tasks**: no intervention — the Agent finishes immediately.

Temporal ordering enforcement: when code is modified AFTER the last successful
verification and that is the only thing wrong, the guard independently re-runs the verification command in the
sandbox before allowing completion — zero LLM cost, no agent trust required. A re-run answers nothing else
(never verified, failed or empty verification, a failure that still stands, an unfinished todo, an unsupported claim).

Every check reads the turn's call ledger (``state.record_evidence``), not the loop guard's window of the last calls:
an answer is judged against everything the turn did, so a long run neither loses the code it never verified nor
the evidence it gathered early.

A message that is not a completion attempt but already holds a finished answer next to read-only tool calls goes to
the Mixed Message Guard (``mixed_message``).

Internal tools (``_``-prefixed names) are no part of the run's work and are left out of every check.

A held-back answer is never turned into a tool call: the guard routes the run back to the model
(``jump_to="model"``) and records the instruction in the turn's guard state; ``CompletionDirectiveMiddleware``
appends it to the next model request only. Nothing the guard says to the model is stored in the conversation, shown
as a task step, approved, counted by the loop guard or scanned as tool output. What happens to the draft itself is
decided by ``hold_back``.

A demand is made only of a run that could meet it (``CompletionCapabilities``): a deliverable code block is held to
being saved (and staged into the workspace on a forced finish) only when the run can save a file, an unfinished
todo blocks only a run that keeps a todo list, and a freshness question is held to external evidence only when the
run holds a tool that can produce it. A run that holds none is asked once to say plainly it could not check, and
the answer then passes: no further attempt could change what it holds.

State lives in the per-turn registry of ``state`` (keyed by the bound message id), not in a ContextVar, because
LangGraph executes nodes in copied contexts, which prevents ContextVar state from persisting across ReAct cycles.

[INPUT]
- langchain.agents.middleware::AgentMiddleware, hook_config (POS: LangChain middleware base and the declaration that a hook may route back to the model)
- agent.middlewares.tooling.tool_interceptor_middleware::get_loop_guard (POS: LoopGuard accessor)
- agent.middlewares.completion.completion_guard.checklist::assess_checklist, CriticalCause, VERIFICATION_CAUSES, find_last_successful_verification_command (POS: task-aware verification checklist and the causes that hold an answer back)
- agent.middlewares.completion.completion_guard.directive::BlockReasons (POS: why one completion attempt was held back)
- agent.middlewares.completion.completion_guard.hold_back::hold_back (POS: what happens to the draft and where the instruction follows)
- agent.middlewares.completion.completion_guard.mixed_message::strip_readonly_calls_beside_answer (POS: early termination of a finished answer that still carries read-only calls)
- agent.middlewares.completion.completion_guard.capabilities::CompletionCapabilities (POS: what the run can do, so a demand is made only of a run that could meet it)
- agent.middlewares.completion.completion_guard.external_evidence::build_external_evidence_reason, extract_latest_human_text (POS: Freshness-sensitive external evidence gate including MCP PTC bash via skills.mcp_* and Direct FC via mcp__{server}__{tool})
- agent.middlewares.completion.completion_guard.rerun::rerun_verification_in_sandbox (POS: independent sandbox re-run of the last verification command)
- agent.middlewares.completion.completion_guard.safety::FINISH_TOOL_NAMES (POS: which tool call is a completion attempt)
- agent.middlewares.completion.deliverable.write_verifier::check_deliverable_write_claim (POS: Zero-call deliverable write claim detection for CompletionGuard)
- agent.middlewares.completion.execution_claim.verifier::check_execution_claim (POS: Completion-claim grounding against this run's tool records)
- agent.middlewares._run_workspace::run_workspace (POS: the workspace of the current run)

[OUTPUT]
- CompletionGuard: after_model middleware for critical completion verification + independent re-run; a held-back answer routes the run back to the model with the instruction pending in the turn state
- reset_completion_guard(): reset this run's guard state

[POS]
Fills the "Agent finishing" gap in the guard chain. Existing guards cover
tool-call loops (LoopGuard), context overflow (ContextBudgetGuard), and
emergency stops (EStop). CompletionGuard ensures code modifications are
verified before delivery via temporal ordering analysis and independent
sandbox re-run when code changes occur after the last successful verification and nothing else is wrong.
The Mixed Message Guard prevents wasted token/time when LLM already produced
a complete answer.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import replace

from langchain.agents.middleware import AgentMiddleware, AgentState, hook_config
from langchain_core.messages import AIMessage
from langgraph.runtime import Runtime

from myrm_agent_harness.agent.middlewares._run_workspace import run_workspace
from myrm_agent_harness.agent.middlewares.completion.completion_guard.capabilities import CompletionCapabilities
from myrm_agent_harness.agent.middlewares.completion.completion_guard.checklist import (
    VERIFICATION_CAUSES,
    CriticalCause,
    assess_checklist,
    find_last_successful_verification_command,
)
from myrm_agent_harness.agent.middlewares.completion.completion_guard.directive import BlockReasons
from myrm_agent_harness.agent.middlewares.completion.completion_guard.external_evidence import (
    build_external_evidence_reason,
    extract_latest_human_text,
)
from myrm_agent_harness.agent.middlewares.completion.completion_guard.hold_back import hold_back
from myrm_agent_harness.agent.middlewares.completion.completion_guard.mixed_message import (
    strip_readonly_calls_beside_answer,
)
from myrm_agent_harness.agent.middlewares.completion.completion_guard.rerun import rerun_verification_in_sandbox
from myrm_agent_harness.agent.middlewares.completion.completion_guard.safety import FINISH_TOOL_NAMES
from myrm_agent_harness.agent.middlewares.completion.completion_guard.state import (
    RunGuardState,
    current_run_state,
    publish_disclosure,
    publish_tier_disclosure,
    record_evidence,
    reset_run_state,
)
from myrm_agent_harness.agent.middlewares.completion.deliverable.auto_staging import (
    stage_unwritten_deliverables,
)
from myrm_agent_harness.agent.middlewares.completion.deliverable.write_verifier import (
    UnwrittenDeliverable,
    check_deliverable_write_claim,
    check_unwritten_deliverables,
)
from myrm_agent_harness.agent.middlewares.completion.execution_claim.verifier import (
    check_execution_claim,
    has_completion_claim,
)
from myrm_agent_harness.agent.middlewares.completion.query_grounding_verifier import (
    check_query_grounding_claim,
)

logger = logging.getLogger(__name__)


def reset_completion_guard() -> None:
    """Reset this run's guard state — call at the start of each agent run."""
    reset_run_state()


class CompletionGuard(AgentMiddleware):
    """Critical completion verification guard.

    Holds back a completion attempt that this run's tool records do not support: code changed without proof it
    works, a freshness question without external evidence, a claim no call backs. Other answers pass through
    immediately.

    Also implements the Mixed Message Guard to strip read-only tool_calls
    from messages that already contain a substantive final answer. Only tools
    that are guaranteed side-effect free AND carry no interaction/UI function
    are stripped; effectful calls and interaction/UI carriers are preserved.

    Parameters
    ----------
    enabled:
        Master on/off switch.
    max_rejections:
        Maximum times the guard blocks before forced finish (safety valve).
    capabilities:
        What this run can do, so a demand is made only of a run that could meet it. Without it the run is held
        to every demand.
    """

    def __init__(
        self,
        *,
        enabled: bool = True,
        max_rejections: int = 3,
        capabilities: CompletionCapabilities | None = None,
    ) -> None:
        self._enabled = enabled
        self._max_rejections = max_rejections
        self._capabilities = capabilities or CompletionCapabilities()

    def _evidence_demand(
        self, run_state: RunGuardState, messages: Sequence[object], records: Sequence[object]
    ) -> tuple[str | None, bool]:
        """The external-evidence demand on this answer, and whether the run is unable to meet it.

        A run that cannot gather evidence is asked once to say plainly it could not check, so the demand
        comes back flagged unreachable the first time and is dropped after: repeating it only costs calls.
        """
        reason = build_external_evidence_reason(messages=messages, records=records)
        if reason is None or self._capabilities.can_gather_evidence():
            return reason, False
        if run_state.evidence_disclosure_requested:
            return None, False
        return reason, True

    @hook_config(can_jump_to=["model"])
    async def aafter_model(self, state: AgentState, runtime: Runtime) -> dict[str, object] | None:
        """Hold back a completion attempt that fails a check: route the run back to the model with the instruction pending."""
        run_state = current_run_state()
        if not self._enabled or run_state.forced_finish:
            return None

        messages = state.get("messages", [])
        if not messages:
            return None

        last_ai_msg = next((msg for msg in reversed(messages) if isinstance(msg, AIMessage)), None)
        if last_ai_msg is None:
            return None

        from myrm_agent_harness.agent.middlewares.tooling.tool_interceptor_middleware import (
            get_loop_guard,
        )

        window = [r for r in get_loop_guard().recorded_calls() if not r.tool_name.startswith("_")]
        records = record_evidence(window)
        latest_user_text = extract_latest_human_text(messages)
        content_str = last_ai_msg.content if isinstance(last_ai_msg.content, str) else str(last_ai_msg.content or "")
        publish_tier_disclosure(content_str, records, has_claim=has_completion_claim(content_str))

        is_attempting_completion = not last_ai_msg.tool_calls or any(
            tc.get("name") in FINISH_TOOL_NAMES for tc in last_ai_msg.tool_calls if isinstance(tc, dict)
        )
        if not is_attempting_completion:
            return strip_readonly_calls_beside_answer(
                last_ai_msg, messages=messages, records=records, user_text=latest_user_text
            )

        workspace_root = run_workspace(runtime)
        todo_workspace = workspace_root if self._capabilities.keeps_todo_list() else None

        checklist = assess_checklist(records, workspace_root=todo_workspace)
        evidence_reason, evidence_unreachable = self._evidence_demand(run_state, messages, records)
        deliverable_write_reason: str | None = None
        unwritten_deliverables: list[UnwrittenDeliverable] = []
        execution_claim_reason = check_execution_claim(
            user_text=latest_user_text,
            assistant_text=content_str,
            records=records,
        )
        if last_ai_msg.content:
            deliverable_write_reason = check_deliverable_write_claim(content_str, records)
            if deliverable_write_reason is None and self._capabilities.can_save_files(runtime):
                unwritten_reason, unwritten_deliverables = check_unwritten_deliverables(
                    content=content_str,
                    records=records,
                    latest_user_text=latest_user_text,
                )
                if unwritten_reason is not None:
                    deliverable_write_reason = unwritten_reason
        query_grounding_reason = check_query_grounding_claim(
            user_text=latest_user_text,
            assistant_text=content_str,
            records=records,
        )

        blocked_by_a_check = any(
            reason is not None
            for reason in (evidence_reason, deliverable_write_reason, execution_claim_reason, query_grounding_reason)
        )
        if not checklist.critical and not blocked_by_a_check:
            return None

        # --- INDEPENDENT RE-RUN ---
        # Clears exactly one cause: code was modified after the last passing verification. Any other critical
        # finding (no verification, failed or empty verification, a failure that still stands, an unfinished
        # todo, an unsupported claim) is not something a green re-run can answer.
        if checklist.causes == {CriticalCause.STALE_VERIFICATION} and not blocked_by_a_check:
            rerun_cmd = find_last_successful_verification_command(records)
            if rerun_cmd and await rerun_verification_in_sandbox(rerun_cmd):
                logger.info("[CompletionGuard] Independent re-run of '%s' passed — allowing completion.", rerun_cmd)
                return None

        # --- CRITICAL BLOCKING MODE ---
        reasons = BlockReasons(
            evidence=evidence_reason or "",
            evidence_unreachable=evidence_unreachable,
            deliverable_write=deliverable_write_reason or "",
            execution_claim=execution_claim_reason or "",
            query_grounding=query_grounding_reason or "",
            verification=bool(checklist.causes & VERIFICATION_CAUSES),
        )
        current_rejections = run_state.rejections

        if current_rejections >= self._max_rejections:
            logger.error(
                "[CompletionGuard] Max rejections (%d) reached. Allowing agent to finish despite critical errors.",
                self._max_rejections,
            )
            run_state.forced_finish = True
            staged_metas_dict: list[dict[str, object]] = []
            if unwritten_deliverables and workspace_root:
                staged = stage_unwritten_deliverables(str(workspace_root), unwritten_deliverables)
                staged_metas_dict = [dict(m.to_dict()) for m in staged]
                if staged_metas_dict:
                    publish_disclosure(staged_artifacts=staged_metas_dict)
            reasons = replace(reasons, forced_finish=True, staged_artifacts=tuple(staged_metas_dict))
            return await hold_back(
                run_state,
                messages,
                last_ai_msg,
                reasons,
                records,
                todo_workspace,
                rejection=current_rejections,
                max_rejections=self._max_rejections,
            )

        run_state.rejections = current_rejections + 1
        logger.warning(
            "[CompletionGuard] Critical errors found. Blocking completion (rejection %d/%d).",
            current_rejections + 1,
            self._max_rejections,
        )
        if evidence_unreachable:
            run_state.evidence_disclosure_requested = True
        return await hold_back(
            run_state,
            messages,
            last_ai_msg,
            reasons,
            records,
            todo_workspace,
            rejection=current_rejections + 1,
            max_rejections=self._max_rejections,
        )


__all__ = [
    "CompletionGuard",
    "reset_completion_guard",
]
