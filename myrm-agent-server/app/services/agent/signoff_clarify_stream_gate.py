"""H2e stream gate — propagate signoff clarify contract into agent stream context.

[INPUT]
- GeneralAgentParams.signoff_clarify_contract (POS: request-level contract flag)
- MYRM_E2E_SIGNOFF_CLARIFY_POOL env on SHPOIB backend (POS: pool SSOT)

[OUTPUT]
- apply_signoff_clarify_stream_gate: merge contract flag into params + extra_context

[POS]
Business streaming layer belt-and-suspenders so SHPOIB pool backends always activate
signoff clarify contract even if engineParams parsing drifts.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.ai_agents.general_agent.signoff_clarify_contract_core import (
    signoff_clarify_contract_enabled,
)

if TYPE_CHECKING:
    from app.ai_agents import GeneralAgentParams

logger = logging.getLogger(__name__)


def apply_signoff_clarify_stream_gate(
    params: GeneralAgentParams,
    extra_context: dict[str, object] | None,
) -> dict[str, object]:
    """Ensure signoff clarify contract is active for SHPOIB pool agent streams."""
    if not signoff_clarify_contract_enabled(
        flag=bool(getattr(params, "signoff_clarify_contract", False))
    ):
        return dict(extra_context or {})

    params.signoff_clarify_contract = True
    if not params.enable_structured_clarify:
        params.enable_structured_clarify = True

    ctx = dict(extra_context or {})
    ctx["signoff_clarify_contract"] = True
    logger.info(
        "SignoffClarifyContract stream gate active chat_id=%s message_id=%s",
        params.chat_id,
        params.message_id,
    )
    return ctx
