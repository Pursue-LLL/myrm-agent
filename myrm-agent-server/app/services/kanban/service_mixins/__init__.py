"""KanbanService composition subpackage — mixins and shared types for the service facade.

[POS]
KanbanService 组合子域。core 为单例状态基类；ai/board_task/query_dispatcher 为
业务薄壳 mixin；types 为共享 DTO/异常/常量。service.py（门面）组合它们。

[IMPORT CONSTRAINT]
聚合入口由门面（service.py）与包根 `__init__.py` 消费。根操作模块
（board_summary/dependency_ops/move_orchestrator/task_ops）处于
mixin → 根操作模块 → types 的依赖链中，若也走聚合入口会形成循环导入，
故它们必须穿透导入 `service_mixins.types`（子模块），不得改为聚合入口。
"""

from app.services.kanban.service_mixins.ai_mixin import KanbanAiWorkflowMixin
from app.services.kanban.service_mixins.board_task_mixin import KanbanBoardTaskMixin
from app.services.kanban.service_mixins.core import KanbanServiceCore
from app.services.kanban.service_mixins.query_dispatcher_mixin import (
    KanbanDispatcherMixin,
    KanbanReadMixin,
)
from app.services.kanban.service_mixins.types import (
    STATUS_TO_EVENT_KIND,
    SYNTHETIC_RUN_TARGETS,
    TARGET_TO_RUN_OUTCOME,
    UNSET,
    BoardSummaryData,
    DependencyUnmetError,
    PromoteResult,
    Sentinel,
    UnmetParentInfo,
)

__all__ = [
    "BoardSummaryData",
    "DependencyUnmetError",
    "KanbanAiWorkflowMixin",
    "KanbanBoardTaskMixin",
    "KanbanDispatcherMixin",
    "KanbanReadMixin",
    "KanbanServiceCore",
    "PromoteResult",
    "STATUS_TO_EVENT_KIND",
    "SYNTHETIC_RUN_TARGETS",
    "Sentinel",
    "TARGET_TO_RUN_OUTCOME",
    "UNSET",
    "UnmetParentInfo",
]
