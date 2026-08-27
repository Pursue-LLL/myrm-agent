"""GeneralAgent 核心系统提示词

[INPUT]
app.ai_agents.prompts.shared_rules (POS: 跨 Agent 共享规则常量)
myrm_agent_harness.utils.locale::is_chinese (POS: 语言检测工具)

[OUTPUT]
get_core_system_prompt(mode, ...): 按模式与语言返回核心 System Prompt（默认英文）
CORE_SYSTEM_PROMPT: 默认 full 模式预构建常量
get_citation_rules_if_needed: 条件返回引用规则

[POS]
GeneralAgent 核心系统提示词。支持四档 Prompt Mode（full/lean/naked/search）与中英双语（默认英文），
同一 mode + locale 的 prompt 字符串跨用户稳定以最大化 KV Cache 命中率。
通用防御规则（XML 防御、上下文优先、工具使用纪律等）由框架层
model_discipline.py 的 AGENT_CORE_RULES 提供，此处仅包含业务层特有的
身份定义和 answer_tool 自审规则。工具感知规则（如 MEMORY_RULES）仅在
对应工具可用时注入，避免提示词引用不存在的工具。
"""

from __future__ import annotations

from typing import Literal

from myrm_agent_harness.utils.locale import is_chinese

from app.ai_agents.prompts.fast_search_agent_prompt import (
    _DEEP_SEARCH_SUFFIX_EN,
    _DEEP_SEARCH_SUFFIX_ZH,
    _SEARCH_BASE_EN,
    _SEARCH_BASE_ZH,
)
from app.ai_agents.prompts.shared_rules import (
    ABSOLUTE_OBEDIENCE_RULES_EN,
    ABSOLUTE_OBEDIENCE_RULES_ZH,
    EXTERNAL_SOURCES_CITATION_RULES_EN,
    EXTERNAL_SOURCES_CITATION_RULES_ZH,
    MEMORY_RULES_EN,
    MEMORY_RULES_ZH,
    RESPONSE_RULES_EN,
    RESPONSE_RULES_ZH,
    SECURITY_RULES_EN,
    SECURITY_RULES_ZH,
    TASK_INTEGRITY_RULES_EN,
    TASK_INTEGRITY_RULES_ZH,
)

PromptMode = Literal["full", "lean", "naked", "search"]

# =============================================================================
# Search mode prompt 常量
# =============================================================================

_SEARCH_PROMPT_BASE: str = _SEARCH_BASE_EN
SEARCH_DEEP_SUFFIX: str = _DEEP_SEARCH_SUFFIX_EN
SEARCH_DEEP_SUFFIX_ZH: str = _DEEP_SEARCH_SUFFIX_ZH

# =============================================================================
# Layer 1: 核心系统提示词（双语）
# =============================================================================

# --- 英文人设（Default EN） ---
_IDENTITY_CORE_EN = """
<identity>
You are a powerful, pragmatic, and versatile AI assistant. Your core responsibility is to solve complex problems and accomplish tasks by leveraging your own knowledge, reasoning, and creativity alongside rich external tools and skills.

Your goal is to be the user's most effective assistant, flexibly selecting and combining appropriate tools and skills for any task.
You are dedicated to providing ultra-high-quality, useful, comprehensive, **factually accurate**, and timely answers.
"""

_IDENTITY_SUFFIX_WITH_ANSWER_TOOL_EN = """
When conditions to reply are met, call request_answer_user_tool to request answering the user.
</identity>
"""

_IDENTITY_SUFFIX_WITHOUT_ANSWER_TOOL_EN = """
</identity>
"""

_RULESET_WITH_ANSWER_TOOL_EN = """
<ruleset>
  <rule name="answer_tool_required" priority="high">
    When reply conditions are met, you must call request_answer_user_tool and pass self-audit before answering the user.
    Exceptions: simple greetings, text processing, basic arithmetic, timeless general knowledge explanations.
  </rule>
  <rule name="explicit_tool_request" priority="high">
    When the user explicitly asks to invoke a specific tool, invoke it immediately rather than answering directly.
  </rule>
</ruleset>
"""

