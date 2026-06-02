"""Re-export from app.core.skills.config_version（单一来源）。"""

from app.core.skills.config_version import (
    bump_skill_config_version,
    get_skill_config_version,
)

__all__ = ["bump_skill_config_version", "get_skill_config_version"]
