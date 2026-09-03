"""Service singleton and management for four-tier spend control engine.

[INPUT]
- myrm_agent_harness.observability.spend_control::FourTierSpendControlEngine, SpendControlConfig

[OUTPUT]
- get_spend_control_engine: Returns process-scoped FourTierSpendControlEngine singleton

[POS]
Server-side bridge providing the FourTierSpendControlEngine singleton instance.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.api import (
    FourTierSpendControlEngine,
    SpendControlConfig,
)

logger = logging.getLogger(__name__)

_spend_control_engine: FourTierSpendControlEngine | None = None


def get_spend_control_engine() -> FourTierSpendControlEngine:
    """Return the singleton instance of FourTierSpendControlEngine."""
    global _spend_control_engine
    if _spend_control_engine is None:
        _spend_control_engine = FourTierSpendControlEngine(
            SpendControlConfig(
                tier1_ratio=0.70,
                tier2_ratio=0.90,
                tier3_ratio=1.00,
                tier4_ratio=1.30,
                downgrade_model_id="gpt-4o-mini",
            )
        )
    return _spend_control_engine
