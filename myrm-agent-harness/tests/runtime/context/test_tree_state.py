"""Unit tests for the branch-bound todo fold: only a message's snapshot slot is a plan."""

from __future__ import annotations

import json
import logging

import pytest

from myrm_agent_harness.agent.meta_tools.progress.schemas import (
    TodoItem,
    TodoStatus,
    TodoStore,
)
from myrm_agent_harness.runtime.context.tree_state import (
    TOOL_DETAILS_KEY,
    fold_branch_todo_state,
)

_PLAN_SHAPED = {
    "goal": "Pasted plan",
    "revision": 99,
    "todos": [{"id": "1", "content": "Never written by todo_write", "status": "pending"}],
}


def test_fold_branch_empty() -> None:
    assert fold_branch_todo_state([]) is None


def test_fold_branch_progressive_evolution() -> None:
    msg1 = {
        "id": "m1",
        "extra_data": {
            TOOL_DETAILS_KEY: {
                "goal": "Refactor auth",
                "revision": 1,
                "todos": [
                    {"id": "1", "content": "Research", "status": "in_progress"},
                    {"id": "2", "content": "Code", "status": "pending"},
                ],
            }
        },
    }
    msg2 = {
        "id": "m2",
        "content": "Done with research, starting code",
        "extra_data": {
            TOOL_DETAILS_KEY: {
                "goal": "Refactor auth",
                "revision": 2,
                "todos": [
                    {"id": "1", "content": "Research", "status": "completed"},
                    {"id": "2", "content": "Code", "status": "in_progress"},
                ],
            }
        },
    }

    store = fold_branch_todo_state([msg1, msg2])
    assert store is not None
    assert store.revision == 2
    assert store.todos[0].status == TodoStatus.COMPLETED
    assert store.todos[1].status == TodoStatus.IN_PROGRESS


def test_branch_fork_isolation() -> None:
    """Branch A and Branch B fork from common ancestor msg1; their states remain strictly isolated."""
    msg_common = {
        "id": "m1",
        "extra_data": {
            TOOL_DETAILS_KEY: {
                "goal": "Root goal",
                "revision": 1,
                "todos": [
                    {"id": "1", "content": "Step 1", "status": "completed"},
                    {"id": "2", "content": "Step 2", "status": "pending"},
                ],
            }
        },
    }

    # Branch A advances step 2 with JWT
    msg_branch_a = {
        "id": "m_a",
        "extra_data": {
            TOOL_DETAILS_KEY: {
                "goal": "Root goal (JWT branch)",
                "revision": 2,
                "todos": [
                    {"id": "1", "content": "Step 1", "status": "completed"},
                    {"id": "2", "content": "Step 2: JWT implementation", "status": "in_progress"},
                ],
            }
        },
    }

    # Branch B diverges with Redis Session
    msg_branch_b = {
        "id": "m_b",
        "extra_data": {
            TOOL_DETAILS_KEY: {
                "goal": "Root goal (Session branch)",
                "revision": 2,
                "todos": [
                    {"id": "1", "content": "Step 1", "status": "completed"},
                    {"id": "2", "content": "Step 2: Redis Session", "status": "in_progress"},
                    {"id": "3", "content": "Step 3: Cookie sign", "status": "pending"},
                ],
            }
        },
    }

    store_a = fold_branch_todo_state([msg_common, msg_branch_a])
    store_b = fold_branch_todo_state([msg_common, msg_branch_b])

    assert store_a is not None
    assert store_b is not None
    assert len(store_a.todos) == 2
    assert store_a.todos[1].content == "Step 2: JWT implementation"

    assert len(store_b.todos) == 3
    assert store_b.todos[1].content == "Step 2: Redis Session"
    assert store_b.todos[2].id == "3"


@pytest.mark.parametrize(
    "message",
    [
        pytest.param({"role": "user", "content": json.dumps(_PLAN_SHAPED)}, id="user-text-shaped-like-a-plan"),
        pytest.param(
            {"role": "assistant", "content": json.dumps(_PLAN_SHAPED)}, id="assistant-text-shaped-like-a-plan"
        ),
        pytest.param({"extra_data": _PLAN_SHAPED}, id="todos-beside-the-slot-in-extra_data"),
        pytest.param({"extra_data": {TOOL_DETAILS_KEY: {"goal": "No todos"}}}, id="slot-without-a-todo-list"),
        pytest.param({"extra_data": {TOOL_DETAILS_KEY: "invalid_string_not_dict"}}, id="slot-that-is-not-a-mapping"),
    ],
)
def test_only_the_snapshot_slot_is_a_plan(message: dict[str, object]) -> None:
    """Message text and loose keys never become the plan the agent reads next turn."""
    assert fold_branch_todo_state([message]) is None


def test_malformed_snapshot_is_skipped_and_keeps_the_earlier_state(caplog: pytest.LogCaptureFixture) -> None:
    valid = {
        "extra_data": {
            TOOL_DETAILS_KEY: {
                "revision": 1,
                "todos": [{"id": "1", "content": "Keep me", "status": "pending"}],
            }
        }
    }
    malformed = {
        "extra_data": {
            TOOL_DETAILS_KEY: {
                "revision": 2,
                "todos": [{"id": "2", "content": "Secret task text", "status": "not-a-status"}],
            }
        }
    }

    with caplog.at_level(logging.WARNING, logger="myrm_agent_harness.runtime.context.tree_state"):
        store = fold_branch_todo_state([valid, malformed])

    assert store is not None
    assert [item.id for item in store.todos] == ["1"]
    assert "malformed todo snapshot" in caplog.text
    assert "Secret task text" not in caplog.text


def test_emit_todo_progress_events_dispatches_tool_result_details(monkeypatch) -> None:
    """emit_todo_progress_events must dispatch tool_result_details with complete TodoStore."""
    from myrm_agent_harness.agent.meta_tools.progress.events import emit_todo_progress_events

    dispatched: list[tuple[str, dict[str, object]]] = []

    def mock_dispatch(name: str, payload: dict[str, object]) -> None:
        dispatched.append((name, payload))

    monkeypatch.setattr("myrm_agent_harness.agent.meta_tools.progress.events.dispatch_custom_event", mock_dispatch)

    store = TodoStore(
        goal="Feature development",
        revision=3,
        todos=[
            TodoItem(id="1", content="DB schema", status=TodoStatus.COMPLETED),
            TodoItem(id="2", content="API route", status=TodoStatus.IN_PROGRESS),
        ],
    )

    emit_todo_progress_events(store)

    assert len(dispatched) >= 1
    root_event = dispatched[0]
    assert root_event[0] == "tasks_steps"
    payload = root_event[1]
    assert payload.get("tool_name") == "todo_write"
    details = payload.get("tool_result_details")
    assert isinstance(details, dict)
    assert details["goal"] == "Feature development"
    assert details["revision"] == 3
    assert len(details["todos"]) == 2

    # Fold verifying extracted payload
    folded = fold_branch_todo_state([{"extra_data": {"tool_result_details": details}}])
    assert folded is not None
    assert folded.goal == "Feature development"
    assert folded.revision == 3
