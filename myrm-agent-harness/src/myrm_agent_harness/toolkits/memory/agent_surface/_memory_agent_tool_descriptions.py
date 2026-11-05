"""LLM-visible descriptions for memory agent tools (prompt/cache SSOT).

Kept separate from the ``memory_agent_tools`` package so static tests can import
descriptions without pulling MemoryManager or search execution dependencies.

English and Chinese variants are both first-class LLM-facing strings.
Default locale is English; callers pass BCP-47 locale strings (e.g. ``zh-CN``).

[INPUT]
- toolkits.memory.agent_surface.memory_search_policy::MemorySearchPolicy (POS: corpus ACL for memory_search_tool)
- toolkits.memory.agent_surface._memory_tool_texts_en / _memory_tool_texts_zh (POS: static EN/ZH description texts)
- utils.locale::is_chinese (POS: BCP-47 Chinese detection for description locale)

[OUTPUT]
- build_memory_search_tool_description: Dynamic memory_search_tool description builder
- build_memory_save_tool_description: Dynamic memory_save_tool description (policy + approval)
- resolve_memory_save_tool_description / resolve_memory_manage_tool_description
- MEMORY_SAVE_CORE_* / MEMORY_*_TOOL_DESCRIPTION_EN / _ZH: locale-specific SSOT constants

[POS]
Prompt SSOT for memory agent tools. Imported by memory_agent_tools/, mcp_server/ (memory_manage/memory_store with surface=mcp), and static tests.
"""

from __future__ import annotations

from typing import Literal

from myrm_agent_harness.toolkits.memory.agent_surface._memory_tool_texts_en import (
    MEMORY_MANAGE_TOOL_DESCRIPTION_EN,
    MEMORY_SAVE_CORE_EN,
)
from myrm_agent_harness.toolkits.memory.agent_surface._memory_tool_texts_zh import (
    MEMORY_MANAGE_TOOL_DESCRIPTION_ZH,
    MEMORY_SAVE_CORE_ZH,
)
from myrm_agent_harness.toolkits.memory.agent_surface.memory_search_policy import (
    MemorySearchPolicy,
)
from myrm_agent_harness.toolkits.memory.agent_surface.wiki_memory_boundary import (
    WIKI_MEMORY_SAVE_MAX_CHARS,
    WIKI_MEMORY_SAVE_MIN_HEADINGS,
)
from myrm_agent_harness.utils.locale import is_chinese

DEFAULT_MEMORY_TOOL_DESCRIPTION_LOCALE = "en"

MemoryToolDescriptionSurface = Literal["agent", "mcp"]

_AGENT_TO_MCP_TOOL_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("memory_manage_tool", "memory_manage"),
    ("memory_search_tool", "memory_recall"),
    ("memory_save_tool", "memory_store"),
)

_MCP_SURFACE_EXTRA_REPLACEMENTS_EN: tuple[tuple[str, str], ...] = (
    (
        "Task progress, session outcomes, or completed-work logs → use memory_recall with corpus=sessions",
        "Task progress, session outcomes, or completed-work logs → do not store via memory_store",
    ),
    (
        "Task progress or chat history → memory_recall with corpus=sessions",
        "Task progress or chat history → do not use memory_manage for session logs",
    ),
    (
        "- Use wiki_ingest_tool for articles, notes, or long reference text. Memory is for short durable facts.",
        "- Long-form articles, notes, or reference text are not appropriate for memory. "
        "Memory is for short durable facts.",
    ),
)

_MCP_SURFACE_EXTRA_REPLACEMENTS_ZH: tuple[tuple[str, str], ...] = (
    (
        "任务进度、会话结果、已完成工作日志 → 使用 memory_recall，corpus=sessions",
        "任务进度、会话结果、已完成工作日志 → 不要用 memory_store 存储",
    ),
    (
        "任务进度或聊天历史 → memory_recall，corpus=sessions",
        "任务进度或聊天历史 → 不要用 memory_manage 管理会话日志",
    ),
    (
        "- 长文/笔记/参考资料请用 wiki_ingest_tool；memory 只存短小的持久事实。",
        "- 长文/笔记/参考资料不属于 memory；memory 只存短小的持久事实。",
    ),
)


def _apply_tool_surface_names(
    description: str,
    *,
    surface: MemoryToolDescriptionSurface = "agent",
    locale: str | None = DEFAULT_MEMORY_TOOL_DESCRIPTION_LOCALE,
) -> str:
    """Map GUI Turn1 tool names to MCP HTTP tool names when surface is mcp."""
    if surface == "agent":
        return description
    result = description
    for agent_name, mcp_name in _AGENT_TO_MCP_TOOL_REPLACEMENTS:
        result = result.replace(agent_name, mcp_name)
    extras = _MCP_SURFACE_EXTRA_REPLACEMENTS_ZH if is_chinese(locale) else _MCP_SURFACE_EXTRA_REPLACEMENTS_EN
    for old, new in extras:
        result = result.replace(old, new)
    return result


