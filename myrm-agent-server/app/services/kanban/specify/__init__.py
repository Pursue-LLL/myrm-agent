"""Specify domain — TRIAGE → spec rewrite engine and orchestration.

Aggregated public API for the ``specify`` subpackage.

[INPUT]
- myrm_agent_harness.toolkits.kanban.protocols::SpecifyOutcome, TaskSpecifier
    (POS: Harness protocol for TRIAGE→spec rewrite.)
- myrm_agent_harness.toolkits.kanban.types::KanbanTask (POS: Domain task type.)

[OUTPUT]
- PlatformTaskSpecifier: Concrete TaskSpecifier using LiteLLM + WebUI config.
- SPECIFY_ALL_MAX_CONCURRENT / run_specify_task / run_apply_spec /
    run_specify_all_triage: Specify orchestration helpers.

[POS]
Server-layer specify domain owned by KanbanService.
"""

from app.services.kanban.specify.orchestrator import (
    SPECIFY_ALL_MAX_CONCURRENT,
    run_apply_spec,
    run_specify_all_triage,
    run_specify_task,
)
from app.services.kanban.specify.specifier import PlatformTaskSpecifier

__all__ = [
    "PlatformTaskSpecifier",
    "SPECIFY_ALL_MAX_CONCURRENT",
    "run_apply_spec",
    "run_specify_all_triage",
    "run_specify_task",
]
