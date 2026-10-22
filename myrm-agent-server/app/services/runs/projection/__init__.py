"""Runs Multi-Surface Projection Service Package.

[INPUT]
- app.services.runs.projection.projection_types
- app.services.runs.projection.run_projection_service

[OUTPUT]
- Public facades for run snapshots, attempts, events, and projection service

[POS]
app/services/runs/projection/__init__.py: Package entrypoint exposing projection models and services.
"""

from __future__ import annotations

from app.services.runs.projection.projection_types import (
    AttemptRecord,
    AttemptStatus,
    AuditLedgerEntry,
    DeliverableItem,
    RunProjectionEvent,
    RunStateSnapshot,
    SurfaceViewType,
)
from app.services.runs.projection.run_projection_service import (
    RunProjectionService,
    run_projection_service,
)

__all__ = [
    "AttemptRecord",
    "AttemptStatus",
    "AuditLedgerEntry",
    "DeliverableItem",
    "RunProjectionEvent",
    "RunProjectionService",
    "RunStateSnapshot",
    "SurfaceViewType",
    "run_projection_service",
]
