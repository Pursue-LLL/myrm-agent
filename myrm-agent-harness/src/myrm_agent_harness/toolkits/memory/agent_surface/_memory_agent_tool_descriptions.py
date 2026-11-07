"""LLM-visible descriptions for memory agent tools (prompt/cache SSOT).

Kept separate from the ``memory_agent_tools`` package so static tests can import
descriptions without pulling MemoryManager or search execution dependencies.

English and Chinese variants are both first-class LLM-facing strings.
Default locale is English; callers pass BCP-47 locale strings (e.g. ``zh-CN``).

[INPUT]
- toolkits.memory.agent_surface.memory_search_policy::MemorySearchPolicy (POS: corpus ACL for memory_search_tool)
- toolkits.memory.agent_surface._memory_tool_texts_en / _memory_tool_texts_zh (POS: static EN/ZH description texts)
- toolkits.memory.agent_surface._memory_search_description (POS: policy-derived search description, EN/ZH)
- utils.locale::is_chinese (POS: BCP-47 Chinese detection for description locale)

[OUTPUT]
- build_memory_search_tool_description: Dynamic memory_search_tool description builder
- build_memory_save_tool_description: Dynamic memory_save_tool description (policy + approval)
- resolve_memory_save_tool_description / resolve_memory_manage_tool_description
- MEMORY_SAVE_CORE_* / MEMORY_SAVE_WRITE_TARGET_* / MEMORY_MANAGE_TOOL_DESCRIPTION_EN / _ZH: locale-specific SSOT constants

[POS]
Prompt SSOT for memory agent tools. Imported by memory_agent_tools/, mcp_server/ (memory_manage/memory_store with surface=mcp), and static tests.
"""

from __future__ import annotations

from typing import Literal

from myrm_agent_harness.toolkits.memory.agent_surface._memory_search_description import (
    build_memory_search_description_en,
    build_memory_search_description_zh,
)
from myrm_agent_harness.toolkits.memory.agent_surface._memory_tool_texts_en import (
    MEMORY_MANAGE_TOOL_DESCRIPTION_EN,
    MEMORY_SAVE_CORE_EN,
    MEMORY_SAVE_WRITE_TARGET_EN,
)
from myrm_agent_harness.toolkits.memory.agent_surface._memory_tool_texts_zh import (
    MEMORY_MANAGE_TOOL_DESCRIPTION_ZH,
    MEMORY_SAVE_CORE_ZH,
    MEMORY_SAVE_WRITE_TARGET_ZH,
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


def _apply_tool_surface_names(description: str, *, surface: MemoryToolDescriptionSurface = "agent") -> str:
    """Map GUI Turn1 tool names to MCP HTTP tool names when surface is mcp."""
    if surface == "agent":
        return description
    result = description
    for agent_name, mcp_name in _AGENT_TO_MCP_TOOL_REPLACEMENTS:
        result = result.replace(agent_name, mcp_name)
    return result


# The save description is composed per runtime policy; only the manage description is a plain constant.
MEMORY_MANAGE_TOOL_DESCRIPTION = MEMORY_MANAGE_TOOL_DESCRIPTION_EN


def build_memory_search_tool_description(
    policy: MemorySearchPolicy,
    *,
    locale: str | None = DEFAULT_MEMORY_TOOL_DESCRIPTION_LOCALE,
) -> str:
    """Build memory_search_tool description (the corpora it names are the ones ``policy`` enables)."""
    if is_chinese(locale):
        return build_memory_search_description_zh(policy)
    return build_memory_search_description_en(policy)


def _wiki_boundary_fragment_en(surface: MemoryToolDescriptionSurface) -> str:
    # The MCP surface exposes no wiki tools, so it cannot be pointed at wiki_ingest_tool.
    redirect = (
        "- Use wiki_ingest_tool for articles, notes, or long reference text. "
        if surface == "agent"
        else "- Long-form articles, notes, or reference text are not appropriate for memory. "
    )
    return (
        f"**WIKI BOUNDARY** (wiki corpus enabled):\n"
        f"- For knowledge/event only: do not save document-like content "
        f"(≥{WIKI_MEMORY_SAVE_MAX_CHARS} characters or ≥{WIKI_MEMORY_SAVE_MIN_HEADINGS} markdown headings).\n"
        f"{redirect}Memory is for short durable facts."
    )


def _wiki_boundary_fragment_zh(surface: MemoryToolDescriptionSurface) -> str:
    redirect = (
        "- 长文/笔记/参考资料请用 wiki_ingest_tool；" if surface == "agent" else "- 长文/笔记/参考资料不属于 memory；"
    )
    return (
        f"**Wiki 边界**（已启用 wiki corpus）：\n"
        f"- 仅 knowledge/event：不要保存文档式内容"
        f"（≥{WIKI_MEMORY_SAVE_MAX_CHARS} 字符或 ≥{WIKI_MEMORY_SAVE_MIN_HEADINGS} 个 markdown 标题）。\n"
        f"{redirect}memory 只存短小的持久事实。"
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
    """Build memory_save_tool description (write target, wiki boundary and approval vary by runtime)."""
    chinese = is_chinese(locale)
    parts: list[str] = [MEMORY_SAVE_CORE_ZH if chinese else MEMORY_SAVE_CORE_EN]
    if policy.allow_shared_write:
        parts.append(MEMORY_SAVE_WRITE_TARGET_ZH if chinese else MEMORY_SAVE_WRITE_TARGET_EN)
    if policy.allow_wiki:
        parts.append(_wiki_boundary_fragment_zh(surface) if chinese else _wiki_boundary_fragment_en(surface))
    if approval_required:
        parts.append(_approval_fragment_zh() if chinese else _approval_fragment_en())
    return _apply_tool_surface_names("\n\n".join(parts), surface=surface)


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
    return _apply_tool_surface_names(base, surface=surface)


__all__ = [
    "DEFAULT_MEMORY_TOOL_DESCRIPTION_LOCALE",
    "MEMORY_MANAGE_TOOL_DESCRIPTION",
    "MEMORY_MANAGE_TOOL_DESCRIPTION_EN",
    "MEMORY_MANAGE_TOOL_DESCRIPTION_ZH",
    "MEMORY_SAVE_CORE_EN",
    "MEMORY_SAVE_CORE_ZH",
    "MEMORY_SAVE_WRITE_TARGET_EN",
    "MEMORY_SAVE_WRITE_TARGET_ZH",
    "MemoryToolDescriptionSurface",
    "build_mcp_memory_store_tool_description",
    "build_memory_save_tool_description",
    "build_memory_search_tool_description",
    "resolve_memory_manage_tool_description",
    "resolve_memory_save_tool_description",
]
