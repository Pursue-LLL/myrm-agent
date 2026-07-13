"""Product surface SSOT — hidden agents, templates, and removed feature keys.

[INPUT]
app.services.features.registration::FeatureStage.REMOVED (POS: deep_research 产品面关闭策略)

[OUTPUT]
HIDDEN_BUILTIN_AGENT_IDS / HIDDEN_PREBUILT_TEMPLATE_IDS / REMOVED_FEATURE_OVERRIDE_KEYS
及 is_hidden_* 判定函数。

[POS]
Deep Research 等产品隐藏策略的 Server 层单一事实源；API 列表与模板 API 过滤入口。
"""

from __future__ import annotations

HIDDEN_BUILTIN_AGENT_IDS: frozenset[str] = frozenset(
    {
        "builtin-researcher",
        "builtin-deep-search",
    }
)

HIDDEN_PREBUILT_TEMPLATE_IDS: frozenset[str] = frozenset(
    {
        "research_analysis_squad",
    }
)

REMOVED_FEATURE_OVERRIDE_KEYS: frozenset[str] = frozenset(
    {
        "deep_research",
    }
)


def is_hidden_builtin_agent(agent_id: str) -> bool:
    return agent_id in HIDDEN_BUILTIN_AGENT_IDS


def is_hidden_prebuilt_template(template_id: str) -> bool:
    return template_id in HIDDEN_PREBUILT_TEMPLATE_IDS
