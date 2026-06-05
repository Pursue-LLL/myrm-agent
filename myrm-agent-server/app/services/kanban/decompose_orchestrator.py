"""Decompose orchestration helpers for KanbanService.

Mirrors ``specify_orchestrator.py``: single owner of the TRIAGE → child-graph
flow that bridges the harness-layer ``TaskDecomposer`` Protocol and the
server-layer store / event-bus / dispatcher.

[INPUT]
- myrm_agent_harness.toolkits.kanban.protocols::DecomposeOutcome, DecomposeChildSpec,
    TaskDecomposer (POS: Harness protocol for TRIAGE→child-graph.)
- myrm_agent_harness.toolkits.kanban.types::KanbanTask, TaskEventKind, TaskStatus
- app.services.agent.agent_service::AgentService (POS: Agent profile listing.)

[OUTPUT]
- build_agent_roster: Construct roster from the platform's agent profiles.
- run_decompose_task: Preview a decomposition without persistence.
- run_apply_decompose: Persist children atomically from a cached preview.
- run_apply_no_fanout: Persist a fanout=false result as Specify (TRIAGE→READY).

[POS]
Server-layer decompose orchestration owned by KanbanService.
"""

from __future__ import annotations

import logging
from typing import Protocol

from myrm_agent_harness.toolkits.kanban.protocols import (
    DecomposeChildSpec,
    DecomposeOutcome,
    TaskDecomposer,
)
from myrm_agent_harness.toolkits.kanban.types import (
    KanbanTask,
    TaskEventKind,
    TaskStatus,
)

from app.core.kanban.adapters import SqlAlchemyKanbanStore

logger = logging.getLogger(__name__)

DEFAULT_AGENT_ID = "default"


class _DispatcherWaker(Protocol):
    def __call__(self, board_id: str) -> None: ...


class _EventPublisher(Protocol):
    def __call__(
        self,
        board_id: str,
        task_id: str,
        action: str,
        *,
        title: str,
        status: str,
    ) -> None: ...


async def build_agent_roster() -> tuple[list[dict[str, str]], set[str], str]:
    """Build the agent roster from the platform's AgentService.

    Returns:
        (roster_for_prompt, valid_agent_ids, default_agent_id)
    """
    from app.services.agent.agent_service import AgentService

    profiles, _ = await AgentService.get_agent_list(page=1, page_size=200)
    roster: list[dict[str, str]] = []
    valid_ids: set[str] = set()
    default_id = DEFAULT_AGENT_ID

    for p in profiles:
        name = p.display_name or p.id
        desc = p.description or p.system_prompt or ""
        if desc and len(desc) > 200:
            desc = desc[:197] + "..."
        roster.append({"name": p.id, "description": desc or name})
        valid_ids.add(p.id)
        if p.built_in:
            default_id = p.id

    return roster, valid_ids, default_id


async def run_decompose_task(
    task_id: str,
    *,
    store: SqlAlchemyKanbanStore,
    decomposer: TaskDecomposer | None,
) -> DecomposeOutcome:
    """Run the TaskDecomposer on a single TRIAGE task (preview only)."""
    if decomposer is None:
        return DecomposeOutcome(
            task_id=task_id,
            ok=False,
            reason="decomposer_unavailable",
        )

    task = await store.get_task(task_id)
    if task is None:
        return DecomposeOutcome(task_id=task_id, ok=False, reason="unknown_task")

    roster, _valid_ids, default_id = await build_agent_roster()
    return await decomposer.decompose(
        task,
        roster=roster,
        default_assignee=default_id,
    )


