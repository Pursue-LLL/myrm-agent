"""Re-export from myrm_agent_harness.backends.skills.config_version（框架层）。"""

from myrm_agent_harness.backends.skills.config_version import (
    bump_skill_config_version,
    get_skill_config_version,
)

__all__ = ["bump_skill_config_version", "get_skill_config_version"]
