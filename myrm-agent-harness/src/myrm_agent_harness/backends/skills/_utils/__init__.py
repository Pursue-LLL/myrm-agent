"""[INPUT]
- myrm_agent_harness.backends.skills._utils.frontmatter::_MAX_SKILL_FILE_SIZE / SkillFrontmatter / SkillMetadataError (POS: skills _utils 子包的一部分；由 __init__.py 聚合导出。)
- myrm_agent_harness.backends.skills._utils.parsing::parse_skill_frontmatter (POS: skills _utils 子包的一部分；由 __init__.py 聚合导出。)

[OUTPUT]
- _MAX_SKILL_FILE_SIZE
- SkillFrontmatter
- SkillMetadataError
- parse_skill_frontmatter

[POS]
`myrm_agent_harness.backends.skills._utils` 的唯一入口；实现按 frontmatter/contract/parsing 分层。
"""

from myrm_agent_harness.backends.skills._utils.frontmatter import (
    _MAX_SKILL_FILE_SIZE,
    SkillFrontmatter,
    SkillMetadataError,
)
from myrm_agent_harness.backends.skills._utils.parsing import parse_skill_frontmatter

__all__ = [
    "SkillFrontmatter",
    "SkillMetadataError",
    "_MAX_SKILL_FILE_SIZE",
    "parse_skill_frontmatter",
]
