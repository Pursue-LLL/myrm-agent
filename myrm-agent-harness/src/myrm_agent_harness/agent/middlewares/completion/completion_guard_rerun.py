"""Independent re-run of a verification command, for the completion guard.

When code was written after the agent's last successful verification, the guard does not take the agent's word
that the checks still pass: it runs the same command itself in the sandbox, which costs no model call.

[INPUT]
- toolkits.code_execution.executors.base::get_executor (POS: the run's sandbox executor)
- toolkits.code_execution.executors.models::ExecutionContext (POS: one command to execute)

[OUTPUT]
- rerun_verification_in_sandbox(): whether the command exits with code 0 when run again

[POS]
Sandbox side of the completion guard's temporal-ordering check; ``completion_guard`` decides when a re-run is due.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

RERUN_TIMEOUT_SECONDS: int = 120


async def rerun_verification_in_sandbox(command: str) -> bool:
    """Execute a verification command independently in the sandbox.

    Returns True only when the command exits with code 0. Any executor
    unavailability or execution failure returns False (fail-closed).
    """
    try:
        from myrm_agent_harness.toolkits.code_execution.executors.base import (
            get_executor,
        )
        from myrm_agent_harness.toolkits.code_execution.executors.models import (
            ExecutionContext,
        )

        executor = get_executor()
        if not executor:
            logger.warning("[CompletionGuard] Sandbox executor unavailable — skipping independent re-run.")
            return False

        context = ExecutionContext(code=command, timeout=RERUN_TIMEOUT_SECONDS)
        result = await executor.execute_bash(context)

        if result.exit_code == 0:
            return True

        logger.warning(
            "[CompletionGuard] Independent re-run failed (exit_code=%d): %s",
            result.exit_code,
            (result.stderr or result.stdout or "")[:500],
        )
        return False
    except Exception:
        logger.warning("[CompletionGuard] Independent re-run raised exception.", exc_info=True)
        return False