# Locale aliases of the save core and the default (English) aliases.
MEMORY_SAVE_TOOL_DESCRIPTION_EN = MEMORY_SAVE_CORE_EN
MEMORY_SAVE_TOOL_DESCRIPTION_ZH = MEMORY_SAVE_CORE_ZH
MEMORY_SAVE_TOOL_DESCRIPTION = MEMORY_SAVE_TOOL_DESCRIPTION_EN
MEMORY_MANAGE_TOOL_DESCRIPTION = MEMORY_MANAGE_TOOL_DESCRIPTION_EN


def _join_scope_fragments(fragments: list[str]) -> str:
    if not fragments:
        return ""
    if len(fragments) == 1:
        return fragments[0]
    if len(fragments) == 2:
        return f"{fragments[0]} and {fragments[1]}"
    return ", ".join(fragments[:-1]) + f", and {fragments[-1]}"


def _build_memory_search_en(policy: MemorySearchPolicy) -> str:
    scope_fragments = ["long-term memory"]
    if policy.allow_wiki:
        scope_fragments.append("wiki")
    if policy.allow_sessions:
        scope_fragments.append("prior conversations")

    corpus_lines = [
        "- memory (default): durable facts, preferences, profile, learned rules",
    ]
    if policy.allow_sessions:
        corpus_lines.append("- sessions: prior chat snippets and summaries")
    if policy.allow_wiki:
        corpus_lines.append("- wiki: agent wiki vault content")
    corpus_lines.append("- all: search every corpus enabled for this agent")

    tip_lines = [
        '- Be specific: "user\'s Python framework preference" not just "Python"',
        "- Filter domain for scoped partition: user, assistant, task",
        "- Filter categories for memory corpus: knowledge, claim, event, preference, rule",
        "- Use profile_key for instant attribute lookup (memory corpus only)",
        "- Use since/until for time-scoped queries (7d, 2w, 1m, 24h, 1y, or ISO 8601)",
        "- For memory retrieval only.",
    ]
    if policy.allow_sessions:
        tip_lines.append('- For recent chats without a query, use corpus=sessions with query="*"')
        tip_lines.append(
            "- When a sessions hit includes message_id and the user needs verbatim detail, "
            "call again with corpus=sessions, expand_conversation_id, and expand_message_id"
        )

    context_parts = ["personal context", "preferences"]
    if policy.allow_wiki:
        context_parts.append("wiki docs")
    if policy.allow_sessions:
        context_parts.append("earlier chat evidence")

    return (
        f"Unified search across {_join_scope_fragments(scope_fragments)}.\n\n"
        f"Use when the user's question relates to {_join_scope_fragments(context_parts)}.\n\n"
        "**Corpus guide**:\n" + "\n".join(corpus_lines) + "\n\n**Search tips**:\n" + "\n".join(tip_lines)
    )


def _build_memory_search_zh(policy: MemorySearchPolicy) -> str:
    scope_fragments = ["长期记忆"]
    if policy.allow_wiki:
        scope_fragments.append("Wiki")
    if policy.allow_sessions:
        scope_fragments.append("历史会话")

    corpus_lines = [
        "- memory（默认）：持久事实、偏好、profile、已学规则",
    ]
    if policy.allow_sessions:
        corpus_lines.append("- sessions：历史聊天片段与摘要")
    if policy.allow_wiki:
        corpus_lines.append("- wiki：Agent Wiki vault")
    corpus_lines.append("- all：搜索当前 Agent 启用的全部 corpus")

    tip_lines = [
        "- 要具体：「user's Python framework preference」而非仅「Python」",
        "- domain 过滤认知域：user（用户画像/偏好）、assistant（助手身份/规范）、task（任务规约/避坑）",
        "- memory corpus 过滤类别：knowledge、claim、event、preference、rule",
        "- profile_key 可即时查属性（仅 memory corpus）",
        "- since/until 时间范围：7d、2w、1m、24h、1y 或 ISO 8601",
        "- 仅用于记忆检索。",
    ]
    if policy.allow_sessions:
        tip_lines.append('- 查最近聊天无 query：corpus=sessions，query="*"')
        tip_lines.append(
            "- sessions 结果含 message_id 且用户要原文细节时，用 corpus=sessions 并传 expand_conversation_id 与 expand_message_id 再查"
        )

    context_parts = ["个人上下文", "偏好"]
    if policy.allow_wiki:
        context_parts.append("Wiki 文档")
    if policy.allow_sessions:
        context_parts.append("早期聊天证据")

    zh_join = "、".join(scope_fragments[:-1]) + (
        f"与{scope_fragments[-1]}" if len(scope_fragments) > 1 else scope_fragments[0]
    )
    context_join = "、".join(context_parts)

    return (
        f"跨{zh_join}的统一检索。\n\n"
        f"当用户问题涉及{context_join}时使用。\n\n"
        "**Corpus 指南**：\n" + "\n".join(corpus_lines) + "\n\n**搜索技巧**：\n" + "\n".join(tip_lines)
    )


def build_memory_search_tool_description(
    policy: MemorySearchPolicy,
    *,
    locale: str | None = DEFAULT_MEMORY_TOOL_DESCRIPTION_LOCALE,
) -> str:
    """Build memory_search_tool description (corpus ACL varies by policy)."""
    if is_chinese(locale):
        return _build_memory_search_zh(policy)
    return _build_memory_search_en(policy)


