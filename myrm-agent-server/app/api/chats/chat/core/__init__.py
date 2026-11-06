"""Chat core API.

[INPUT]
- .crud / .recall / .pins / .session (POS: endpoint sub-routers)

[OUTPUT]
- router

[POS]
Aggregate exit of the chat core router package; sub-routers are mounted in a fixed order.
"""

from __future__ import annotations

from fastapi import APIRouter

from .crud import router as crud_router
from .pins import router as pins_router
from .recall import router as recall_router
from .session import router as session_router

router = APIRouter()
router.include_router(crud_router)
router.include_router(recall_router)
router.include_router(pins_router)
router.include_router(session_router)

__all__ = ["router"]
