"""Discovery - 技能发现、采纳、挂载与上游更新子域。

[POS]
聚合出口：
- adopt: 显式 allowlist 场景安装后自动采纳（append skill_id）
- mount: 安装/更新后 catalog enable 入口
- autoupdate: 上游版本检测与更新检查
"""

from .adopt import complete_discovery_adoption
from .autoupdate import get_update_checker
from .mount import (
    DEFAULT_MOUNT_AGENT_ID,
    SkillMountResult,
    maybe_mount_after_install,
    resolve_mount_skill_id,
)

__all__ = [
    "DEFAULT_MOUNT_AGENT_ID",
    "SkillMountResult",
    "complete_discovery_adoption",
    "get_update_checker",
    "maybe_mount_after_install",
    "resolve_mount_skill_id",
]
