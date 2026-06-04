"""Kanban REST API — aggregates route modules on a single router.

[INPUT]
app.api.kanban.routes.* (POS: Kanban 分域 HTTP 端点)

[OUTPUT]
router: 挂载全部 Kanban 端点的 APIRouter

[POS]
Kanban API 聚合入口，供 app.api.router 注册。
"""

from app.api.kanban.http_common import router
from app.api.kanban.routes import boards, bulk, specify, task_meta, tasks  # noqa: F401

__all__ = ["router"]
