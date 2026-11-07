"""[INPUT]
- .base::MemoryImportSessionBase (POS: 共享状态)
- .dry_run::DryRunMixin (POS: dry-run/confirm)
- .queries::ImportQueriesMixin (POS: 查询)
- .readiness::ReadinessMixin (POS: 就绪诊断)
- .rollback::RollbackMixin (POS: 回滚)

[OUTPUT]
- MemoryImportSessionService: 对外导入会话服务

[POS]
`import_sessions/` 的编排层；组合四个阶段并建立 db/ledger 状态。
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.memory.imports.import_ledger import (
    MemoryImportLedgerService,
)
from app.services.memory.ledger.operation_ledger import MemoryOperationLedgerService

from .base import MemoryImportSessionBase
from .dry_run import DryRunMixin
from .queries import ImportQueriesMixin
from .readiness import ReadinessMixin
from .rollback import RollbackMixin


class MemoryImportSessionService(
    DryRunMixin, RollbackMixin, ReadinessMixin, ImportQueriesMixin, MemoryImportSessionBase
):
    """Creates and confirms server-bound memory import review sessions."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._ledger = MemoryOperationLedgerService(db)
        self._import_ledger = MemoryImportLedgerService(db)
