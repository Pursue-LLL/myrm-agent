"""Cron post-run delivery verification — verifier-only pass after agent stream completes.

[INPUT]
- myrm_agent_harness.agent.sub_agents.orchestrator::verify_worker_output (POS: Verifier pass)
- myrm_agent_harness.toolkits.cron.types::CronJob, JobResult (POS: Cron job types)

[OUTPUT]
- run_post_run_verification: Optional verifier-only pass after cron agent stream

[POS]
Server cron adapter. Runs adversarial-reviewer verification on cron job output when
configured, without re-running the full agent loop.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace

from myrm_agent_harness.agent.middlewares.completion_guard import is_mutating_tool
from myrm_agent_harness.agent.sub_agents.orchestrator import verify_worker_output
from myrm_agent_harness.agent.sub_agents.types import WorkspacePolicy
from myrm_agent_harness.toolkits.cron.types import CronJob, JobResult

logger = logging.getLogger(__name__)

_DEFAULT_VERIFIER_TYPE = "adversarial-reviewer"
_VERIFICATION_TIMEOUT_SECONDS = 120


def _has_effectful_tools(progress_steps: list[dict[str, object]]) -> bool:
    for step in progress_steps:
        tool_name = step.get("tool_name")
        if isinstance(tool_name, str) and is_mutating_tool(tool_name):
            return True
    return False


def _attach_verification_metadata(
    result: JobResult,
    *,
    status: str,
    passed: bool | None,
    summary: str,
) -> JobResult:
    metadata = dict(result.metadata or {})
    metadata["verification"] = {
        "status": status,
        "passed": passed,
        "summary": summary[:500],
    }
    return JobResult(
        success=result.success,
        output=result.output,
        error=result.error,
        skipped=result.skipped,
        metadata=metadata,
    )


async def apply_cron_post_run_verification(
    agent: object,
    job: CronJob,
    result: JobResult,
    *,
    enabled: bool,
) -> JobResult:
    """Optionally run verifier-only delivery assurance on a completed cron agent run."""
    if not enabled or not result.success or result.skipped:
        return result

    progress_steps_raw = (result.metadata or {}).get("progressSteps")
    progress_steps: list[dict[str, object]] = (
        [step for step in progress_steps_raw if isinstance(step, dict)]
        if isinstance(progress_steps_raw, list)
        else []
    )
    if not _has_effectful_tools(progress_steps):
        return _attach_verification_metadata(
            result,
            status="skipped",
            passed=None,
            summary="No effectful tool usage detected",
        )

    from app.ai_agents.general_agent import GeneralAgent

    if not isinstance(agent, GeneralAgent):
        return result

    skill_agent = agent.agent
    if skill_agent is None:
        return _attach_verification_metadata(
            result,
            status="error",
            passed=False,
            summary="Agent runtime not available for verification",
        )

    manager = getattr(skill_agent, "_subagent_manager", None)
    if manager is None:
        return _attach_verification_metadata(
            result,
            status="error",
            passed=False,
            summary="Subagent manager not available for verification",
        )

    worker_output = (result.output or "").strip()
    if not worker_output:
        return _attach_verification_metadata(
            result,
            status="skipped",
            passed=None,
            summary="Empty agent output",
        )

    parent_tools = skill_agent._cached_tools or skill_agent.user_tools

    def tool_registry_getter() -> list[object]:
        return list(parent_tools)

    parent_ctx = dict(getattr(skill_agent, "_last_context", None) or {})
    child_context: dict[str, object] = dict(parent_ctx)
    child_context.setdefault("session_id", job.chat_id or job.id)

    try:
        from app.ai_agents.subagent_catalog import DatabaseSubagentCatalog

        catalog = DatabaseSubagentCatalog()
        verifier_config = await catalog.resolve(_DEFAULT_VERIFIER_TYPE)
        if not verifier_config:
            return _attach_verification_metadata(
                result,
                status="error",
                passed=False,
                summary=f"Verifier preset '{_DEFAULT_VERIFIER_TYPE}' not found",
            )

        readonly_verifier = replace(verifier_config, workspace_policy=WorkspacePolicy.READ_ONLY_SANDBOX)
        verdict = await asyncio.wait_for(
            verify_worker_output(
                manager,
                worker_output=worker_output,
                worker_type=job.agent_id or "cron-worker",
                verifier_type=_DEFAULT_VERIFIER_TYPE,
                verifier_config=readonly_verifier,
                context=child_context,
                tool_registry_getter=tool_registry_getter,
                verifier_task_template=(
                    "Review this unattended scheduled task output. "
                    "Confirm side effects match the reported outcome and flag regressions or silent failures."
                ),
            ),
            timeout=_VERIFICATION_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        logger.warning("Cron job %s post-run verification timed out after %ss", job.id, _VERIFICATION_TIMEOUT_SECONDS)
        return _attach_verification_metadata(
            result,
            status="error",
            passed=False,
            summary=f"Verification timed out after {_VERIFICATION_TIMEOUT_SECONDS}s",
        )
    except Exception as exc:
        logger.warning("Cron job %s post-run verification failed: %s", job.id, exc)
        return _attach_verification_metadata(
            result,
            status="error",
            passed=False,
            summary=str(exc),
        )

    status = "pass" if verdict.passed else "fail"
    annotated = _attach_verification_metadata(
        result,
        status=status,
        passed=verdict.passed,
        summary=verdict.summary,
    )
    if verdict.passed:
        return annotated

    fail_note = f"[Delivery verification: FAIL] {verdict.summary}"
    combined_output = f"{worker_output}\n\n---\n{fail_note}" if worker_output else fail_note
    return JobResult(
        success=result.success,
        output=combined_output,
        error=result.error,
        skipped=result.skipped,
        metadata=annotated.metadata,
    )
