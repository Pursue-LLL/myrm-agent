"""The one definition of a failed run, shared by every reader of run history.

[INPUT]
- toolkits.cron.types::RunStatus (POS: Cron job domain types.)

[OUTPUT]
- FAILED_RUN_STATUSES: the statuses of a run that failed: a plain error, or a circuit break (a failure with a status of its own)
- matching_run_statuses: the stored statuses a run-history status filter selects

[POS]
Status-filter semantics for every ``CronStore`` and for the listings built on one. A circuit break is a failed run, so
the filter that asks for failures (``error``) selects it too; any other filter selects exactly its own status. A store
that compared ``status == filter`` would count fewer failures than the run history shows.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.cron.types import RunStatus

FAILED_RUN_STATUSES = frozenset({RunStatus.ERROR, RunStatus.CIRCUIT_BREAK})


def matching_run_statuses(status: str) -> frozenset[str]:
    """The stored statuses a filter on ``status`` selects: every failure for ``error``, otherwise just ``status``."""
    return FAILED_RUN_STATUSES if status == RunStatus.ERROR else frozenset({status})
