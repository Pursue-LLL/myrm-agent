"""Evolution API - Pending Evolutions & LLM Confirmation Rejection Logs"""

from fastapi import APIRouter

from .derive import router as derive_router
from .fix import router as fix_router
from .history import router as history_router
from .pending import router as pending_router
from .rejections import router as rejections_router

router = APIRouter(prefix="/evolution", tags=["evolution"])

router.include_router(pending_router)
router.include_router(rejections_router)
router.include_router(history_router)
router.include_router(derive_router)
router.include_router(fix_router)

# Re-export for callers that import from `app.api.skills.evolution`.
from .pending import (  # noqa: E402
    approve_pending_evolution_record,
    count_pending_evolution_records,
    list_pending_evolution_records,
    reject_pending_evolution_record,
)

__all__ = [
    "approve_pending_evolution_record",
    "count_pending_evolution_records",
    "list_pending_evolution_records",
    "reject_pending_evolution_record",
    "router",
]
