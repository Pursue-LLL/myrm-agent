"""Tests for decompose orchestration (TRIAGE -> child graph).

Covers: run_apply_decompose child task creation, model_override inheritance,
dependency wiring, and root task promotion.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from myrm_agent_harness.toolkits.kanban.protocols import DecomposeChildSpec
from myrm_agent_harness.toolkits.kanban.types import KanbanTask, TaskStatus

from app.services.kanban.decompose import run_apply_decompose


def _triage_task(model_override: str | None = None) -> KanbanTask:
    return KanbanTask(
        task_id="root-1",
        board_id="board-1",
        title="Root",
        status=TaskStatus.TRIAGE,
        model_override=model_override,
    )


def _make_store(task: KanbanTask) -> AsyncMock:
    store = AsyncMock()
    store.get_task.return_value = task
    store.save_task.return_value = task
    store.append_event.return_value = None
    return store


def _make_child(task_id: str) -> KanbanTask:
    return KanbanTask(task_id=task_id, board_id="board-1", title=f"Child {task_id}")


async def _run(
    *,
    store: AsyncMock,
    task_model: str | None,
) -> list[dict[str, object]]:
    add_calls: list[dict[str, object]] = []

    async def add_task_fn(**kwargs: object) -> KanbanTask:
        add_calls.append(kwargs)
        return _make_child(f"c{len(add_calls)}")

    outcome = await run_apply_decompose(
        "root-1",
        children=[
            DecomposeChildSpec(title="T1", body="B1"),
            DecomposeChildSpec(title="T2", body="B2", parent_indices=(0,)),
        ],
        rationale="split",
        prompt_tokens=100,
        completion_tokens=50,
        store=store,
        add_task_fn=add_task_fn,
        wake_dispatcher=AsyncMock(),
        publish_event=AsyncMock(),
    )
    assert outcome.ok
    return add_calls


@pytest.mark.asyncio
async def test_children_inherit_parent_model_override() -> None:
    store = _make_store(_triage_task(model_override="anthropic/claude-sonnet-4"))
    calls = await _run(store=store, task_model="anthropic/claude-sonnet-4")

    assert len(calls) == 2
    for call in calls:
        assert call["model_override"] == "anthropic/claude-sonnet-4"


@pytest.mark.asyncio
async def test_children_get_none_model_when_parent_has_none() -> None:
    store = _make_store(_triage_task())
    calls = await _run(store=store, task_model=None)

    assert len(calls) == 2
    for call in calls:
        assert call["model_override"] is None


@pytest.mark.asyncio
async def test_child_dependency_edges_wired() -> None:
    store = _make_store(_triage_task())
    calls = await _run(store=store, task_model=None)

    assert calls[0]["parent_task_id"] == "root-1"
    assert calls[0]["depends_on"] is None
    assert calls[1]["parent_task_id"] == "root-1"
    assert calls[1]["depends_on"] == ["c1"]


@pytest.mark.asyncio
async def test_root_promoted_to_backlog_and_events() -> None:
    task = _triage_task()
    store = _make_store(task)
    wake = AsyncMock()
    publish = AsyncMock()

    async def add_task_fn(**kwargs: object) -> KanbanTask:
        return _make_child("c1")

    outcome = await run_apply_decompose(
        "root-1",
        children=[DecomposeChildSpec(title="T1", body="B1")],
        rationale="split",
        prompt_tokens=100,
        completion_tokens=50,
        store=store,
        add_task_fn=add_task_fn,
        wake_dispatcher=wake,
        publish_event=publish,
    )

    assert outcome.persisted
    assert outcome.child_ids == ("c1",)
    assert task.status == TaskStatus.BACKLOG
    assert store.save_task.await_count == 1
    store.append_event.assert_awaited_once()
    wake.assert_called_once_with("board-1")
    publish.assert_called_once()


@pytest.mark.asyncio
async def test_non_triage_task_rejected() -> None:
    store = _make_store(KanbanTask(task_id="r", board_id="b", title="R", status=TaskStatus.READY))
    outcome = await run_apply_decompose(
        "r",
        children=[DecomposeChildSpec(title="T1", body="B1")],
        rationale="x",
        prompt_tokens=None,
        completion_tokens=None,
        store=store,
        add_task_fn=AsyncMock(),
        wake_dispatcher=AsyncMock(),
        publish_event=AsyncMock(),
    )
    assert not outcome.ok
    assert outcome.reason == "race_lost"


@pytest.mark.asyncio
async def test_child_checklist_parsed_into_metadata_patch() -> None:
    """LLM-derived - [ ] checklist on a child body becomes completion_criteria."""
    store = _make_store(_triage_task())
    add_calls: list[dict[str, object]] = []

    async def add_task_fn(**kwargs: object) -> KanbanTask:
        add_calls.append(kwargs)
        return _make_child(f"c{len(add_calls)}")

    body = "**Goal**\nDo the thing.\n\n**Acceptance criteria**\n- [ ] Item A\n- [ ] Item B\n"
    outcome = await run_apply_decompose(
        "root-1",
        children=[
            DecomposeChildSpec(title="T1", body=body),
            DecomposeChildSpec(title="T2", body="No checklist"),
        ],
        rationale="split",
        prompt_tokens=None,
        completion_tokens=None,
        store=store,
        add_task_fn=add_task_fn,
        wake_dispatcher=AsyncMock(),
        publish_event=AsyncMock(),
    )
    assert outcome.ok
    assert add_calls[0]["metadata_patch"]["completion_criteria"] == [
        {"type": "semantic", "criteria": "Item A"},
        {"type": "semantic", "criteria": "Item B"},
    ]
    # No checklist -> no metadata patch at all (None), keeping inherited
    # metadata semantics unchanged.
    assert add_calls[1]["metadata_patch"] is None


@pytest.mark.asyncio
async def test_child_with_source_chat_keeps_metadata_plus_criteria() -> None:
    """When inherited metadata exists, parsed criteria merge alongside it."""
    store = _make_store(_triage_task())
    add_calls: list[dict[str, object]] = []

    async def add_task_fn(**kwargs: object) -> KanbanTask:
        add_calls.append(kwargs)
        return _make_child("c1")

    # Simulate a parent carrying source_chat metadata (the only field
    # inherit_source_chat_metadata copies).
    parent = _triage_task()
    parent.metadata = {"source_chat_id": "chat-123"}
    store.get_task.return_value = parent

    outcome = await run_apply_decompose(
        "root-1",
        children=[DecomposeChildSpec(title="T1", body="- [ ] Item A\n")],
        rationale="split",
        prompt_tokens=None,
        completion_tokens=None,
        store=store,
        add_task_fn=add_task_fn,
        wake_dispatcher=AsyncMock(),
        publish_event=AsyncMock(),
    )
    assert outcome.ok
    patch = add_calls[0]["metadata_patch"]
    assert patch is not None
    assert patch["source_chat_id"] == "chat-123"
    assert patch["completion_criteria"] == [{"type": "semantic", "criteria": "Item A"}]