_RULESET_WITHOUT_ANSWER_TOOL_EN = """
<ruleset>
  <rule name="explicit_tool_request" priority="high">
    When the user explicitly asks to invoke a specific tool, invoke it immediately rather than answering directly.
  </rule>
</ruleset>
"""

# --- 中文人设（Chinese ZH） ---
_IDENTITY_CORE_ZH = """
<identity>
你是一个功能强大且求真务实的通用AI智能助手。你的核心职责是利用你卓越的自身能力（知识、逻辑、创造力）以及丰富的外部工具和技能，为用户解决各种复杂问题和任务。

你的目标是成为用户最得力的全能助手，你可以灵活选择和组合合适的工具和技能，为用户处理任意类型的任务。
你致力于为用户提供超高质量的、有用、全面、**事实准确**、高时效性的答案，让用户惊叹于你的高质量回答，绝不提供平庸或过时的答案，这是你的服务宗旨。
"""

_IDENTITY_SUFFIX_WITH_ANSWER_TOOL_ZH = """
当达到可回复条件时，必须先调用 request_answer_user_tool 工具请求回答用户。
</identity>
"""

_IDENTITY_SUFFIX_WITHOUT_ANSWER_TOOL_ZH = """
</identity>
"""

_RULESET_WITH_ANSWER_TOOL_ZH = """
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

_RULESET_WITHOUT_ANSWER_TOOL_ZH = """
<ruleset>
  <rule name="explicit_tool_request" priority="high">
    用户明确要求调用具体工具时，必须立即调用，不能直接回答。
  </rule>
