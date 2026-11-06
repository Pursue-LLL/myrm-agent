"""[INPUT]
- myrm_agent_harness.core.config.llm::LLMConfig (POS: Framework-agnostic LLM configuration SSOT. Defines CustomModelDef and LLMConfig for agent/ and toolkits/ without runtime)
- myrm_agent_harness.toolkits.llms.routing.complexity_router.dedup::_dedup_check / _dedup_store (POS: complexity_router 子包的一部分；由 __init__.py 聚合导出。)
- myrm_agent_harness.toolkits.llms.routing.complexity_router.judge::_cache_get / _cache_put / _hash_text / _llm_judge_classify / _select_model_for_tier (POS: complexity_router 子包的一部分；由 __init__.py 聚合导出。)
- myrm_agent_harness.toolkits.llms.routing.complexity_router.keywords::DEFAULT_JUDGE_SYSTEM_PROMPT / DEFAULT_REASONING_KEYWORDS / DEFAULT_SIMPLE_INDICATORS / DEFAULT_STANDARD_KEYWORDS (POS: complexity_router 子包的一部分；由 __init__.py 聚合导出。)
- myrm_agent_harness.toolkits.llms.routing.complexity_router.momentum::_apply_momentum (POS: complexity_router 子包的一部分；由 __init__.py 聚合导出。)
- myrm_agent_harness.toolkits.llms.routing.complexity_router.scoring::_rule_based_classify (POS: complexity_router 子包的一部分；由 __init__.py 聚合导出。)
- myrm_agent_harness.toolkits.llms.routing.complexity_router.signals::_normalize_query (POS: complexity_router 子包的一部分；由 __init__.py 聚合导出。)
- myrm_agent_harness.toolkits.llms.routing.complexity_router.types::_TIER_RANK / RoutingResult / RoutingTier (POS: complexity_router 子包的一部分；由 __init__.py 聚合导出。)

[OUTPUT]
- route_task: Route a task to the appropriate model tier (3-tier).

[POS]
complexity_router 子包的一部分；由 __init__.py 聚合导出。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from myrm_agent_harness.core.config.llm import LLMConfig
from myrm_agent_harness.toolkits.llms.routing.complexity_router.dedup import _dedup_check, _dedup_store
from myrm_agent_harness.toolkits.llms.routing.complexity_router.judge import (
    _cache_get,
    _cache_put,
    _hash_text,
    _llm_judge_classify,
    _select_model_for_tier,
)
from myrm_agent_harness.toolkits.llms.routing.complexity_router.keywords import (
    DEFAULT_JUDGE_SYSTEM_PROMPT,
    DEFAULT_REASONING_KEYWORDS,
    DEFAULT_SIMPLE_INDICATORS,
    DEFAULT_STANDARD_KEYWORDS,
)
from myrm_agent_harness.toolkits.llms.routing.complexity_router.momentum import _apply_momentum
from myrm_agent_harness.toolkits.llms.routing.complexity_router.scoring import _rule_based_classify
from myrm_agent_harness.toolkits.llms.routing.complexity_router.signals import _normalize_query
from myrm_agent_harness.toolkits.llms.routing.complexity_router.types import _TIER_RANK, RoutingResult, RoutingTier

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

logger = logging.getLogger(__name__)


async def route_task(
    query: str | list[dict[str, object]],
    standard_model_cfg: LLMConfig,
    light_model_cfg: LLMConfig | None = None,
    reasoning_model_cfg: LLMConfig | None = None,
    standard_fallback_cfg: LLMConfig | None = None,
    light_fallback_cfg: LLMConfig | None = None,
    reasoning_fallback_cfg: LLMConfig | None = None,
    judge_llm: BaseChatModel | None = None,
    *,
    recent_tiers: list[RoutingTier] | None = None,
    min_tier: RoutingTier | None = None,
    standard_keywords: frozenset[str] | None = None,
    reasoning_keywords: frozenset[str] | None = None,
    simple_indicators: frozenset[str] | None = None,
    judge_system_prompt: str | None = None,
) -> RoutingResult:
    """Route a task to the appropriate model tier (3-tier).

    Uses unified multi-dimensional scoring (MR-16), weighted momentum (MR-17),
    and content dedup (MR-18).

    Args:
        query: User query (text or multimodal)
        standard_model_cfg: Primary model config — STANDARD tier
        light_model_cfg: Light model config — SIMPLE tier
        reasoning_model_cfg: Reasoning model config — REASONING tier
        standard_fallback_cfg: Fallback for STANDARD tier
        light_fallback_cfg: Fallback for SIMPLE tier
        reasoning_fallback_cfg: Fallback for REASONING tier
        judge_llm: Optional LLM for Phase 2 classification
        recent_tiers: Recent routing tiers from conversation history (for momentum)
        min_tier: Minimum tier floor — result will not be lower than this (e.g. for regenerate escalation)
        standard_keywords: Custom standard-tier keywords (defaults provided)
        reasoning_keywords: Custom reasoning-tier keywords (defaults provided)
        simple_indicators: Custom simple greeting indicators (defaults provided)
        judge_system_prompt: Custom LLM judge system prompt (default provided)

    Returns:
        RoutingResult with selected tier, model config, fallback, and reason
    """
    std_kw = standard_keywords or DEFAULT_STANDARD_KEYWORDS
    reason_kw = reasoning_keywords or DEFAULT_REASONING_KEYWORDS
    simple_ind = simple_indicators or DEFAULT_SIMPLE_INDICATORS
    judge_prompt = judge_system_prompt or DEFAULT_JUDGE_SYSTEM_PROMPT

    select_args = (
        standard_model_cfg,
        light_model_cfg,
        reasoning_model_cfg,
        standard_fallback_cfg,
        light_fallback_cfg,
        reasoning_fallback_cfg,
    )

    text, has_image = _normalize_query(query)

    if not text.strip():
        cfg, fallback = _select_model_for_tier(RoutingTier.STANDARD, *select_args)
        return RoutingResult(
            tier=RoutingTier.STANDARD,
            model_cfg=cfg,
            fallback_model_cfg=fallback,
            reason="empty_query",
        )

    rule_result = _rule_based_classify(
        text,
        has_image,
        std_kw,
        reason_kw,
        simple_ind,
    )
    if rule_result is not None:
        if not min_tier:
            deduped = _dedup_check(text, has_image)
            if deduped is not None:
                # 命中纯判定缓存：仍需走 momentum（与 judge 缓存对称），
                # 缓存只存无上下文的档位，会话上下文在此每轮重算。
                final_tier, overridden = _apply_momentum(deduped, text, recent_tiers, has_image)
                reason = "momentum_override" if overridden else "content_dedup"
            else:
                _dedup_store(text, has_image, rule_result)
                final_tier, overridden = _apply_momentum(rule_result, text, recent_tiers, has_image)
                reason = "momentum_override" if overridden else "rule_based"
        else:
            # min_tier 场景：跳过 dedup 读写，避免把升级上下文写入缓存
            final_tier, overridden = _apply_momentum(rule_result, text, recent_tiers, has_image)
            reason = "momentum_override" if overridden else "rule_based"
    elif judge_llm is not None:
        text_hash = _hash_text(text)
        cached_tier = _cache_get(text_hash)
        if cached_tier is not None:
            final_tier = cached_tier
            reason = "llm_judge_cached"
        else:
            judged_tier = await _llm_judge_classify(text, judge_llm, judge_prompt)
            if judged_tier is None:
                # 降级（超时/异常/解析失败）：安全默认 STANDARD，且不写入任何缓存
                # ——缓存只应保存真实判定，瞬时故障不得钉死默认档位达 cache TTL。
                final_tier = RoutingTier.STANDARD
                reason = "llm_judge_unavailable"
            else:
                _cache_put(text_hash, judged_tier)
                final_tier = judged_tier
                reason = "llm_judge"
        final_tier, overridden = _apply_momentum(final_tier, text, recent_tiers, has_image)
        if overridden:
            reason = "momentum_override"
    else:
        final_tier = RoutingTier.STANDARD
        reason = "default_standard"

    if min_tier and _TIER_RANK.get(final_tier, 1) < _TIER_RANK.get(min_tier, 1):
        final_tier = min_tier
        reason = f"min_tier_escalation({reason})"

    cfg, fallback = _select_model_for_tier(final_tier, *select_args)
    logger.info(
        "Routing decision: tier=%s model=%s reason=%s",
        final_tier.value,
        cfg.model,
        reason,
    )
    return RoutingResult(tier=final_tier, model_cfg=cfg, fallback_model_cfg=fallback, reason=reason)
