"""Kanban business service facade.

Orchestrates store, dispatcher, and EventBus for kanban operations.
Provides a clean API for the HTTP layer.

[INPUT]
- core.kanban.adapters::SqlAlchemyKanbanStore (POS: KanbanStore persistence adapter.)
- myrm_agent_harness.toolkits.kanban (POS: Kanban toolkit framework layer.)
- api.events.event_bus::AppEvent, AppEventType, get_event_bus (POS: Global SSE event bus.)

[OUTPUT]
- KanbanService: Singleton business orchestration service.

[POS]
Kanban business service facade; domain logic lives in sibling orchestrator modules.
"""

from __future__ import annotations

from typing import cast

from app.services.kanban.event_publisher import emit_btw_done as _emit_btw_done
from app.services.kanban.event_publisher import publish_kanban_event as _publish_kanban_event
from app.services.kanban.service_ai_mixin import KanbanAiWorkflowMixin
from app.services.kanban.service_board_task_mixin import KanbanBoardTaskMixin
from app.services.kanban.service_core import KanbanServiceCore
from app.services.kanban.service_query_dispatcher_mixin import KanbanDispatcherMixin, KanbanReadMixin
from app.services.kanban.service_types import (
    BoardSummaryData,
    DependencyUnmetError,
    PromoteResult,
    UnmetParentInfo,
)

__all__ = [
    "BoardSummaryData",
    "DependencyUnmetError",
    "KanbanService",
    "PromoteResult",
    "UnmetParentInfo",
    "_emit_btw_done",
    "_publish_kanban_event",
]


class KanbanService(
    KanbanBoardTaskMixin,
    KanbanReadMixin,
    KanbanDispatcherMixin,
    KanbanAiWorkflowMixin,
    KanbanServiceCore,
):
    """Singleton business orchestration service for kanban."""

    @classmethod
    def get_instance(cls) -> KanbanService:
        if cls._instance is None:
            cls._instance = cls()
        return cast(KanbanService, cls._instance)
