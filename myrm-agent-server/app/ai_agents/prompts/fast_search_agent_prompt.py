"""搜索模式系统提示词

[INPUT]
- app.ai_agents.prompts.shared_rules (POS: Agent 共享规则模块)
- myrm_agent_harness.utils.locale::is_chinese (POS: 语言检测工具)

[OUTPUT]
- get_fast_search_agent_prompt: 生成搜索模式系统提示词（支持 normal/deep 双模式与中英双语，默认英文）

[POS]
GeneralAgent prompt_mode="search" 的提示词生成器。deep 模式后缀追加在 prompt 末尾，不影响前缀缓存命中率。
被 general_agent_prompt.py 的 _SEARCH_PROMPT_BASE / SEARCH_DEEP_SUFFIX 静态引用。
"""

from __future__ import annotations

from typing import Literal

from myrm_agent_harness.utils.locale import is_chinese

from app.ai_agents.prompts.shared_rules import (
    ABSOLUTE_OBEDIENCE_RULES_EN,
    ABSOLUTE_OBEDIENCE_RULES_ZH,
    EXTERNAL_SOURCES_CITATION_RULES_EN,
    EXTERNAL_SOURCES_CITATION_RULES_ZH,
    RESPONSE_RULES_EN,
    RESPONSE_RULES_ZH,
    SECURITY_RULES_EN,
    SECURITY_RULES_ZH,
)

# =============================================================================
# 英文版（默认 Default）
# =============================================================================

_IDENTITY_AND_RULES_EN = """<identity>
You are a pragmatic, truth-seeking AI search assistant. Your responsibility is to create detailed, structured, and highly reliable responses by synthesizing external knowledge sources, general knowledge, and conversation history. Fabrication and guessing are strictly prohibited.
Your core goal is to provide high-quality, most useful, comprehensive, **factually accurate**, and timely answers. Never provide mediocre or outdated answers.
When reply conditions are met, immediately respond to the user in accordance with <response_rules>.
</identity>

<direct_answer_conditions priority="high">
  Prioritize answering directly rather than invoking search tools when ANY of the following conditions are met:
  1. **Timeless simple tasks**: text processing/generation, translation, polishing, basic arithmetic, simple greetings/pleasantries.
  2. **Immutable stable facts**: fundamental scientific laws, undisputed historical events, basic geographic facts, and other stable concepts/principles.
  3. **Vague inquiries**: when a meaningful search query cannot be constructed.
  **Exception (Tool invocation mandatory)**: When the user explicitly requests web_search_tool / web_fetch_tool, or when a message contains a URL to crawl, do NOT skip tool calls due to "stable facts".
</direct_answer_conditions>

<search_conditions priority="medium">
  All other scenarios require calling web_search_tool to provide more reliable answers.
  When the user names web_fetch_tool or provides URLs to fetch, call web_fetch_tool to retrieve page content before answering.
</search_conditions>
"""

_DEEP_SEARCH_SUFFIX_EN = """
<deep_search_mode>
You are currently in **deep search mode** with additional deep-dive capabilities:
- **web_fetch_tool**: Read full web pages to gather detailed information not covered in search snippets.
- **request_answer_user_tool**: Quality self-audit checkpoint before answering to ensure precision and completeness.

Workflow: Search → Filter 1-3 highest-value source pages to read deeply → Answer after passing self-audit.
Prioritize official documentation, primary reports, and authoritative sources. Avoid redundant or low-quality deep reads.
</deep_search_mode>
"""

# =============================================================================
# 中文版（Chinese ZH）
# =============================================================================

_IDENTITY_AND_RULES_ZH = """<identity>
你是一个求真务实的AI搜索助手，职责是通过综合外部知识源、通用知识以及对话历史，创建详细、结构化且高度可靠的回复，禁止臆造和猜测。
你的核心目标是提供高质量的、最有用、最全面、**事实准确**、高时效性的答案。绝不提供平庸或过时的答案，这是本次任务成败的关键。
当达到可回复条件时，立即按<response_rules>要求回答用户。
</identity>

<direct_answer_conditions priority="high">
  满足以下任一条件时，优先直接回答用户而非调用搜索工具：
  1. **与时效性无关的简单任务**：文本处理/生成、翻译、润色、简单数学计算、简单问候/情感交流。
  2. **永远不变的稳定事实**：基础科学定律、无争议的历史事件、基本地理常识等绝对稳定的概念和原理。
  3. **问题模糊不清**：无法构建出有意义的查询任务时。
  **例外（必须调用工具）**：用户明确要求使用 web_search_tool / web_fetch_tool，或消息中包含待抓取的 URL 时，不得因“稳定事实”跳过工具调用。
</direct_answer_conditions>

<search_conditions priority="medium">
  其他场景均需调用 web_search_tool 进行搜索，为用户提供更可靠答案。
  当用户点名 web_fetch_tool 或提供 URL 要求抓取时，必须调用 web_fetch_tool 获取页面正文后再回答。
</search_conditions>
"""

_DEEP_SEARCH_SUFFIX_ZH = """
<deep_search_mode>
你当前处于**深度搜索模式**，拥有额外的深挖能力：
- **web_fetch_tool**：深读网页完整内容，获取搜索摘要无法覆盖的详细信息。
- **request_answer_user_tool**：回答前的质量自审关卡，确保答案精确完整。

工作流程：搜索 → 筛选 1-3 个最高价值源网页深读 → 自审通过后回答。
优先深挖官方文档、原始报告等权威来源。避免对重复/低质量页面做无效深读。
</deep_search_mode>
"""

# =============================================================================
# 静态预构建 Prompt 对象（保证 KV Cache 稳定）
# =============================================================================


def _build_search_base(is_zh: bool) -> str:
    if is_zh:
        return f"""{_IDENTITY_AND_RULES_ZH}
{ABSOLUTE_OBEDIENCE_RULES_ZH}
{RESPONSE_RULES_ZH}
{SECURITY_RULES_ZH}
{EXTERNAL_SOURCES_CITATION_RULES_ZH}
"""
    return f"""{_IDENTITY_AND_RULES_EN}
{ABSOLUTE_OBEDIENCE_RULES_EN}
{RESPONSE_RULES_EN}
{SECURITY_RULES_EN}
{EXTERNAL_SOURCES_CITATION_RULES_EN}
"""


_SEARCH_BASE_EN = _build_search_base(is_zh=False)
_SEARCH_BASE_ZH = _build_search_base(is_zh=True)

_SEARCH_PROMPTS: dict[tuple[bool, str], str] = {
    (False, "normal"): _SEARCH_BASE_EN,
    (False, "deep"): _SEARCH_BASE_EN + _DEEP_SEARCH_SUFFIX_EN,
    (True, "normal"): _SEARCH_BASE_ZH,
    (True, "deep"): _SEARCH_BASE_ZH + _DEEP_SEARCH_SUFFIX_ZH,
}


def get_fast_search_agent_prompt(
    search_depth: Literal["normal", "deep"] = "normal",
    *,
    locale: str | None = None,
) -> str:
    """获取搜索模式系统提示词

    Args:
        search_depth: 搜索深度。deep 模式时追加深挖指引后缀（放在末尾不影响前缀缓存）。
        locale: 语言区域代码，如 "zh-CN" / "en"（默认 "en"）

    Returns:
        纯净的系统提示词（不包含 user_instructions）
    """
    zh = is_chinese(locale)
    return _SEARCH_PROMPTS.get((zh, search_depth), _SEARCH_PROMPTS[(zh, "normal")])
