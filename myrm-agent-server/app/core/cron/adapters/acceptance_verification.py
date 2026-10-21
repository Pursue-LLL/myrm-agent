"""Acceptance criteria verification for cron jobs executed in direct mode.

When a CronJob has `acceptance_criteria` configured and runs outside the Goal
system (direct execution via _run_once), this module applies the same
VerificationGatekeeper used by the Goal system to validate the output.

[INPUT]
- myrm_agent_harness.agent.goals.verification.gatekeeper::VerificationGatekeeper (POS: Goal 验收验证编排器)
- myrm_agent_harness.toolkits.cron.types::CronJob, JobResult (POS: Cron 领域类型定义)

[OUTPUT]
- apply_acceptance_criteria_verification: Post-run verification using structured criteria.

[POS]
Bridges the VerificationGatekeeper (framework) into the Cron direct-execution path,
ensuring criteria-based verification is available regardless of execution mode.
"""

from __future__ import annotations

import asyncio
import logging

from myrm_agent_harness.agent.goals.verification.gatekeeper import VerificationGatekeeper
from myrm_agent_harness.toolkits.cron.types import CronJob, JobResult

logger = logging.getLogger(__name__)


async def apply_acceptance_criteria_verification(
    job: CronJob,
    result: JobResult,
    *,
    timeout_seconds: float = 60.0,
) -> JobResult:
    """Verify a successful cron result against the job's acceptance criteria.

    If verification passes, returns the original result unchanged.
    If verification fails, marks the result as failed with diagnostic info.
    """
    if not job.acceptance_criteria:
        return result

    # In direct execution mode (no GoalProvider), only shell criteria can be
    # verified. Semantic criteria require a GoalProvider for LLM evaluation,
    # which is only available in the Goal queue path.
    shell_only = [c for c in job.acceptance_criteria if c.get("type") == "shell"]
    if not shell_only:
        return result

    gatekeeper = VerificationGatekeeper(shell_only)
    if not gatekeeper.criteria:
        return result

    try:
        verification = await asyncio.wait_for(
            gatekeeper.verify_all(),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "Acceptance criteria verification timed out for job %s",
            job.id,
        )
        return _with_verification_metadata(
            result,
            status="error",
            passed=None,
            summary="Acceptance criteria verification timed out",
            success_override=False,
        )
    except Exception as exc:
        logger.warning(
            "Acceptance criteria verification error for job %s: %s",
            job.id,
            exc,
        )
        return result

    if verification.passed:
        logger.info("Cron job %s passed acceptance criteria", job.id)
        return _with_verification_metadata(
            result,
            status="pass",
            passed=True,
            summary=f"All {len(gatekeeper.criteria)} acceptance criteria passed",
        )

    failed_criteria = [{"label": r.criterion_label, "reason": r.reason} for r in verification.per_criterion if not r.passed]
    summary = "; ".join(f"{c['label']}: {c['reason']}" for c in failed_criteria[:3])
    logger.warning(
        "Cron job %s failed acceptance criteria: %s",
        job.id,
        failed_criteria,
    )
    return _with_verification_metadata(
        result,
        status="fail",
        passed=False,
        summary=f"{len(failed_criteria)} criterion(s) failed — {summary}",
        success_override=False,
    )


def _with_verification_metadata(
    result: JobResult,
    *,
    status: str,
    passed: bool | None,
    summary: str,
    success_override: bool | None = None,
) -> JobResult:
    """Attach verification result in the same format as post_run_verification."""
    metadata = dict(result.metadata or {})
    metadata["verification"] = {
        "status": status,
        "passed": passed,
        "summary": summary[:500],
    }
    return JobResult(
        success=success_override if success_override is not None else result.success,
        output=result.output,
        error=result.error if success_override is not False else f"acceptance criteria: {summary[:200]}",
        metadata=metadata,
        exit_code=result.exit_code if success_override is not False else 2,
    )
