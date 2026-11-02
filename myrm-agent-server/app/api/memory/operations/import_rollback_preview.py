"""Memory import rollback preview endpoint.

[INPUT]
- app.services.memory.operations.crud_handlers::dry_run_rollback_import_memories (POS: 回滚预演的只读处理函数)

[OUTPUT]
router: `POST /memory/import/rollback/dry-run` content-safe preview of what rolling back a confirmed import batch would undo.

[POS]
导入回滚预演 API 操作层。只有 Memory Labs 命令中心的导入回滚弹窗调用它，因此只在 `MYRM_MEMORY_LABS=1` 时挂载；
实际回滚 `POST /import/rollback` 不依赖预演结果，迁移向导与演示数据清理都直接调用，由 `crud.py` 提供，对所有用户挂载。
"""

from __future__ import annotations

from fastapi import APIRouter

from app.schemas.memory.archive import MemoryImportRollbackPreviewResponse
from app.services.memory.operations import crud_handlers as handlers

router = APIRouter()

router.post("/import/rollback/dry-run", response_model=MemoryImportRollbackPreviewResponse)(
    handlers.dry_run_rollback_import_memories
)
