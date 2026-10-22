"""Defer a cron agent run whose provider quota window is closed.

[INPUT]
- myrm_agent_harness.api.hooks::deferral_wait_s (POS: waitable provider boundary carried by a fatal LLM error)
- myrm_agent_harness.toolkits.cron.types::JobResult (POS: runner result; ``retry_at`` re-arms the job)

[OUTPUT]
- USAGE_LIMIT_SKIP_REASON: run-history code recorded for a deferred run
- usage_limit_deferral: JobResult that re-arms the job at the provider's reset, or None

[POS]
Cron-side consumer of the provider-window fact. A job that fails inside a known window must
neither burn its retries against the closed window nor accumulate failures until it is
auto-paused; it runs again right after the provider reopens.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from myrm_agent_harness.api.hooks import deferral_wait_s
from myrm_agent_harness.toolkits.cron.types import JobResult

USAGE_LIMIT_SKIP_REASON = "usage_limit"


def usage_limit_deferral(exc: BaseException, *, now: datetime | None = None) -> JobResult | None:
    """Deferral result for *exc*, or None when it carries no waitable provider boundary."""
    wait_s = deferral_wait_s(exc)
    if wait_s is None:
        return None
    reference = now or datetime.now(UTC)
    return JobResult(
        success=False,
        error=str(exc),
        skip_reason=USAGE_LIMIT_SKIP_REASON,
        retry_at=reference + timedelta(seconds=wait_s),
    )
