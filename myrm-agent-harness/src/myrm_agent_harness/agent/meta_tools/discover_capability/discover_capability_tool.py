"""统一能力发现元工具 (Unified Capability Discovery)

[INPUT]
- backends.skills.types::SkillMetadata (POS: 技能元数据定义)
- langchain.tools::tool (POS: LangChain 工具装饰器)
- pydantic::BaseModel, Field (POS: 参数验证)
- agent.meta_tools.skills.search.engine::SkillSearchEngine (POS: BM25/Regex 搜索引擎)
- agent.tool_management.registry::ToolRegistry (POS: 工具注册表，由 sync_discover_capability_tool 使用)

[OUTPUT]
- create_discover_capability_tool: 创建统一能力发现工具的工厂函数
- sync_discover_capability_tool: 条件注册 skill_search_tool（hidden_skill_count > 0 时）
- 运行时命中结果以 `<BoundSkills>` XML 包裹

[POS]
Unified Capability Discovery meta-tool. Indexes agent-bound searchable skills (MCP PTC + user skills)
via SkillSearchEngine into a BM25 (lexical) search index.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from langchain.tools import tool
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

    from myrm_agent_harness.agent.meta_tools.skills.search.engine import SkillSearchEngine

from myrm_agent_harness.agent.tool_management.registry import ToolRegistry
from myrm_agent_harness.backends.skills.types import SkillMetadata
from myrm_agent_harness.utils.locale import is_chinese

_MARKET_INSTALLED_LINE_EN = "NOT for installing new skills from external markets — use `skill_market_tool` for that."
_MARKET_OFF_LINE_EN = (
    "NOT for installing new skills from external markets. "
    "Install skills via product Settings → Skills → Discover, "
    "or enable the Skill Market capability on this agent profile."
)

_MARKET_INSTALLED_LINE_ZH = "本工具**不用于**从外部市场安装新技能 — 如需安装新技能请使用 `skill_market_tool`。"
_MARKET_OFF_LINE_ZH = (
    "本工具**不用于**从外部市场安装新技能。如需安装新技能请前往设置 → 技能库发现，或在 Agent 配置中开启技能市场。"
)


def _build_tool_description(*, market_tool_mounted: bool, locale: str | None = None) -> str:
    if is_chinese(locale):
        market_line = _MARKET_INSTALLED_LINE_ZH if market_tool_mounted else _MARKET_OFF_LINE_ZH
        return f"""在当前 Agent 已绑定的技能库中搜索所需的专业能力与流程规范（包含领域技能与扩展集成）。
{market_line}

重要：在因缺少能力而拒绝用户请求前，必须先在此搜索。切勿在未检查是否存在可用技能前宣称无法完成某项任务（如绘图、视频生成、GitHub、Jira 等）。

**查询方式**：
- 索引里的技能名与描述以英文为主、按词匹配：请用英文关键词检索并补上同义词；只写其他语言的词经常搜不到。
- 跨语言最佳效果格式："概念/翻译/同义词"（例如："火车票/railway ticket/train booking"）。
- 精确名字：`select:<skill_name>`（不参与 BM25）。
- 必含词：`+term query`（term 必须出现在索引中）。
- 使用 query="*" 列出所有已绑定的可搜索技能。

**后续操作**：
- 如果用户已点名技能，直接使用 `skill_select_tool`；只有名称未知时才先搜索。
- 命中技能后，必须使用 `skill_select_tool` 加载其 SOP 文档后再执行。

**示例**：视频生成、GitHub 集成、数据库操作。
"""

    market_line = _MARKET_INSTALLED_LINE_EN if market_tool_mounted else _MARKET_OFF_LINE_EN
    return f"""Search for missing capabilities among skills already available to this agent (bound library, domain skills, and extensions).
{market_line}

IMPORTANT: You MUST search here BEFORE declining any user request due to missing capability. Never tell the user you cannot do something without first checking if a skill exists (e.g., drawing, video generation, Github, Jira, etc.).

**How to query**:
- Skill names and descriptions are indexed mostly in English and matched word by word: write English keywords and add synonyms. A query in another language alone often finds nothing.
- For best results across languages, use format: "concept/translation/synonym" (e.g., "火车票/railway ticket/train booking").
- Exact name: `select:<skill_name>` (bypasses BM25).
- Required term: `+term query` (the term must appear in the index).
- Use query="*" to list all searchable skills bound to this agent.

