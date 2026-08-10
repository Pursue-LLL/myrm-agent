"""Decompose domain — TRIAGE → child task graph engine and orchestration.

Aggregated public API for the ``decompose`` subpackage.

[INPUT]
- myrm_agent_harness.toolkits.kanban.protocols::DecomposeOutcome, TaskDecomposer
    (POS: Harness protocol for TRIAGE→child-graph.)
- myrm_agent_harness.toolkits.kanban.types::KanbanTask (POS: Domain task type.)

[OUTPUT]
- PlatformTaskDecomposer: Concrete TaskDecomposer using LiteLLM + WebUI config.
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
