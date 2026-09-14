"""Kanban REST API — aggregates route modules on a single router.

[INPUT]
app.api.kanban.routes.* (POS: Kanban 分域 HTTP 端点)

[OUTPUT]
router: 挂载全部 Kanban 端点的 APIRouter

[POS]
Kanban API 聚合入口，供 app.api.router 注册。
"""

from app.api.kanban.http_common import router
from app.api.kanban.routes import (  # noqa: F401
    boards,
    bulk,
    race,
    specify,
    task_meta,
    tasks,
    tasks_list,
)

__all__ = ["router"]
