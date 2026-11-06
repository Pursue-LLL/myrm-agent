"""[INPUT]
- myrm_agent_harness.toolkits.llms.routing.complexity_router.scoring::_MOMENTUM_LONG_THRESHOLD / _MOMENTUM_MAX_HISTORY / _MOMENTUM_SHORT_THRESHOLD / _TIER_SCORES (POS: complexity_router 子包的一部分；由 __init__.py 聚合导出。)
- myrm_agent_harness.toolkits.llms.routing.complexity_router.types::RoutingTier (POS: complexity_router 子包的一部分；由 __init__.py 聚合导出。)

[OUTPUT]
- _apply_momentum: Apply session momentum using weighted average (MR-17).

[POS]
complexity_router 子包的一部分；由 __init__.py 聚合导出。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.llms.routing.complexity_router.scoring import (
    _MOMENTUM_LONG_THRESHOLD,
    _MOMENTUM_MAX_HISTORY,
    _MOMENTUM_SHORT_THRESHOLD,
    _TIER_SCORES,
)
from myrm_agent_harness.toolkits.llms.routing.complexity_router.types import RoutingTier

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def _apply_momentum(
    tier: RoutingTier,
    text: str,
    recent_tiers: list[RoutingTier] | None,
    has_image: bool = False,
) -> tuple[RoutingTier, bool]:
    """Apply session momentum using weighted average (MR-17).

    Uses weighted average of recent tier scores instead of median.
    Momentum weight decays with message length:
    - <30 chars: full momentum (0.6)
    - 30-100 chars: linear decay
    - >100 chars: no momentum

    Also supports downgrading: if recent tiers are all SIMPLE but current
    tier is STANDARD/REASONING, apply negative momentum to prevent over-routing.

    Image queries carry a vision hard floor: the SIMPLE tier selects the light
    model, which is not guaranteed vision-capable (see ``image_input`` +6.0 in
    unified scoring). Momentum must never downgrade them below STANDARD — a
    text-only conversation history cannot justify stripping the user's image.

    Returns (adjusted_tier, was_overridden).
    """
    if not recent_tiers:
        return tier, False

    msg_len = len(text)

    # Compute momentum weight based on message length
    if msg_len > _MOMENTUM_LONG_THRESHOLD:
        momentum_weight = 0.0
    elif msg_len >= _MOMENTUM_SHORT_THRESHOLD:
        momentum_weight = 0.3 * (
            1.0 - (msg_len - _MOMENTUM_SHORT_THRESHOLD) / (_MOMENTUM_LONG_THRESHOLD - _MOMENTUM_SHORT_THRESHOLD)
        )
    else:
        momentum_weight = 0.3 + 0.3 * (1.0 - msg_len / _MOMENTUM_SHORT_THRESHOLD)

    if momentum_weight <= 0:
        return tier, False

    # Compute weighted average of recent tier scores
    recent_slice = recent_tiers[:_MOMENTUM_MAX_HISTORY]
    history_sum = sum(_TIER_SCORES.get(t, 0.0) for t in recent_slice)
    history_avg = history_sum / len(recent_slice)

    # Current tier score
    current_score = _TIER_SCORES.get(tier, 0.0)

    # Blended score
    effective_score = (1 - momentum_weight) * current_score + momentum_weight * history_avg

    # Map effective score back to tier
    # Thresholds are lower than raw scores because blended range is narrower.
    if effective_score >= 0.1:
        adjusted = RoutingTier.REASONING
    elif effective_score >= -0.1:
        adjusted = RoutingTier.STANDARD
    else:
        adjusted = RoutingTier.SIMPLE

    if adjusted != tier:
        if has_image and adjusted == RoutingTier.SIMPLE:
            # Vision floor: SIMPLE selects the light (non-vision-guaranteed)
            # model, so an image query keeps its rule verdict (STANDARD+).
            logger.debug("Momentum downgrade to SIMPLE skipped: image query requires a vision-capable tier")
            return tier, False

        logger.info(
            "Momentum override: %s → %s (weight=%.2f, history_avg=%.2f, effective=%.2f)",
            tier,
            adjusted,
            momentum_weight,
            history_avg,
            effective_score,
        )
        return adjusted, True

    return tier, False
