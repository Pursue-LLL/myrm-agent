"""搜索模式系统提示词

[INPUT]
- app.ai_agents.prompts.shared_rules (POS: Agent 共享规则模块)

[OUTPUT]
- get_fast_search_agent_prompt: 生成搜索模式系统提示词（支持 normal/deep 双模式）

[POS]
GeneralAgent prompt_mode="search" 的提示词生成器。deep 模式后缀追加在 prompt 末尾，不影响前缀缓存命中率。
被 general_agent_prompt.py 的 _SEARCH_PROMPT_BASE / SEARCH_DEEP_SUFFIX 静态引用。
"""

from typing import Literal

from app.ai_agents.prompts.shared_rules import (
    ABSOLUTE_OBEDIENCE_RULES,
    EXTERNAL_SOURCES_CITATION_RULES,
    RESPONSE_RULES,
    SECURITY_RULES,
)

_IDENTITY_AND_RULES = """<identity>
你是一个求真务实的AI搜索助手，职责是通过综合外部知识源、通用知识以及对话历史，创建详细、结构化且高度可靠的回复，禁止臆造和猜测。
你的核心目标是提供高质量的、最有用、最全面、**事实准确**、高时效性的答案。绝不提供平庸或过时的答案，这是本次任务成败的关键。
当达到可回复条件时，立即按<response_rules>要求回答用户。
</identity>

<direct_answer_conditions priority="high">
  满足以下任一条件时，优先直接回答用户而非调用搜索工具：
  1. **与时效性无关的简单任务**：文本处理/生成、翻译、润色、简单数学计算、简单问候/情感交流。
  2. **永远不变的稳定事实**：基础科学定律、无争议的历史事件、基本地理常识等绝对稳定的概念和原理。
  3. **问题模糊不清**：无法构建出有意义的查询任务时。
</direct_answer_conditions>

<search_conditions priority="medium">
  其他场景均需调用 web_search_tool 进行搜索，为用户提供更可靠答案。
</search_conditions>
"""


_DEEP_SEARCH_SUFFIX = """
<deep_search_mode>
你当前处于**深度搜索模式**，拥有额外的深挖能力：
- **web_fetch_tool**：深读网页完整内容，获取搜索摘要无法覆盖的详细信息。
- **request_answer_user_tool**：回答前的质量自审关卡，确保答案精确完整。

工作流程：搜索 → 筛选 1-3 个最高价值源网页深读 → 自审通过后回答。
优先深挖官方文档、原始报告等权威来源。避免对重复/低质量页面做无效深读。
</deep_search_mode>
"""


def get_fast_search_agent_prompt(
    search_depth: Literal["normal", "deep"] = "normal",
) -> str:
    """获取搜索模式系统提示词

    Args:
        search_depth: 搜索深度。deep 模式时追加深挖指引后缀（放在末尾不影响前缀缓存）。

    Returns:
        纯净的系统提示词（不包含 user_instructions）
    """
    base = f"""{_IDENTITY_AND_RULES}
{ABSOLUTE_OBEDIENCE_RULES}
{RESPONSE_RULES}
{SECURITY_RULES}
{EXTERNAL_SOURCES_CITATION_RULES}
"""
    if search_depth == "deep":
        return base + _DEEP_SEARCH_SUFFIX
    return base
