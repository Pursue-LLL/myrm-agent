"""[INPUT]
- myrm_agent_harness.toolkits.llms.routing.complexity_router.keywords::_TRACEBACK_RE (POS: complexity_router 子包的一部分；由 __init__.py 聚合导出。)
- myrm_agent_harness.toolkits.llms.routing.complexity_router.signals::_has_code_content / _has_math_content / _is_simple_greeting / _score_contextual_signals / _score_structural_signals / _word_count (POS: complexity_router 子包的一部分；由 __init__.py 聚合导出。)
- myrm_agent_harness.toolkits.llms.routing.complexity_router.types::RoutingTier (POS: complexity_router 子包的一部分；由 __init__.py 聚合导出。)

[OUTPUT]
- _compute_unified_score: Compute unified scores for all tiers using multi-dimensional signals.
- _rule_based_classify: Phase 1: unified scoring classification. Returns None if ambiguous.

[POS]
complexity_router 子包的一部分；由 __init__.py 聚合导出。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.llms.routing.complexity_router.keywords import _TRACEBACK_RE
from myrm_agent_harness.toolkits.llms.routing.complexity_router.signals import (
    _has_code_content,
    _has_math_content,
    _is_simple_greeting,
    _score_contextual_signals,
    _score_structural_signals,
    _word_count,
)
from myrm_agent_harness.toolkits.llms.routing.complexity_router.types import RoutingTier

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def _compute_unified_score(
    text: str,
    has_image: bool,
    standard_keywords: frozenset[str],
    reasoning_keywords: frozenset[str],
    simple_indicators: frozenset[str],
) -> dict[RoutingTier, float]:
    """Compute unified scores for all tiers using multi-dimensional signals.

    Aggregates keyword, structural, and contextual signals into per-tier scores.
    Higher score = stronger signal for that tier.

    Returns dict mapping each RoutingTier to its aggregate score.
    """
    scores: dict[RoutingTier, float] = {
        RoutingTier.SIMPLE: 0.0,
        RoutingTier.STANDARD: 0.0,
        RoutingTier.REASONING: 0.0,
    }
    lower = text.lower()
    wc = _word_count(text)

    # --- Keyword signals (weighted) ---
    for kw in standard_keywords:
        if kw in lower:
            # Multi-word or technical keywords are stronger signals
            weight = 2.0 if (" " in kw or len(kw) > 10) else 1.0
            scores[RoutingTier.STANDARD] += weight

    for kw in reasoning_keywords:
        if kw in lower:
            weight = 2.0 if (" " in kw or len(kw) > 10) else 1.0
            scores[RoutingTier.REASONING] += weight

    # --- Simple greeting signal ---
    if _is_simple_greeting(text, simple_indicators):
        scores[RoutingTier.SIMPLE] += 5.0  # strong signal

    # --- Math signal ---
    if _has_math_content(text):
        scores[RoutingTier.REASONING] += 3.0

    # --- Code signal ---
    if _has_code_content(text):
        scores[RoutingTier.STANDARD] += 2.0

    # --- Traceback / stack-trace pattern signal ---
    if _TRACEBACK_RE.search(text):
        scores[RoutingTier.STANDARD] += 3.0

    # --- Structural signals (MR-16) ---
    structural = _score_structural_signals(text)
    if "urls" in structural:
        scores[RoutingTier.STANDARD] += structural["urls"]
    if "file_paths" in structural:
        scores[RoutingTier.STANDARD] += structural["file_paths"]

    # --- Contextual signals (MR-16) ---
    contextual = _score_contextual_signals(text, has_image, wc)
    if "image_input" in contextual:
        scores[RoutingTier.STANDARD] += contextual["image_input"]
    if "long_input" in contextual:
        scores[RoutingTier.STANDARD] += contextual["long_input"]
    if "repetition_request" in contextual:
        scores[RoutingTier.STANDARD] += contextual["repetition_request"]

    # --- Short message without signals → SIMPLE ---
    if wc <= 8 and scores[RoutingTier.STANDARD] < 1.0 and scores[RoutingTier.REASONING] < 1.0:
        scores[RoutingTier.SIMPLE] += 3.0

    # --- Long message without strong signals → STANDARD ---
    if wc > 50 and scores[RoutingTier.STANDARD] < 1.0 and scores[RoutingTier.REASONING] < 1.0:
        scores[RoutingTier.STANDARD] += 1.5

    return scores


# Scoring thresholds for tier activation
_TIER_THRESHOLDS: dict[RoutingTier, float] = {
    RoutingTier.SIMPLE: 2.0,
    RoutingTier.STANDARD: 1.5,
    RoutingTier.REASONING: 2.0,
}


def _rule_based_classify(
    text: str,
    has_image: bool,
    standard_keywords: frozenset[str],
    reasoning_keywords: frozenset[str],
    simple_indicators: frozenset[str],
) -> RoutingTier | None:
    """Phase 1: unified scoring classification. Returns None if ambiguous.

    Uses multi-dimensional scoring (keyword + structural + contextual) aggregated
    into per-tier scores, then selects the highest-scoring tier above its threshold.
    """
    scores = _compute_unified_score(text, has_image, standard_keywords, reasoning_keywords, simple_indicators)

    # Find the best tier above its threshold
    best_tier: RoutingTier | None = None
    best_score = 0.0

    for tier, score in scores.items():
        threshold = _TIER_THRESHOLDS[tier]
        if score >= threshold and score > best_score:
            best_tier = tier
            best_score = score

    return best_tier


# ============ MR-17: Weighted Multi-Turn Momentum ============
# Weighted average momentum instead of median.
# Mirrors manifest-router's momentum.ts with tier-specific scores and length-based decay.

_TIER_SCORES: dict[RoutingTier, float] = {
    RoutingTier.SIMPLE: -0.2,
    RoutingTier.STANDARD: 0.0,
    RoutingTier.REASONING: 0.4,
}

_MOMENTUM_MAX_HISTORY = 5
_MOMENTUM_LONG_THRESHOLD = 100  # messages > 100 chars get zero momentum weight
_MOMENTUM_SHORT_THRESHOLD = 30  # messages < 30 chars get full momentum weight
