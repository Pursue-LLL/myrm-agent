"""GeneralAgent 核心系统提示词

[INPUT]
app.ai_agents.prompts.shared_rules (POS: 跨 Agent 共享规则常量)

[OUTPUT]
get_core_system_prompt(mode): 按三档模式返回核心 System Prompt
CORE_SYSTEM_PROMPT: full 模式预构建常量
get_citation_rules_if_needed: 条件返回引用规则

[POS]
GeneralAgent 核心系统提示词。支持四档 Prompt Mode（full/lean/naked/search），
同一 mode 的 prompt 字符串跨用户稳定以最大化 KV Cache 命中率。
通用防御规则（XML 防御、上下文优先、工具使用纪律等）由框架层
model_discipline.py 的 AGENT_CORE_RULES 提供，此处仅包含业务层特有的
身份定义和 answer_tool 自审规则。工具感知规则（如 MEMORY_RULES）仅在
对应工具可用时注入，避免提示词引用不存在的工具。
"""

from typing import Literal

from app.ai_agents.prompts.shared_rules import (
    ABSOLUTE_OBEDIENCE_RULES,
    EXTERNAL_SOURCES_CITATION_RULES,
    MEMORY_RULES,
    RESPONSE_RULES,
    SECURITY_RULES,
    TASK_INTEGRITY_RULES,
)

PromptMode = Literal["full", "lean", "naked", "search"]

# =============================================================================
# Search mode prompt (FastSearch 走 GeneralAgent 统一路径时使用)
# =============================================================================

from app.ai_agents.prompts.fast_search_agent_prompt import (  # noqa: E402
    get_fast_search_agent_prompt as _build_search_prompt,
)

_SEARCH_PROMPT_BASE: str = _build_search_prompt(search_depth="normal")
SEARCH_DEEP_SUFFIX: str = _build_search_prompt(search_depth="deep")[len(_SEARCH_PROMPT_BASE) :]

# =============================================================================
# Layer 1: 核心系统提示词（永远不变）
# =============================================================================

# GeneralAgent 特有的身份定义
_IDENTITY_CORE = """
<identity>
你是一个功能强大且求真务实的通用AI智能助手。你的核心职责是利用你卓越的自身能力（知识、逻辑、创造力）以及丰富的外部工具和技能，为用户解决各种复杂问题和任务。

你的目标是成为用户最得力的全能助手，你可以灵活选择和组合合适的工具和技能，为用户处理任意类型的任务。
你致力于为用户提供超高质量的、有用、全面、**事实准确**、高时效性的答案，让用户惊叹于你的高质量回答，绝不提供平庸或过时的答案，这是你的服务宗旨。
"""

_IDENTITY_SUFFIX_WITH_ANSWER_TOOL = """
当达到可回复条件时，必须先调用 request_answer_user_tool 工具请求回答用户。
</identity>
"""

_IDENTITY_SUFFIX_WITHOUT_ANSWER_TOOL = """
</identity>
"""

_RULESET_WITH_ANSWER_TOOL = """
<ruleset>
  <rule name="answer_tool_required" priority="high">
    当达到可回复条件时，必须调用 request_answer_user_tool 自审通过后才能回答用户。
    例外：简单问候、文本处理、基础计算、不涉及时效性的常识解释。
  </rule>
  <rule name="explicit_tool_request" priority="high">
    用户明确要求调用具体工具时，必须立即调用，不能直接回答。
  </rule>
</ruleset>
"""

_RULESET_WITHOUT_ANSWER_TOOL = """
<ruleset>
  <rule name="explicit_tool_request" priority="high">
    用户明确要求调用具体工具时，必须立即调用，不能直接回答。
  </rule>
</ruleset>
"""


def _build_identity_and_rules(enable_answer_tool: bool) -> str:
    suffix = _IDENTITY_SUFFIX_WITH_ANSWER_TOOL if enable_answer_tool else _IDENTITY_SUFFIX_WITHOUT_ANSWER_TOOL
    ruleset = _RULESET_WITH_ANSWER_TOOL if enable_answer_tool else _RULESET_WITHOUT_ANSWER_TOOL
    return f"{_IDENTITY_CORE}{suffix}{ruleset}"


_IDENTITY_AND_RULES = _build_identity_and_rules(enable_answer_tool=True)
_IDENTITY_AND_RULES_NO_ANSWER = _build_identity_and_rules(enable_answer_tool=False)

_NAKED_TOOL_GUIDANCE = """
<tool_guidance>
When you need to perform actions, use the available tools via Function Calling API.
Do NOT output tool calls as XML tags in your response text.
</tool_guidance>
"""


def _build_prompt_map(
    identity: str,
    *,
    include_memory_rules: bool = True,
) -> dict[PromptMode, str]:
    full_parts = [identity, ABSOLUTE_OBEDIENCE_RULES, RESPONSE_RULES, SECURITY_RULES, TASK_INTEGRITY_RULES]
    if include_memory_rules:
        full_parts.append(MEMORY_RULES)

    return {
        "full": "\n".join(full_parts),
        "lean": f"{identity}\n{SECURITY_RULES}\n{TASK_INTEGRITY_RULES}",
        "naked": f"{SECURITY_RULES}\n{_NAKED_TOOL_GUIDANCE}",
        "search": _SEARCH_PROMPT_BASE,
    }


# 预构建 4 个静态 Map（enable_answer_tool × enable_memory），
# 每个组合跨用户始终返回同一字符串对象以保证 KV Cache 稳定。
_PROMPT_MAPS: dict[tuple[bool, bool], dict[PromptMode, str]] = {
    (True, True): _build_prompt_map(_IDENTITY_AND_RULES, include_memory_rules=True),
    (True, False): _build_prompt_map(_IDENTITY_AND_RULES, include_memory_rules=False),
    (False, True): _build_prompt_map(_IDENTITY_AND_RULES_NO_ANSWER, include_memory_rules=True),
    (False, False): _build_prompt_map(_IDENTITY_AND_RULES_NO_ANSWER, include_memory_rules=False),
}

CORE_SYSTEM_PROMPT: str = _PROMPT_MAPS[(True, True)]["full"]

# =============================================================================
# API 函数
# =============================================================================


def get_core_system_prompt(
    mode: PromptMode = "full",
    *,
    enable_answer_tool: bool = True,
    enable_memory: bool = True,
) -> str:
    """获取核心层 System Prompt (Layer 1)

    Args:
        mode: 提示词模式
            - full: 完整规则（默认），适合通用场景
            - lean: 精简规则，保留身份+安全+任务完整性
            - naked: 裸调模式，仅安全规则+工具调用指引
            - search: 搜索模式，轻量搜索专用提示词
        enable_answer_tool: 是否包含 request_answer_user_tool 引导规则
        enable_memory: 是否包含 MEMORY_RULES（memory 工具不可用时应为 False）

    Returns:
        核心 System Prompt（同一参数组合跨用户缓存稳定）
    """
    prompt_map = _PROMPT_MAPS[(enable_answer_tool, enable_memory)]
    return prompt_map.get(mode, prompt_map["full"])


def get_citation_rules_if_needed(has_external_sources: bool) -> str | None:
    """获取外部来源引用规则（如果需要）

    用于在 final_answer 阶段、当前轮次有 external_sources 时追加。

    Args:
        has_external_sources: 当前轮次是否有外部知识源

    Returns:
        引用规则内容，如果不需要则返回 None
    """
    if has_external_sources:
        return EXTERNAL_SOURCES_CITATION_RULES
    return None
