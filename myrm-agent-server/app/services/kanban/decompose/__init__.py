"""Decompose domain — TRIAGE → child task graph engine and orchestration.

Aggregated public API for the ``decompose`` subpackage.

[OUTPUT]
- PlatformTaskDecomposer: Concrete TaskDecomposer using the platform LLM + WebUI config.
- run_decompose_task / run_apply_decompose / run_apply_no_fanout:
    Decompose orchestration helpers.

[POS]
Server-layer decompose domain owned by KanbanService.
"""

from app.services.kanban.decompose.decomposer import PlatformTaskDecomposer
from app.services.kanban.decompose.orchestrator import (
    run_apply_decompose,
    run_apply_no_fanout,
    run_decompose_task,
)

__all__ = [
    "PlatformTaskDecomposer",
    "run_apply_decompose",
    "run_apply_no_fanout",
    "run_decompose_task",
]