def _wiki_boundary_fragment_en() -> str:
    return (
        f"**WIKI BOUNDARY** (wiki corpus enabled):\n"
        f"- For knowledge/event only: do not save document-like content "
        f"(≥{WIKI_MEMORY_SAVE_MAX_CHARS} characters or ≥{WIKI_MEMORY_SAVE_MIN_HEADINGS} markdown headings).\n"
        "- Use wiki_ingest_tool for articles, notes, or long reference text. "
        "Memory is for short durable facts."
    )


def _wiki_boundary_fragment_zh() -> str:
    return (
        f"**Wiki 边界**（已启用 wiki corpus）：\n"
        f"- 仅 knowledge/event：不要保存文档式内容"
        f"（≥{WIKI_MEMORY_SAVE_MAX_CHARS} 字符或 ≥{WIKI_MEMORY_SAVE_MIN_HEADINGS} 个 markdown 标题）。\n"
        "- 长文/笔记/参考资料请用 wiki_ingest_tool；memory 只存短小的持久事实。"
    )


def _approval_fragment_en() -> str:
    return (
        "**APPROVAL**: When user confirmation is required, the tool may return "
        '"submitted for approval" — the memory is not active until the user approves.'
    )


def _approval_fragment_zh() -> str:
    return "**审批**：若需用户确认，工具可能返回「submitted for approval」——在用户批准前该记忆不会生效。"


def build_memory_save_tool_description(
    policy: MemorySearchPolicy,
    *,
    approval_required: bool = False,
    locale: str | None = DEFAULT_MEMORY_TOOL_DESCRIPTION_LOCALE,
    surface: MemoryToolDescriptionSurface = "agent",
) -> str:
    """Build memory_save_tool description (wiki boundary + approval vary by runtime)."""
    parts: list[str] = [MEMORY_SAVE_CORE_ZH if is_chinese(locale) else MEMORY_SAVE_CORE_EN]
    if policy.allow_wiki:
        parts.append(_wiki_boundary_fragment_zh() if is_chinese(locale) else _wiki_boundary_fragment_en())
    if approval_required:
        parts.append(_approval_fragment_zh() if is_chinese(locale) else _approval_fragment_en())
    return _apply_tool_surface_names("\n\n".join(parts), surface=surface, locale=locale)


def build_mcp_memory_store_tool_description(
    *,
    wiki_boundary_in_description: bool = False,
    approval_required: bool = False,
    locale: str | None = DEFAULT_MEMORY_TOOL_DESCRIPTION_LOCALE,
) -> str:
    """Build memory_store MCP @tool description from save SSOT core.

    The wiki boundary fragment is excluded by default: the MCP surface exposes
    no wiki tools, and the runtime wiki guard is enabled per-request by the
    server (ContextVar), so a static "(wiki corpus enabled)" claim would be
    false for most connected agents. Callers that manage their own per-agent
    wiki enablement may opt in via ``wiki_boundary_in_description``.
    """
    policy = MemorySearchPolicy(allow_wiki=wiki_boundary_in_description)
    return build_memory_save_tool_description(
        policy,
        approval_required=approval_required,
        locale=locale,
        surface="mcp",
    )


def resolve_memory_save_tool_description(
    locale: str | None = DEFAULT_MEMORY_TOOL_DESCRIPTION_LOCALE,
    *,
    surface: MemoryToolDescriptionSurface = "agent",
) -> str:
    return build_memory_save_tool_description(
        MemorySearchPolicy(),
        locale=locale,
        surface=surface,
    )


def resolve_memory_manage_tool_description(
    locale: str | None = DEFAULT_MEMORY_TOOL_DESCRIPTION_LOCALE,
    *,
    surface: MemoryToolDescriptionSurface = "agent",
) -> str:
    base = MEMORY_MANAGE_TOOL_DESCRIPTION_ZH if is_chinese(locale) else MEMORY_MANAGE_TOOL_DESCRIPTION_EN
    return _apply_tool_surface_names(base, surface=surface, locale=locale)


__all__ = [
    "DEFAULT_MEMORY_TOOL_DESCRIPTION_LOCALE",
    "MEMORY_MANAGE_TOOL_DESCRIPTION",
    "MEMORY_MANAGE_TOOL_DESCRIPTION_EN",
    "MEMORY_MANAGE_TOOL_DESCRIPTION_ZH",
    "MEMORY_SAVE_CORE_EN",
    "MEMORY_SAVE_CORE_ZH",
    "MEMORY_SAVE_TOOL_DESCRIPTION",
    "MEMORY_SAVE_TOOL_DESCRIPTION_EN",
    "MEMORY_SAVE_TOOL_DESCRIPTION_ZH",
    "MemoryToolDescriptionSurface",
    "build_mcp_memory_store_tool_description",
    "build_memory_save_tool_description",
    "build_memory_search_tool_description",
    "resolve_memory_manage_tool_description",
    "resolve_memory_save_tool_description",
]
