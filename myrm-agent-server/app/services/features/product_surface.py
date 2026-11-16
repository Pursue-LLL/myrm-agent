"""Product surface SSOT — hidden agents, templates, and removed feature keys.

[INPUT]
app.services.features.registration::FeatureStage.REMOVED (POS: 已下线产品面的配置清洗)

[OUTPUT]
HIDDEN_BUILTIN_AGENT_IDS / HIDDEN_PREBUILT_TEMPLATE_IDS / REMOVED_FEATURE_OVERRIDE_KEYS
及 is_hidden_* 判定函数。

[POS]
已下线产品面的 Server 层单一事实源；API 列表与模板 API 过滤入口。
"""

from __future__ import annotations

# Hidden preset ids stay out of every agent list. ``builtin-ko-office`` is a retired preset: no spec ships any more,
# so only databases created by an earlier version still hold its row, and chat requests that name it resolve to the
# general agent on the client.
HIDDEN_BUILTIN_AGENT_IDS: frozenset[str] = frozenset(
    {
        "builtin-researcher",
        "builtin-deep-search",
        "builtin-ko-office",
    }
)

HIDDEN_PREBUILT_TEMPLATE_IDS: frozenset[str] = frozenset(
    {
        "research_analysis_squad",
        "second_brain_assistant",
    }
)

REMOVED_FEATURE_OVERRIDE_KEYS: frozenset[str] = frozenset(
    {
        "consensus",
    }
)


def is_hidden_builtin_agent(agent_id: str) -> bool:
    return agent_id in HIDDEN_BUILTIN_AGENT_IDS


def is_hidden_prebuilt_template(template_id: str) -> bool:
    return template_id in HIDDEN_PREBUILT_TEMPLATE_IDS
