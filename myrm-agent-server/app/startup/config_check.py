"""
@input: 依赖 app.config.change_tracker 的「配置变更追踪」、app.config.migrator 的「配置迁移」
@output: 对外提供启动前配置校验与迁移
@pos: 启动配置校验 —— 确保配置合法后再启动服务

🔄 更新规则：修改此文件后，请更新头注释 + 所属文件夹 _ARCH.md
"""

import sys
from pathlib import Path

from app.config.change_tracker import track_config_changes
from app.config.migrator import check_and_migrate_config
from app.config.pre_flight import preflight_check_config
from app.config.settings import settings


def run_config_check() -> None:
    """执行配置迁移、预检和变更追踪。配置有误时直接退出进程。"""
    print()  # Add blank line for readability

    state_dir = Path(settings.database.state_dir)

    # 1. Check and migrate config schema (if version changed)
    check_and_migrate_config(state_dir)

    # 2. Pre-flight config validation
    preflight_result = preflight_check_config()
    preflight_result.print_report()

    if preflight_result.has_errors():
        sys.exit(1)

    # 3. Track config changes (output change summary)
    try:
        config_dict = settings.model_dump(mode="json")
        track_config_changes(state_dir, config_dict)
    except Exception as e:
        print(f"[CONFIG] Warning: Failed to track config changes: {e}")

    print()  # Add blank line for readability
