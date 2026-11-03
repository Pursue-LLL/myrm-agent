"""Skill search module.

提供自适应的技能搜索功能。
当技能数量超过阈值时，使用搜索引擎替代完全内联。

搜索是 BM25 词法搜索：技能名与描述按词匹配，由工具提示词引导模型用英文关键词与同义词查询。
"""

from .query_expansion import QueryExpander
from .types import SKILL_SEARCH_TOP_K, SkillSearchResult

__all__ = [
    "SKILL_SEARCH_TOP_K",
    "QueryExpander",
    "SkillSearchResult",
]
