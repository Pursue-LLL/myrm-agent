"""Previewed consolidation plans, held until the user confirms one.

[INPUT]
- myrm_agent_harness.agent.skills.curator.consolidation::ConsolidationPlan (POS: the plan a preview produced)
- secrets / time (POS: random token and expiry)

[OUTPUT]
- store_plan: keep a previewed plan and issue the 900-second, single-use token that names it
- take_plan: hand back the plan a token names and forget it; None for an unknown or expired token

[POS]
Execute applies the plan the user previewed, not a new judgment of the same skills (a model answers the same
question differently from one call to the next). The preview stores its plan here and the token is the only way back
to it. The store is process-local, so a restart drops every pending plan and the user previews again.
"""

from __future__ import annotations

import secrets
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from myrm_agent_harness.agent.skills.curator.consolidation import ConsolidationPlan

_TTL_SECONDS = 900
_store: dict[str, tuple[float, ConsolidationPlan]] = {}


def store_plan(plan: ConsolidationPlan) -> str:
    token = secrets.token_urlsafe(24)
    _store[token] = (time.time() + _TTL_SECONDS, plan)
    return token


def take_plan(token: str) -> ConsolidationPlan | None:
    """Hand back the plan ``token`` names and forget it, so a token executes once."""
    entry = _store.pop(token, None)
    if entry is None:
        return None
    expires_at, plan = entry
    return plan if time.time() <= expires_at else None
