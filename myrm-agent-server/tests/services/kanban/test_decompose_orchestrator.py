"""Tests for decompose orchestrator metadata inheritance."""

from __future__ import annotations

import pytest
from myrm_agent_harness.toolkits.kanban.protocols import DecomposeChildSpec
from myrm_agent_harness.toolkits.kanban.types import (
    KANBAN_SOURCE_CHAT_METADATA_KEY,
    KanbanTask,
    TaskPriority,
    TaskStatus,
)

from app.services.kanban.decompose_orchestrator import run_apply_decompose


class _MemoryStore:
    def __init__(self) -> None:
        self._tasks: dict[str, KanbanTask] = {}

    async def get_task(self, task_id: str) -> KanbanTask | None:
        return self._tasks.get(task_id)

    async def save_task(self, task: KanbanTask) -> KanbanTask:
        self._tasks[task.task_id] = task
        return task

    async def append_event(self, task_id: str, kind: object, payload: dict[str, object] | None = None) -> None:
        del task_id, kind, payload


@pytest.mark.asyncio
async def test_apply_decompose_inherits_source_chat_id() -> None:
    store = _MemoryStore()
    parent = KanbanTask(
        task_id="parent1",
        board_id="board1",
        title="Parent",
        description="",
        status=TaskStatus.TRIAGE,
        priority=TaskPriority.NORMAL,
        metadata={KANBAN_SOURCE_CHAT_METADATA_KEY: "chat-abc"},
    )
    await store.save_task(parent)

    created_metadata: list[dict[str, object] | None] = []

    async def add_task_fn(
        board_id: str,
        title: str,
        description: str,
        *,
        agent_id: str | None,
        parent_task_id: str | None,
        depends_on: list[str] | None,
        extra_skill_ids: list[str] | None = None,
        metadata_patch: dict[str, object] | None = None,
    ) -> KanbanTask:
        del board_id, description, agent_id, parent_task_id, depends_on, extra_skill_ids
        created_metadata.append(metadata_patch)
        child = KanbanTask(
            task_id=f"child{len(created_metadata)}",
            board_id="board1",
            title=title,
            description="",
            status=TaskStatus.READY,
            priority=TaskPriority.NORMAL,
            metadata=dict(metadata_patch or {}),
        )
        await store.save_task(child)
        return child

    outcome = await run_apply_decompose(
        "parent1",
        children=[
            DecomposeChildSpec(title="Child A", body="Do A", assignee="default", parent_indices=()),
            DecomposeChildSpec(title="Child B", body="Do B", assignee="default", parent_indices=(0,)),
        ],
        rationale="split",
        prompt_tokens=None,
        completion_tokens=None,
        store=store,  # type: ignore[arg-type]
        add_task_fn=add_task_fn,
        wake_dispatcher=lambda _board_id: None,
        publish_event=lambda *_args, **_kwargs: None,
    )

    assert outcome.ok is True
    assert len(created_metadata) == 2
    assert created_metadata[0] == {KANBAN_SOURCE_CHAT_METADATA_KEY: "chat-abc"}
    assert created_metadata[1] == {KANBAN_SOURCE_CHAT_METADATA_KEY: "chat-abc"}

    child = await store.get_task("child1")
    assert child is not None
    assert child.metadata.get(KANBAN_SOURCE_CHAT_METADATA_KEY) == "chat-abc"