**What happens next**:
- If the user named a skill, call `skill_select_tool` directly; search only when the name is unknown.
- If a **skill** is found, you MUST use `skill_select_tool` to load its SOP documentation before using it.

**Examples**: video generation, GitHub integration, database operations.
"""


def create_discover_capability_tool(
    skills: list[SkillMetadata] | None = None,
    *,
    market_tool_mounted: bool = False,
    locale: str | None = None,
) -> BaseTool:
    """创建统一能力发现工具

    Args:
        skills: 全部可用技能列表 (用于构建 agent 已绑定技能搜索索引)
        market_tool_mounted: Whether skill_market_tool is Turn1-mounted on this agent.

    Returns:
        discover_capability 工具函数
    """
    all_skills = list(skills or [])
    engine: SkillSearchEngine | None = None
    if all_skills:
        from myrm_agent_harness.agent.meta_tools.skills.search.engine import SkillSearchEngine

        engine = SkillSearchEngine(all_skills)

    tool_description = _build_tool_description(market_tool_mounted=market_tool_mounted, locale=locale)

    class DiscoverCapabilityInput(BaseModel):
        query: str = Field(
            description=(
                "Search query: English keywords plus synonyms (a query in another language alone often finds nothing). "
                "Use 'concept/translation/synonym' format for best results. "
                "Use 'select:<skill_name>' for an exact name, '+term query' to require a term, "
                "or '*' to list all skills."
            )
        )
        mode: Literal["bm25", "regex"] = Field(
            default="bm25",
            description="Search mode: 'bm25' for natural language, 'regex' for pattern matching",
        )

    @tool(
        "skill_search_tool",
        description=tool_description,
        args_schema=DiscoverCapabilityInput,
    )
    async def discover_capability_func(query: str, mode: Literal["bm25", "regex"] = "bm25") -> str:
        """Search for capabilities among skills bound to this agent."""
        full_list_hint = (
            f"; query='*' lists all {len(all_skills)} bound skills (a long list, use it last)" if all_skills else ""
        )
        not_found = (
            f"No capabilities found matching '{query}'. Retry with English keywords or synonyms{full_list_hint}."
        )

        if engine is None:
            return not_found

        if mode == "regex":
            matches = engine.search_regex(query)
        else:
            matches = engine.search_bm25(query, top_k=10)

        if not matches:
            return not_found

        skill_text = "\n".join(f"- **{s.name}**: {s.description}" for s in matches)
        listing = (
            "### Found bound skills (You MUST use `skill_select_tool` to load their SOPs before using):\n"
            f"<BoundSkills>\n{skill_text}\n</BoundSkills>"
        )
        if query.strip() == "*":
            return listing
        return f"{listing}\nIf none of these fit, search again with English keywords or synonyms."

    return discover_capability_func


def sync_discover_capability_tool(
    registry: ToolRegistry,
    *,
    skills: list[SkillMetadata] | None = None,
    skill_configs: dict[str, dict[str, object]] | None = None,
    available_tool_names: frozenset[str] | None = None,
    available_tool_groups: frozenset[str] | None = None,
    locale: str | None = None,
) -> BaseTool | None:
    """Register skill_search_tool when inline catalog has hidden bound skills.

    Must run after all tools (framework + server) are registered.
    Uses the same catalog resolution as ``ensure_skill_catalog_in_messages``.
    """
    from myrm_agent_harness.agent.skills.runtime.catalog_display import (
        resolve_catalog_display_skills,
        should_mount_skill_search_tool,
    )
    from myrm_agent_harness.agent.tool_management.types import ToolSource

    bound_skills = skills or []
    registry.remove_tool("skill_search_tool")

    if not should_mount_skill_search_tool(
        bound_skills,
        skill_configs=skill_configs,
        available_tool_names=available_tool_names,
        available_tool_groups=available_tool_groups,
    ):
        return None

    resolution = resolve_catalog_display_skills(
        bound_skills,
        skill_configs=skill_configs,
        available_tool_names=available_tool_names,
        available_tool_groups=available_tool_groups,
    )
    discoverable_skills = [s for s in resolution.filtered_skills if s.model_invocable and s.available]
    if not discoverable_skills:
        return None

    market_tool_mounted = registry.has_tool("skill_market_tool")

    tool = create_discover_capability_tool(
        skills=discoverable_skills,
        market_tool_mounted=market_tool_mounted,
        locale=locale,
    )
    registry.register(tool, source=ToolSource.META)
    return tool
