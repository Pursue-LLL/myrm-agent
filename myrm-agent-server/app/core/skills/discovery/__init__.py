"""Discovery - 技能发现、采纳、挂载、供应链重扫与上游更新子域。

[POS]
聚合出口：
- adopt: 显式 allowlist 场景安装后自动采纳（append skill_id）
- mount: 安装/更新后 catalog enable 入口
- autoupdate: 上游版本检测与更新检查
- rescan_service: 已安装技能供应链漏洞与恶意投毒重扫
"""

from .adopt import complete_discovery_adoption
from .autoupdate import get_update_checker
from .mount import (
    DEFAULT_MOUNT_AGENT_ID,
    SkillMountResult,
    maybe_mount_after_install,
    resolve_mount_skill_id,
)
from .rescan_service import (
    RescanReport,
    SkillRescanItem,
    SkillRescanService,
    rescan_service,
)

__all__ = [
    "DEFAULT_MOUNT_AGENT_ID",
    "RescanReport",
    "SkillMountResult",
    "SkillRescanItem",
    "SkillRescanService",
    "complete_discovery_adoption",
    "get_update_checker",
    "maybe_mount_after_install",
    "rescan_service",
    "resolve_mount_skill_id",
]
