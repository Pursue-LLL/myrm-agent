"""Skills 解析工具门面。

[OUTPUT]
SkillFrontmatter / SkillMetadataError / parse_frontmatter / parse_skill_frontmatter / 文件大小上限。

[POS]
`myrm_agent_harness.backends.skills._utils` 的唯一入口；实现按 frontmatter/contract/parsing 拆分。
"""

from myrm_agent_harness.backends.skills._utils.frontmatter import (
    _MAX_SKILL_FILE_SIZE,
    SkillFrontmatter,
    SkillMetadataError,
    parse_frontmatter,
)
from myrm_agent_harness.backends.skills._utils.parsing import parse_skill_frontmatter

__all__ = [
    "SkillFrontmatter",
    "SkillMetadataError",
    "_MAX_SKILL_FILE_SIZE",
    "parse_frontmatter",
    "parse_skill_frontmatter",
]
