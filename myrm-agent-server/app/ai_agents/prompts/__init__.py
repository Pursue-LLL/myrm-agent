"""Prompts 模块

提示词管理层，存储和管理系统提示词模板。
支持分层提示词架构和动态模板生成。
"""

from .fast_search_agent_prompt import get_fast_search_agent_prompt
from .general_agent_prompt import (
    CORE_SYSTEM_PROMPT,
    get_citation_rules_if_needed,
    get_core_system_prompt,
)
from .shared_rules import (
    EXTERNAL_SOURCES_CITATION_RULES,
    RESPONSE_RULES,
    SECURITY_RULES,
)

__all__ = [
    # fast_search_agent_prompt
    "get_fast_search_agent_prompt",
    # layered_prompts
    "CORE_SYSTEM_PROMPT",
    "get_core_system_prompt",
    "get_citation_rules_if_needed",
    # shared_rules
    "SECURITY_RULES",
    "RESPONSE_RULES",
    "EXTERNAL_SOURCES_CITATION_RULES",
]
