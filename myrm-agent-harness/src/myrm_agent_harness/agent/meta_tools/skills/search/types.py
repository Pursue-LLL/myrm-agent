"""技能搜索模块的共享类型定义

[INPUT]
- (none)

[OUTPUT]
- SkillSearchResult: class — Skill Search Result

[POS]
Provides SkillSearchResult.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["SKILL_SEARCH_TOP_K", "SkillSearchResult"]

SKILL_SEARCH_TOP_K = 5


@dataclass(frozen=True)
class SkillSearchResult:
    """搜索结果条目"""

    name: str
    description: str
    score: float
