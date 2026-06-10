"""KanbanService core state and shared helpers."""

from __future__ import annotations

from typing import ClassVar

from myrm_agent_harness.toolkits.kanban.dispatcher import KanbanDispatcher
from myrm_agent_harness.toolkits.kanban.protocols import (
    TaskDecomposer,
    TaskRunner,
    TaskSpecifier,
)

from app.core.kanban.adapters import SqlAlchemyKanbanStore


class KanbanServiceCore:
    """Shared singleton state for KanbanService mixins."""

    _instance: ClassVar[KanbanServiceCore | None] = None

    _store: SqlAlchemyKanbanStore
    _dispatchers: dict[str, KanbanDispatcher]
    _runner: TaskRunner | None
    _specifier: TaskSpecifier | None
    _decomposer: TaskDecomposer | None

    def __init__(self) -> None:
        self._store = SqlAlchemyKanbanStore()
        self._dispatchers = {}
        self._runner = None
        self._specifier = None
        self._decomposer = None

    @property
    def store(self) -> SqlAlchemyKanbanStore:
        return self._store

    def set_runner(self, runner: TaskRunner) -> None:
        self._runner = runner

    def set_specifier(self, specifier: TaskSpecifier) -> None:
        self._specifier = specifier

    @property
    def specifier(self) -> TaskSpecifier | None:
        return self._specifier

    def set_decomposer(self, decomposer: TaskDecomposer) -> None:
        self._decomposer = decomposer

    @property
    def decomposer(self) -> TaskDecomposer | None:
        return self._decomposer

    def _wake_dispatcher(self, board_id: str) -> None:
        if board_id in self._dispatchers:
            self._dispatchers[board_id].wake()

    @staticmethod
    async def _validate_agent_id(agent_id: str) -> None:
        from app.services.agent.agent_service import AgentService

        agent = await AgentService.get_agent_by_id(agent_id)
        if agent is None:
            raise ValueError(f"Agent '{agent_id}' not found")
