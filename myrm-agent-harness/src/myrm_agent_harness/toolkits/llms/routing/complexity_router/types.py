"""[INPUT]
- myrm_agent_harness.core.config.llm::LLMConfig (POS: Framework-agnostic LLM configuration SSOT. Defines CustomModelDef and LLMConfig for agent/ and toolkits/ without runtime coupling.)

[OUTPUT]
- RoutingTier: RoutingTier
- RoutingResult: RoutingResult
- WeightedKeyword: A keyword with an associated weight for scoring.
- _build_weighted_keywords: Build weighted keyword dict from a frozenset.

[POS]
complexity_router 子包的一部分；由 __init__.py 聚合导出。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from myrm_agent_harness.core.config.llm import LLMConfig

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class RoutingTier(StrEnum):
    SIMPLE = "simple"
    STANDARD = "standard"
    REASONING = "reasoning"


_TIER_RANK: dict[RoutingTier, int] = {RoutingTier.SIMPLE: 0, RoutingTier.STANDARD: 1, RoutingTier.REASONING: 2}


@dataclass(frozen=True)
class RoutingResult:
    tier: RoutingTier
    model_cfg: LLMConfig
    fallback_model_cfg: LLMConfig | None
    reason: str


# ============ MR-15: Weighted Keywords ============
# Per-keyword weights for unified scoring.
# Mirrors manifest-router's KEYWORD_WEIGHTS + ACTIVATION_THRESHOLDS.


@dataclass(frozen=True)
class WeightedKeyword:
    """A keyword with an associated weight for scoring."""

    keyword: str
    weight: float = 1.0


def _build_weighted_keywords(
    keywords: frozenset[str],
    strong_weight: float = 2.0,
    weak_weight: float = 1.0,
) -> dict[str, float]:
    """Build weighted keyword dict from a frozenset.

    Strong anchors (multi-word, technical) get higher weight.
    Single common words get lower weight.
    """
    result: dict[str, float] = {}
    for kw in keywords:
        # Multi-word or technical keywords are stronger signals
        if " " in kw or len(kw) > 10:
            result[kw] = strong_weight
        else:
            result[kw] = weak_weight
    return result


# ============ MR-16: Unified Scoring Dimensions ============
# Structural and contextual signals for unified scoring.
# Mirrors manifest-router's structural-dimensions + contextual-dimensions.
