"""复杂度路由门面。

[OUTPUT]
route_task / RoutingTier / RoutingResult 以及测试与内部依赖的关键词、评分、缓存函数。

[POS]
`myrm_agent_harness.toolkits.llms.routing.complexity_router` 的唯一入口；实现按关键词/类型/信号/评分/动量/judge/去重/入口拆分。
"""

from myrm_agent_harness.toolkits.llms.routing.complexity_router.dedup import (
    _dedup_cache,
    _dedup_check,
    _dedup_store,
)
from myrm_agent_harness.toolkits.llms.routing.complexity_router.judge import (
    _judge_cache,
    _select_model_for_tier,
)
from myrm_agent_harness.toolkits.llms.routing.complexity_router.keywords import (
    DEFAULT_REASONING_KEYWORDS,
    DEFAULT_SIMPLE_INDICATORS,
    DEFAULT_STANDARD_KEYWORDS,
)
from myrm_agent_harness.toolkits.llms.routing.complexity_router.momentum import _apply_momentum
from myrm_agent_harness.toolkits.llms.routing.complexity_router.route import route_task
from myrm_agent_harness.toolkits.llms.routing.complexity_router.scoring import (
    _compute_unified_score,
    _rule_based_classify,
)
from myrm_agent_harness.toolkits.llms.routing.complexity_router.signals import (
    _has_code_content,
    _has_math_content,
    _is_simple_greeting,
    _normalize_query,
    _score_contextual_signals,
    _score_structural_signals,
    _word_count,
)
from myrm_agent_harness.toolkits.llms.routing.complexity_router.types import RoutingResult, RoutingTier

__all__ = [
    "DEFAULT_REASONING_KEYWORDS",
    "DEFAULT_SIMPLE_INDICATORS",
    "DEFAULT_STANDARD_KEYWORDS",
    "RoutingResult",
    "RoutingTier",
    "_apply_momentum",
    "_compute_unified_score",
    "_dedup_cache",
    "_dedup_check",
    "_dedup_store",
    "_has_code_content",
    "_has_math_content",
    "_is_simple_greeting",
    "_judge_cache",
    "_normalize_query",
    "_rule_based_classify",
    "_score_contextual_signals",
    "_score_structural_signals",
    "_select_model_for_tier",
    "_word_count",
    "route_task",
]