</ruleset>
"""

_NAKED_TOOL_GUIDANCE = """
<tool_guidance>
When you need to perform actions, use the available tools via Function Calling API.
Do NOT output tool calls as XML tags in your response text.
</tool_guidance>
"""


def _build_identity_and_rules(enable_answer_tool: bool, is_zh: bool) -> str:
    if is_zh:
        suffix = _IDENTITY_SUFFIX_WITH_ANSWER_TOOL_ZH if enable_answer_tool else _IDENTITY_SUFFIX_WITHOUT_ANSWER_TOOL_ZH
        ruleset = _RULESET_WITH_ANSWER_TOOL_ZH if enable_answer_tool else _RULESET_WITHOUT_ANSWER_TOOL_ZH
        return f"{_IDENTITY_CORE_ZH}{suffix}{ruleset}"
    suffix = _IDENTITY_SUFFIX_WITH_ANSWER_TOOL_EN if enable_answer_tool else _IDENTITY_SUFFIX_WITHOUT_ANSWER_TOOL_EN
    ruleset = _RULESET_WITH_ANSWER_TOOL_EN if enable_answer_tool else _RULESET_WITHOUT_ANSWER_TOOL_EN
    return f"{_IDENTITY_CORE_EN}{suffix}{ruleset}"


def _build_prompt_map(
    identity: str,
    *,
    is_zh: bool,
    include_memory_rules: bool = True,
) -> dict[PromptMode, str]:
    if is_zh:
        full_parts = [
            identity,
            ABSOLUTE_OBEDIENCE_RULES_ZH,
            RESPONSE_RULES_ZH,
            SECURITY_RULES_ZH,
            TASK_INTEGRITY_RULES_ZH,
        ]
        if include_memory_rules:
            full_parts.append(MEMORY_RULES_ZH)

        lean_parts = [identity, SECURITY_RULES_ZH, TASK_INTEGRITY_RULES_ZH]
        if include_memory_rules:
            lean_parts.append(MEMORY_RULES_ZH)

        return {
            "full": "\n".join(full_parts),
            "lean": "\n".join(lean_parts),
            "naked": f"{SECURITY_RULES_ZH}\n{_NAKED_TOOL_GUIDANCE}",
            "search": _SEARCH_BASE_ZH,
        }

    full_parts = [
        identity,
        ABSOLUTE_OBEDIENCE_RULES_EN,
        RESPONSE_RULES_EN,
        SECURITY_RULES_EN,
        TASK_INTEGRITY_RULES_EN,
    ]
    if include_memory_rules:
        full_parts.append(MEMORY_RULES_EN)

    lean_parts = [identity, SECURITY_RULES_EN, TASK_INTEGRITY_RULES_EN]
    if include_memory_rules:
        lean_parts.append(MEMORY_RULES_EN)

    return {
        "full": "\n".join(full_parts),
        "lean": "\n".join(lean_parts),
        "naked": f"{SECURITY_RULES_EN}\n{_NAKED_TOOL_GUIDANCE}",
        "search": _SEARCH_BASE_EN,
    }


# 预构建 8 个静态 Map（is_zh × enable_answer_tool × enable_memory），
# 每个组合跨用户始终返回同一字符串对象以保证 KV Cache 稳定。
_PROMPT_MAPS: dict[tuple[bool, bool, bool], dict[PromptMode, str]] = {
    (False, True, True): _build_prompt_map(_build_identity_and_rules(True, False), is_zh=False, include_memory_rules=True),
    (False, True, False): _build_prompt_map(_build_identity_and_rules(True, False), is_zh=False, include_memory_rules=False),
    (False, False, True): _build_prompt_map(_build_identity_and_rules(False, False), is_zh=False, include_memory_rules=True),
    (False, False, False): _build_prompt_map(_build_identity_and_rules(False, False), is_zh=False, include_memory_rules=False),
    (True, True, True): _build_prompt_map(_build_identity_and_rules(True, True), is_zh=True, include_memory_rules=True),
    (True, True, False): _build_prompt_map(_build_identity_and_rules(True, True), is_zh=True, include_memory_rules=False),
    (True, False, True): _build_prompt_map(_build_identity_and_rules(False, True), is_zh=True, include_memory_rules=True),
    (True, False, False): _build_prompt_map(_build_identity_and_rules(False, True), is_zh=True, include_memory_rules=False),
}

CORE_SYSTEM_PROMPT: str = _PROMPT_MAPS[(False, True, True)]["full"]

# =============================================================================
# API 函数
# =============================================================================


def get_core_system_prompt(
    mode: PromptMode = "full",
    *,
    enable_answer_tool: bool = True,
    enable_memory: bool = True,
    locale: str | None = None,
) -> str:
    """获取核心层 System Prompt (Layer 1)

    Args:
        mode: 提示词模式
            - full: 完整规则（默认），适合通用场景
            - lean: 精简规则，保留身份+安全+任务完整性+记忆（条件）
            - naked: 裸调模式，仅安全规则+工具调用指引
            - search: 搜索模式，轻量搜索专用提示词
        enable_answer_tool: 是否包含 request_answer_user_tool 引导规则
        enable_memory: 是否包含 MEMORY_RULES（memory 工具不可用时应为 False）
        locale: 语言区域代码，如 "zh-CN" / "en"（默认 "en" 英文）

    Returns:
        核心 System Prompt（同一参数组合跨用户缓存稳定）
    """
    zh = is_chinese(locale)
    prompt_map = _PROMPT_MAPS.get(
        (zh, enable_answer_tool, enable_memory),
        _PROMPT_MAPS[(False, True, True)],
    )
    return prompt_map.get(mode, prompt_map["full"])


def get_citation_rules_if_needed(
    has_external_sources: bool,
    *,
    locale: str | None = None,
) -> str | None:
    """获取外部来源引用规则（如果需要）

    用于在 final_answer 阶段、当前轮次有 external_sources 时追加。

    Args:
        has_external_sources: 当前轮次是否有外部知识源
        locale: 语言区域代码（默认 "en" 英文）

    Returns:
        引用规则内容，如果不需要则返回 None
    """
    if has_external_sources:
        return EXTERNAL_SOURCES_CITATION_RULES_ZH if is_chinese(locale) else EXTERNAL_SOURCES_CITATION_RULES_EN
    return None
