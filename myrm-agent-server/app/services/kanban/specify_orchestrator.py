"""Specify orchestration helpers for KanbanService.

Single owner of the TRIAGE → spec rewrite flow that bridges the harness-layer
``TaskSpecifier`` Protocol and the server-layer store / event-bus / dispatcher.
Keeps the persistence ↔ promotion ↔ wake sequence in one place so that any
future change to the spec lifecycle has exactly one site to update.

[INPUT]
- myrm_agent_harness.toolkits.kanban.protocols::SpecifyOutcome, TaskSpecifier
- myrm_agent_harness.toolkits.kanban.types::KanbanTask, TaskEventKind, TaskStatus

[OUTPUT]
- SPECIFY_ALL_MAX_CONCURRENT: bound on parallel LLM calls per board.
- run_specify_task: persist-or-preview one TRIAGE task.
- run_apply_spec: persist a cached dry-run outcome without re-invoking LLM.
- run_specify_all_triage: bounded-concurrency sweep over a board.

[POS]
Server-layer specify orchestration owned by KanbanService.
"""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, Protocol

from myrm_agent_harness.toolkits.kanban.protocols import (
    SpecifyOutcome,
    TaskSpecifier,
)
from myrm_agent_harness.toolkits.kanban.types import (
    KanbanTask,
    TaskEventKind,
    TaskStatus,
)

from app.core.kanban.adapters import SqlAlchemyKanbanStore

SPECIFY_ALL_MAX_CONCURRENT: int = 3


class _DispatcherWaker(Protocol):
    """Minimal contract: wake a board's dispatcher if one exists."""

    def __call__(self, board_id: str) -> None: ...


class _EventPublisher(Protocol):
    """Minimal contract: publish a Kanban app-event to the bus."""

    def __call__(
        self,
        board_id: str,
        task_id: str,
        action: str,
        *,
        title: str,
        status: str,
    ) -> None: ...


async def _persist_spec(
    task: KanbanTask,
    *,
    new_title: str | None,
    new_body: str,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    reason: str,
    store: SqlAlchemyKanbanStore,
    wake_dispatcher: _DispatcherWaker,
    publish_event: _EventPublisher,
    author: str,
) -> SpecifyOutcome:
    """Shared persistence path for run_specify_task(persist=True) and run_apply_spec."""
    original_title = task.title
    original_description = task.description
    if new_title:
        task.title = new_title
    task.description = new_body

    meta = dict(task.metadata) if task.metadata else {}
    meta.setdefault("original_title", original_title)
    if original_description:
        meta.setdefault("original_description", original_description)
    task.metadata = meta

    deps_met = await store.are_dependencies_met(task.task_id)
    task.status = TaskStatus.READY if deps_met else TaskStatus.BACKLOG
    saved = await store.save_task(task)

    await store.append_event(
        task.task_id,
        TaskEventKind.SPECIFIED,
        payload={
            "author": author,
            "new_title": new_title,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "promoted_to": saved.status.value,
            "reason": reason,
        },
    )
    if saved.status == TaskStatus.READY:
        await store.append_event(
            task.task_id,
            TaskEventKind.PROMOTED,
            payload={"from": TaskStatus.TRIAGE.value, "to": saved.status.value},
        )

    wake_dispatcher(saved.board_id)
    publish_event(
        saved.board_id,
        task.task_id,
        "specified",
        title=saved.title,
        status=saved.status.value,
    )
    return SpecifyOutcome(
        task_id=task.task_id,
        ok=True,
        reason=reason,
        new_title=new_title,
        new_body=new_body,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        persisted=True,
    )


async def run_specify_task(
    task_id: str,
    *,
    store: SqlAlchemyKanbanStore,
    specifier: TaskSpecifier | None,
    wake_dispatcher: _DispatcherWaker,
    publish_event: _EventPublisher,
    persist: bool = False,
    author: str = "specifier",
) -> SpecifyOutcome:
    """Run the TaskSpecifier on a single TRIAGE task.

    persist=False  -> preview only (UI Apply/Reject loop, no side effects).
    persist=True   -> write spec, emit SPECIFIED/PROMOTED events, promote to
                     READY (or BACKLOG when deps unmet), wake dispatcher.
    """
    if specifier is None:
        return SpecifyOutcome(
            task_id=task_id, ok=False, reason="specifier_unavailable",
        )

    task = await store.get_task(task_id)
    if task is None:
        return SpecifyOutcome(
            task_id=task_id, ok=False, reason="unknown_task",
        )

    outcome = await specifier.specify(task, persist=persist)
    if not persist or not outcome.ok or outcome.new_body is None:
        return outcome

    latest = await store.get_task(task_id)
    if latest is None or latest.status != TaskStatus.TRIAGE:
        return SpecifyOutcome(
            task_id=task_id, ok=False, reason="race_lost",
            new_title=outcome.new_title, new_body=outcome.new_body,
            prompt_tokens=outcome.prompt_tokens,
            completion_tokens=outcome.completion_tokens,
            persisted=False,
        )

    return await _persist_spec(
        latest,
        new_title=outcome.new_title,
        new_body=outcome.new_body,
        prompt_tokens=outcome.prompt_tokens,
        completion_tokens=outcome.completion_tokens,
        reason=outcome.reason,
        store=store,
        wake_dispatcher=wake_dispatcher,
        publish_event=publish_event,
        author=author,
    )


async def run_apply_spec(
    task_id: str,
    *,
    new_title: str | None,
    new_body: str,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    store: SqlAlchemyKanbanStore,
    wake_dispatcher: _DispatcherWaker,
    publish_event: _EventPublisher,
    author: str = "specifier",
) -> SpecifyOutcome:
    """Persist a previously-previewed spec without re-invoking the LLM.

    Called by the frontend after the user reviews a dry-run outcome and clicks
    "Apply & Promote".  Receives the cached spec content produced during
    preview so the LLM is never called twice for the same specification.
    """
    task = await store.get_task(task_id)
    if task is None:
        return SpecifyOutcome(
            task_id=task_id, ok=False, reason="unknown_task",
        )
    if task.status != TaskStatus.TRIAGE:
        return SpecifyOutcome(
            task_id=task_id, ok=False, reason="race_lost",
            new_title=new_title, new_body=new_body,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            persisted=False,
        )

    return await _persist_spec(
        task,
        new_title=new_title,
        new_body=new_body,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        reason="applied_from_preview",
        store=store,
        wake_dispatcher=wake_dispatcher,
        publish_event=publish_event,
        author=author,
    )


async def run_specify_all_triage(
    board_id: str,
    *,
    store: SqlAlchemyKanbanStore,
    specify_one: Callable[[str, bool, str], Awaitable[SpecifyOutcome]],
    persist: bool = False,
    author: str = "specifier",
    max_concurrent: int = SPECIFY_ALL_MAX_CONCURRENT,
) -> list[SpecifyOutcome]:
    """Batch-specify every TRIAGE task on a board (bounded concurrency).

    Individual failures do not abort the sweep — the caller gets one outcome
    per task in arrival order.
    """
    triage_tasks = await store.list_tasks(board_id, status=TaskStatus.TRIAGE)
    if not triage_tasks:
        return []

    semaphore = asyncio.Semaphore(max(1, max_concurrent))

    async def _one(task: KanbanTask) -> SpecifyOutcome:
        async with semaphore:
            return await specify_one(task.task_id, persist, author)

    return await asyncio.gather(*(_one(t) for t in triage_tasks))
