"""Curator - 技能生命周期治理子域。

聚合出口：
- service: sweep/配置/历史/后台任务编排（业务层）
- consolidation: 技能合并（umbrella merge）集成
"""

from .consolidation import run_consolidation_execute, run_consolidation_preview
from .service import (
    get_curator_config,
    get_curator_history,
    get_stats_collector,
    resolve_skill_path,
    run_curator_sweep,
    start_curator_background_task,
    stop_curator_background_task,
    update_curator_config,
)

__all__ = [
    "get_curator_config",
    "get_curator_history",
    "get_stats_collector",
    "resolve_skill_path",
    "run_consolidation_execute",
    "run_consolidation_preview",
    "run_curator_sweep",
    "start_curator_background_task",
    "stop_curator_background_task",
    "update_curator_config",
]
