"""KanbanService specify/decompose workflow methods.

[INPUT]
- myrm_agent_harness.toolkits.kanban.protocols (POS: Kanban protocol interfaces.)
- decompose_orchestrator (POS: Task decomposition orchestration.)
- specify_orchestrator (POS: Task specification orchestration.)
- service_core (POS: KanbanService core state.)

[OUTPUT]
- KanbanServiceAIMixin: Mixin providing specify/decompose workflow methods.

[POS]
AI-powered mixin: task specification, decomposition, and batch triage processing.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.kanban.protocols import (
    DecomposeChildSpec,
    DecomposeOutcome,
    SpecifyOutcome,
)
from myrm_agent_harness.toolkits.kanban.types import KanbanTask

from app.services.kanban.decompose_orchestrator import (
    run_apply_decompose,
    run_apply_no_fanout,
    run_decompose_task,
)
from app.services.kanban.event_publisher import publish_kanban_event as _publish_kanban_event
from app.services.kanban.service_core import KanbanServiceCore
from app.services.kanban.specify_orchestrator import (
    SPECIFY_ALL_MAX_CONCURRENT,
    run_apply_spec,
    run_specify_all_triage,
    run_specify_task,
)


class KanbanAiWorkflowMixin(KanbanServiceCore):
    async def specify_task(
        self,
        task_id: str,
        *,
        persist: bool = False,
        author: str = "specifier",
    ) -> SpecifyOutcome:
        return await run_specify_task(
            task_id,
            store=self._store,
            specifier=self._specifier,
            wake_dispatcher=self._wake_dispatcher,
            publish_event=_publish_kanban_event,
            persist=persist,
            author=author,
        )

    async def apply_spec(
        self,
        task_id: str,
        *,
        new_title: str | None,
        new_body: str,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        author: str = "specifier",
    ) -> SpecifyOutcome:
        return await run_apply_spec(
            task_id,
            new_title=new_title,
            new_body=new_body,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            store=self._store,
            wake_dispatcher=self._wake_dispatcher,
            publish_event=_publish_kanban_event,
            author=author,
        )

    async def specify_all_triage(
        self,
        board_id: str,
        *,
        persist: bool = False,
        author: str = "specifier",
        max_concurrent: int = SPECIFY_ALL_MAX_CONCURRENT,
    ) -> list[SpecifyOutcome]:
        async def _delegate(tid: str, p: bool, a: str) -> SpecifyOutcome:
            return await self.specify_task(tid, persist=p, author=a)

        return await run_specify_all_triage(
            board_id,
            store=self._store,
            specify_one=_delegate,
            persist=persist,
            author=author,
            max_concurrent=max_concurrent,
        )

    async def decompose_task(self, task_id: str) -> DecomposeOutcome:
        return await run_decompose_task(
            task_id,
            store=self._store,
            decomposer=self._decomposer,
        )

    async def apply_decompose(
        self,
        task_id: str,
        *,
        children: list[DecomposeChildSpec],
        rationale: str = "",
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        author: str = "decomposer",
    ) -> DecomposeOutcome:
        async def _add_task(
            board_id: str,
            title: str,
            description: str,
            *,
            agent_id: str | None,
            parent_task_id: str | None,
            depends_on: list[str] | None,
            extra_skill_ids: list[str] | None = None,
        ) -> KanbanTask:
            return await self.add_task(
                board_id=board_id,
                title=title,
                description=description,
                agent_id=agent_id,
                parent_task_id=parent_task_id,
                depends_on=depends_on,
                extra_skill_ids=extra_skill_ids,
            )

        return await run_apply_decompose(
            task_id,
            children=children,
            rationale=rationale,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            store=self._store,
            add_task_fn=_add_task,
            wake_dispatcher=self._wake_dispatcher,
            publish_event=_publish_kanban_event,
            author=author,
        )

    async def apply_no_fanout(
        self,
        task_id: str,
        *,
        new_title: str | None = None,
        new_body: str | None = None,
        new_assignee: str | None = None,
        rationale: str = "",
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        author: str = "decomposer",
    ) -> DecomposeOutcome:
        return await run_apply_no_fanout(
            task_id,
            new_title=new_title,
            new_body=new_body,
            new_assignee=new_assignee,
            rationale=rationale,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            store=self._store,
            wake_dispatcher=self._wake_dispatcher,
            publish_event=_publish_kanban_event,
            author=author,
        )
