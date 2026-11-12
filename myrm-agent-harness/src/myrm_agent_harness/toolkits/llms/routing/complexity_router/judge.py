"""[INPUT]
- myrm_agent_harness.core.config.llm::LLMConfig (POS: Framework-agnostic LLM configuration SSOT. Defines CustomModelDef and LLMConfig for agent/ and toolkits/ without runtime coupling.)
- myrm_agent_harness.toolkits.llms.routing.complexity_router.types::RoutingTier (POS: complexity_router 子包的一部分；由 __init__.py 聚合导出。)
- myrm_agent_harness.utils.chat_utils::extract_answer_text (POS: Chat utility functions. Provides business-config-independent chat history conversion (generic part).)

[OUTPUT]
- _hash_text: _hash_text
- _cache_get: _cache_get
- _cache_put: _cache_put
- _llm_judge_classify: Phase 2: LLM-based classification for ambiguous cases.
- _select_model_for_tier: Select model_cfg and fallback for a given tier with graceful degradation.

[POS]
complexity_router 子包的一部分；由 __init__.py 聚合导出。
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from hashlib import sha256
from typing import TYPE_CHECKING

from myrm_agent_harness.core.config.llm import LLMConfig
from myrm_agent_harness.toolkits.llms.routing.complexity_router.types import RoutingTier
from myrm_agent_harness.utils.chat_utils import extract_answer_text

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

logger = logging.getLogger(__name__)


_JUDGE_CACHE_MAX = 256
_JUDGE_CACHE_TTL_S = 300.0
_JUDGE_TIMEOUT_S = 5.0
_judge_cache: dict[str, tuple[str, float]] = {}

_TIER_PARSE_RE = re.compile(r'"tier"\s*:\s*"(SIMPLE|STANDARD|REASONING)"', re.IGNORECASE)

_JUDGE_TIER_MAP: dict[str, RoutingTier] = {
    "SIMPLE": RoutingTier.SIMPLE,
    "STANDARD": RoutingTier.STANDARD,
    "REASONING": RoutingTier.REASONING,
}


def _hash_text(text: str) -> str:
    return sha256(text.encode()).hexdigest()[:16]


def _cache_get(text_hash: str) -> RoutingTier | None:
    entry = _judge_cache.get(text_hash)
    if entry is None:
        return None
    tier_val, ts = entry
    if time.monotonic() - ts > _JUDGE_CACHE_TTL_S:
        _judge_cache.pop(text_hash, None)
        return None
    try:
        return RoutingTier(tier_val)
    except ValueError:
        _judge_cache.pop(text_hash, None)
        return None


def _cache_put(text_hash: str, tier: RoutingTier) -> None:
    if len(_judge_cache) >= _JUDGE_CACHE_MAX:
        oldest_key = next(iter(_judge_cache))
        _judge_cache.pop(oldest_key, None)
    _judge_cache[text_hash] = (tier.value, time.monotonic())


async def _llm_judge_classify(
    text: str,
    judge_llm: BaseChatModel,
    judge_system_prompt: str,
) -> RoutingTier | None:
    """Phase 2: LLM-based classification for ambiguous cases.

    Returns ``None`` on timeout/exception/unparseable output — a degradation,
    not a verdict. Callers must NOT cache ``None`` results (a transient judge
    failure must not pin the default tier for the cache TTL).
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    try:
        response = await asyncio.wait_for(
            judge_llm.ainvoke(
                [
                    SystemMessage(content=judge_system_prompt),
                    HumanMessage(content=text[:500]),
                ]
            ),
            timeout=_JUDGE_TIMEOUT_S,
        )
        content = extract_answer_text(response).strip()

        match = _TIER_PARSE_RE.search(content)
        if match:
            tier_str = match.group(1).upper()
            return _JUDGE_TIER_MAP.get(tier_str, RoutingTier.STANDARD)
    except Exception as e:
        logger.warning("LLM judge classification failed: %s", e)

    return None


def _select_model_for_tier(
    tier: RoutingTier,
    standard_model_cfg: LLMConfig,
    light_model_cfg: LLMConfig | None,
    reasoning_model_cfg: LLMConfig | None,
    standard_fallback_cfg: LLMConfig | None,
    light_fallback_cfg: LLMConfig | None,
    reasoning_fallback_cfg: LLMConfig | None,
) -> tuple[LLMConfig, LLMConfig | None]:
    """Select model_cfg and fallback for a given tier with graceful degradation."""
    if tier == RoutingTier.SIMPLE:
        cfg = light_model_cfg or standard_model_cfg
        fallback = light_fallback_cfg or standard_fallback_cfg
        return cfg, fallback

    if tier == RoutingTier.REASONING:
        cfg = reasoning_model_cfg or standard_model_cfg
        fallback = reasoning_fallback_cfg or standard_fallback_cfg
        return cfg, fallback

    return standard_model_cfg, standard_fallback_cfg


# ============ MR-18: Content-Level Dedup ============
# Deduplicate identical queries to prevent repeated scoring.

_dedup_cache: dict[str, RoutingTier] = {}