async def run_apply_decompose(
    task_id: str,
    *,
    children: list[DecomposeChildSpec],
    rationale: str,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    store: SqlAlchemyKanbanStore,
    add_task_fn: _AddTaskFn,
    wake_dispatcher: _DispatcherWaker,
    publish_event: _EventPublisher,
    author: str = "decomposer",
) -> DecomposeOutcome:
    """Persist children from a cached decompose preview.

    Atomically creates child tasks, wires dependency edges, promotes the
    root TRIAGE → BACKLOG (waits for children), records DECOMPOSED event,
    and wakes the dispatcher so children enter dispatch immediately.
    """
    task = await store.get_task(task_id)
    if task is None:
        return DecomposeOutcome(task_id=task_id, ok=False, reason="unknown_task")
    if task.status != TaskStatus.TRIAGE:
        return DecomposeOutcome(
            task_id=task_id,
            ok=False,
            reason="race_lost",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    child_ids: list[str] = []
    for spec in children:
        depends_on: list[str] = []
        for pi in spec.parent_indices:
            if 0 <= pi < len(child_ids):
                depends_on.append(child_ids[pi])

        child = await add_task_fn(
            board_id=task.board_id,
            title=spec.title,
            description=spec.body,
            agent_id=spec.assignee,
            parent_task_id=task.task_id,
            depends_on=depends_on or None,
            extra_skill_ids=list(spec.extra_skill_ids) or None,
        )
        child_ids.append(child.task_id)

    task.status = TaskStatus.BACKLOG
    await store.save_task(task)

    await store.append_event(
        task.task_id,
        TaskEventKind.DECOMPOSED,
        payload={
            "author": author,
            "child_count": len(child_ids),
            "child_ids": child_ids,
            "rationale": rationale,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        },
    )

    wake_dispatcher(task.board_id)
    publish_event(
        task.board_id,
        task.task_id,
        "decomposed",
        title=task.title,
        status=task.status.value,
    )

    return DecomposeOutcome(
        task_id=task.task_id,
        ok=True,
        fanout=True,
        children=tuple(children),
        rationale=rationale,
        reason="decomposed",
        child_ids=tuple(child_ids),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        persisted=True,
    )


async def run_apply_no_fanout(
    task_id: str,
    *,
    new_title: str | None,
    new_body: str | None,
    new_assignee: str | None,
    rationale: str,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    store: SqlAlchemyKanbanStore,
    wake_dispatcher: _DispatcherWaker,
    publish_event: _EventPublisher,
    author: str = "decomposer",
) -> DecomposeOutcome:
    """Persist a fanout=false decompose as a Specify (single-task fallback).

    Applies the LLM-tightened title/body/assignee to the task, promotes
    TRIAGE → READY, and records a SPECIFIED event — identical to the
    Specify flow, avoiding a redundant second LLM call.
    """
    task = await store.get_task(task_id)
    if task is None:
        return DecomposeOutcome(task_id=task_id, ok=False, reason="unknown_task")
    if task.status != TaskStatus.TRIAGE:
        return DecomposeOutcome(
            task_id=task_id,
            ok=False,
            reason="race_lost",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    original_title = task.title
    original_desc = task.description
    if new_title:
        task.title = new_title
    if new_body:
        task.description = new_body
    if new_assignee and not task.agent_id:
        task.agent_id = new_assignee
    task.metadata = task.metadata or {}
    task.metadata["original_title"] = original_title
    task.metadata["original_description"] = original_desc
    task.status = TaskStatus.READY
    await store.save_task(task)

    await store.append_event(
        task.task_id,
        TaskEventKind.SPECIFIED,
        payload={
            "author": author,
            "promoted_to": TaskStatus.READY.value,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        },
    )

    wake_dispatcher(task.board_id)
    publish_event(
        task.board_id,
        task.task_id,
        "specified",
        title=task.title,
        status=task.status.value,
    )

    return DecomposeOutcome(
        task_id=task.task_id,
        ok=True,
        fanout=False,
        rationale=rationale,
        reason="specified_via_decompose",
        new_title=new_title,
        new_body=new_body,
        new_assignee=new_assignee,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        persisted=True,
    )


class _AddTaskFn(Protocol):
    """Minimal contract for KanbanService.add_task."""

    async def __call__(
        self,
        board_id: str,
        title: str,
        description: str,
        *,
        agent_id: str | None,
        parent_task_id: str | None,
        depends_on: list[str] | None,
        extra_skill_ids: list[str] | None = None,
    ) -> KanbanTask: ...
