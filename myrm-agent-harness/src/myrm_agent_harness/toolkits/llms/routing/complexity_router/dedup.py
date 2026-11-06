"""路由结果去重缓存。

[POS]
complexity_router 子包的一部分；由 __init__.py 聚合导出。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.llms.routing.complexity_router.judge import _hash_text
from myrm_agent_harness.toolkits.llms.routing.complexity_router.types import RoutingTier

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


_dedup_cache: dict[str, RoutingTier] = {}
_DEDUP_CACHE_MAX = 128


def _dedup_key(text: str, has_image: bool) -> str:
    """Build a content-dedup cache key scoped by image presence.

    Image input forces STANDARD (``image_input`` +6.0 in unified scoring), so
    a verdict cached from a text-only query must never satisfy an image query —
    image tasks need vision-capable models.
    """
    return f"{has_image}\x00{text}"


def _dedup_check(text: str, has_image: bool) -> RoutingTier | None:
    """Check if this exact text (with image flag) was recently routed.

    Returns cached tier or None.
    """
    return _dedup_cache.get(_hash_text(_dedup_key(text, has_image)))


def _dedup_store(text: str, has_image: bool, tier: RoutingTier) -> None:
    """Store a context-free routing verdict for content dedup.

    Only pure rule-phase verdicts (`rule_result`) may be stored — never
    momentum- or min_tier-adjusted results, which are session-local. LLM-judge
    verdicts are managed exclusively by the TTL-bounded `_judge_cache`: the
    judge branch never reads this cache, so duplicating judge verdicts here
    would only create an unbounded stale copy for the rule branch to mis-read.
    """
    if len(_dedup_cache) >= _DEDUP_CACHE_MAX:
        oldest_key = next(iter(_dedup_cache))
        _dedup_cache.pop(oldest_key, None)
    _dedup_cache[_hash_text(_dedup_key(text, has_image))] = tier
