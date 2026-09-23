"""Wiki writeback domain module.

[INPUT]
- .schemas (DTOs)
- .service (WikiWritebackService)

[OUTPUT]
- WikiWritebackService, get_writeback_service, schemas

[POS]
Entry point for usage ledger and selective review slip writeback subsystem.
"""

from app.services.wiki.writeback.schemas import (
    ReviewSlipBatch,
    ReviewSlipOption,
    ReviewSlipQuestion,
    UsageLedgerItem,
    UsageLedgerRecord,
    WritebackApplyRequest,
    WritebackApplyResult,
    WritebackDecisionItem,
)
from app.services.wiki.writeback.service import (
    WikiWritebackService,
    get_writeback_service,
)

__all__ = [
    "ReviewSlipBatch",
    "ReviewSlipOption",
    "ReviewSlipQuestion",
    "UsageLedgerItem",
    "UsageLedgerRecord",
    "WikiWritebackService",
    "WritebackApplyRequest",
    "WritebackApplyResult",
    "WritebackDecisionItem",
    "get_writeback_service",
]
