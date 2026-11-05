"""LLM-visible description of memory_search_tool, derived from the corpus policy.

The description names exactly the corpora the policy enables, in the order the schema offers them. When there is only
one corpus there is nothing to choose, so the schema carries no ``corpus`` argument and the description carries no
corpus guide. The sessions routing triggers live here and nowhere else, so they are present exactly when sessions
can be searched.

[INPUT]
- toolkits.memory.agent_surface.memory_search_policy (POS: the corpora a policy enables and the schema offers)

[OUTPUT]
- build_memory_search_description_en / build_memory_search_description_zh: memory_search_tool description for a policy

[POS]
Search half of the memory tool description SSOT; ``_memory_agent_tool_descriptions`` picks the locale.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from myrm_agent_harness.toolkits.memory.agent_surface.memory_search_policy import (
    ConcreteSearchCorpus,
    MemorySearchCorpus,
    MemorySearchPolicy,
    advertised_search_corpora,
    enabled_search_corpora,
)

_SCOPE_EN: Mapping[ConcreteSearchCorpus, str] = {
    "memory": "long-term memory",
    "wiki": "wiki",
    "sessions": "prior conversations",
}
_CONTEXT_EN: Mapping[ConcreteSearchCorpus, tuple[str, ...]] = {
    "memory": ("personal context", "preferences"),
    "wiki": ("wiki docs",),
    "sessions": ("earlier chat evidence",),
}
_GUIDE_EN: Mapping[MemorySearchCorpus, str] = {
    "memory": "- memory (default): durable facts, preferences, profile, learned rules",
    "wiki": "- wiki: agent wiki vault content",
    "sessions": (
        "- sessions: prior conversations — earlier decisions, branch/fork context, "
        'or "last time" / "previously" / "continue that discussion"'
    ),
    "all": "- all: every enabled corpus",
}

_SCOPE_ZH: Mapping[ConcreteSearchCorpus, str] = {"memory": "长期记忆", "wiki": "Wiki", "sessions": "历史会话"}
_CONTEXT_ZH: Mapping[ConcreteSearchCorpus, tuple[str, ...]] = {
    "memory": ("个人上下文", "偏好"),
    "wiki": ("Wiki 文档",),
    "sessions": ("早期聊天证据",),
}
_GUIDE_ZH: Mapping[MemorySearchCorpus, str] = {
    "memory": "- memory（默认）：持久事实、偏好、profile、已学规则",
    "wiki": "- wiki：Agent Wiki vault",
    "sessions": "- sessions：历史会话 — 先前的决定、分支/fork 上下文，或「上次」「之前」「接着聊」",
    "all": "- all：当前启用的全部 corpus",
}


def _join_en(fragments: Sequence[str]) -> str:
    if len(fragments) <= 2:
        return " and ".join(fragments)
    return f"{', '.join(fragments[:-1])}, and {fragments[-1]}"


def _join_zh(fragments: Sequence[str]) -> str:
    return "、".join(fragments[:-1]) + f"与{fragments[-1]}" if len(fragments) > 1 else fragments[0]


def build_memory_search_description_en(policy: MemorySearchPolicy) -> str:
    """English description; names the corpora ``policy`` enables."""
    enabled = enabled_search_corpora(policy)
    advertised = advertised_search_corpora(policy)
    has_choice = len(advertised) > 1
    tips = [
        '- Be specific: "user\'s Python framework preference" not just "Python"',
        "- Filter domain for scoped partition: user, assistant, task",
        f"- Filter categories{' for the memory corpus' if has_choice else ''}: knowledge, claim, event, preference, rule",
        f"- Use profile_key for instant attribute lookup{' (memory corpus only)' if has_choice else ''}",
        "- Use since/until for time-scoped queries (7d, 2w, 1m, 24h, 1y, or ISO 8601)",
    ]
    if "sessions" in enabled:
        tips.append('- For recent chats without a query, use corpus=sessions with query="*"')
        tips.append(
            "- When a sessions hit includes message_id and the user needs verbatim detail, "
            "call again with corpus=sessions, expand_conversation_id, and expand_message_id"
        )
    sections = [
        f"Search {_join_en([_SCOPE_EN[corpus] for corpus in enabled])}.",
        f"Use when the user's question relates to {_join_en([part for corpus in enabled for part in _CONTEXT_EN[corpus]])}.",
    ]
    if has_choice:
        sections.append("**Corpus guide**:\n" + "\n".join(_GUIDE_EN[corpus] for corpus in advertised))
    sections.append("**Search tips**:\n" + "\n".join(tips))
    return "\n\n".join(sections)


def build_memory_search_description_zh(policy: MemorySearchPolicy) -> str:
    """Chinese description; names the corpora ``policy`` enables."""
    enabled = enabled_search_corpora(policy)
    advertised = advertised_search_corpora(policy)
    has_choice = len(advertised) > 1
    tips = [
        "- 要具体：「user's Python framework preference」而非仅「Python」",
        "- domain 过滤认知域：user（用户画像/偏好）、assistant（助手身份/规范）、task（任务规约/避坑）",
        f"- {'memory corpus ' if has_choice else ''}过滤类别：knowledge、claim、event、preference、rule",
        f"- profile_key 可即时查属性{'（仅 memory corpus）' if has_choice else ''}",
        "- since/until 时间范围：7d、2w、1m、24h、1y 或 ISO 8601",
    ]
    if "sessions" in enabled:
        tips.append('- 查最近聊天无 query：corpus=sessions，query="*"')
        tips.append(
            "- sessions 结果含 message_id 且用户要原文细节时，用 corpus=sessions 并传 expand_conversation_id 与 expand_message_id 再查"
        )
    sections = [
        f"检索{_join_zh([_SCOPE_ZH[corpus] for corpus in enabled])}。",
        f"当用户问题涉及{'、'.join(part for corpus in enabled for part in _CONTEXT_ZH[corpus])}时使用。",
    ]
    if has_choice:
        sections.append("**Corpus 指南**：\n" + "\n".join(_GUIDE_ZH[corpus] for corpus in advertised))
    sections.append("**搜索技巧**：\n" + "\n".join(tips))
    return "\n\n".join(sections)
