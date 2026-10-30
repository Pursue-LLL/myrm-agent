"""Whether a failed agent run may be repeated, by the cause the failure carries.

[INPUT]
- myrm_agent_harness.toolkits.llms.errors::MyrmLLMError, classify_failover_reason, RecoverabilityLevel (POS: LLM failure taxonomy; each failure reason states whether waiting or repeating can help)
- myrm_agent_harness.api.config::ConfigIncompleteError (POS: a required setting is missing; only its owner can fix it)

[OUTPUT]
- is_transient_failure: True when a repeat of the run can succeed without anyone changing something

[POS]
Cron-side reader of the failure taxonomy. A failure that no repeat can fix (a revoked key, a context that is
too long, an exhausted balance, a rejected request, a missing model setting) must not be run again in-process
or through the executor's backoff: each repeat spends a full run for the same result.
"""

from __future__ import annotations

from myrm_agent_harness.api.config import ConfigIncompleteError
from myrm_agent_harness.toolkits.llms.errors import (
    MyrmLLMError,
    RecoverabilityLevel,
    classify_failover_reason,
)


def is_transient_failure(exc: Exception) -> bool:
    """True when *exc* is a failure a repeat can clear (rate limit, overload, transport trouble, unknown cause).

    A ``MyrmLLMError`` already carries the reason the agent stream settled on when the run failed, which can
    differ from what its text alone classifies as; any other exception is classified here.
    """
    if isinstance(exc, ConfigIncompleteError):
        return False
    reason = exc.error_code if isinstance(exc, MyrmLLMError) else classify_failover_reason(exc)
    return reason.recoverability is RecoverabilityLevel.TRANSIENT
