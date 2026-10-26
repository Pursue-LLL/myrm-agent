"""Unit tests for progress storage, schemas, and SSE events."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from myrm_agent_harness.agent.meta_tools.progress.events import emit_todo_progress_events
from myrm_agent_harness.agent.meta_tools.progress.schemas import TodoItem, TodoStatus, TodoStore
from myrm_agent_harness.agent.meta_tools.progress.storage import (
    delete_todos_sync_from_workspace,
    merge_todo_items,
    parse_todo_payload,
    read_todos_sync_from_workspace,
    todo_scope,
    todos_path,
    workspace_todos_exist,
    write_todos_sync_to_workspace,
)
from myrm_agent_harness.core.context_vars import chat_id_var, scoped_value


def test_todos_path_is_one_directory_per_chat_under_myrm_progress(tmp_path) -> None:
    assert todos_path(str(tmp_path), "c1") == tmp_path / ".myrm" / "progress" / "c1" / "todos.json"


def test_a_session_key_and_its_chat_id_name_the_same_todo_list(tmp_path) -> None:
    assert todos_path(str(tmp_path), "chat_c1") == todos_path(str(tmp_path), "c1")


def test_todo_scope_defaults_to_the_running_chat() -> None:
    with scoped_value(chat_id_var, "c7"):
        assert todo_scope() == "c7"
    assert todo_scope("c8") == "c8"


def test_a_run_without_a_chat_shares_the_default_scope() -> None:
    with scoped_value(chat_id_var, ""):
        assert todo_scope() == "default"
    assert todo_scope("chat_") == "default"


@pytest.mark.parametrize("chat_id", ["../../etc", "a/b", "..", ".hidden", "a\\b"])
def test_a_chat_id_never_names_a_path_outside_the_progress_directory(tmp_path, chat_id: str) -> None:
    progress_dir = tmp_path / ".myrm" / "progress"
    path = todos_path(str(tmp_path), chat_id)
    assert path.parent.parent == progress_dir
    assert path.parent.name == todo_scope(chat_id)
    assert path.parent.name not in {"", ".", ".."}


def test_each_chat_reads_only_its_own_list(tmp_path) -> None:
    write_todos_sync_to_workspace(str(tmp_path), TodoStore(goal="a", todos=[]), "chat_a")
    write_todos_sync_to_workspace(str(tmp_path), TodoStore(goal="b", todos=[]), "chat_b")
    first = read_todos_sync_from_workspace(str(tmp_path), "a")
    second = read_todos_sync_from_workspace(str(tmp_path), "b")
    assert first is not None and first.goal == "a"
    assert second is not None and second.goal == "b"
    assert read_todos_sync_from_workspace(str(tmp_path), "c") is None


def test_deleting_one_chats_list_leaves_the_others(tmp_path) -> None:
    write_todos_sync_to_workspace(str(tmp_path), TodoStore(goal="a", todos=[]), "a")
    write_todos_sync_to_workspace(str(tmp_path), TodoStore(goal="b", todos=[]), "b")
    delete_todos_sync_from_workspace(str(tmp_path), "a")
    assert read_todos_sync_from_workspace(str(tmp_path), "a") is None
    assert read_todos_sync_from_workspace(str(tmp_path), "b") is not None


def test_read_todos_missing_file_returns_none(tmp_path) -> None:
    assert read_todos_sync_from_workspace(str(tmp_path)) is None


def test_read_todos_invalid_json_returns_none(tmp_path) -> None:
    path = todos_path(str(tmp_path))
    path.parent.mkdir(parents=True)
    path.write_text("not-json", encoding="utf-8")
    assert read_todos_sync_from_workspace(str(tmp_path)) is None


def test_read_todos_non_object_root_returns_none(tmp_path) -> None:
    path = todos_path(str(tmp_path))
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps([1, 2]), encoding="utf-8")
    assert read_todos_sync_from_workspace(str(tmp_path)) is None


def test_write_and_read_roundtrip(tmp_path) -> None:
    store = TodoStore(
        goal="OAuth migration",
        todos=[TodoItem(id="1", content="Read code", status=TodoStatus.IN_PROGRESS)],
    )
    write_todos_sync_to_workspace(str(tmp_path), store)
    loaded = read_todos_sync_from_workspace(str(tmp_path))
    assert loaded is not None
    assert loaded.goal == "OAuth migration"
    assert loaded.todos[0].status == TodoStatus.IN_PROGRESS


def test_delete_todos_removes_file(tmp_path) -> None:
    store = TodoStore(todos=[TodoItem(id="1", content="x", status=TodoStatus.PENDING)])
    write_todos_sync_to_workspace(str(tmp_path), store)
    delete_todos_sync_from_workspace(str(tmp_path))
    assert read_todos_sync_from_workspace(str(tmp_path)) is None


def test_merge_todo_items_replace_mode() -> None:
    current = [TodoItem(id="1", content="a", status=TodoStatus.PENDING)]
    incoming = [TodoItem(id="2", content="b", status=TodoStatus.IN_PROGRESS)]
    merged = merge_todo_items(current, incoming, merge=False)
    assert [item.id for item in merged] == ["2"]


def test_merge_todo_items_merge_mode_preserves_order_and_updates() -> None:
    current = [
        TodoItem(id="1", content="a", status=TodoStatus.PENDING),
        TodoItem(id="2", content="b", status=TodoStatus.PENDING),
    ]
    incoming = [
        TodoItem(id="1", content="a done", status=TodoStatus.COMPLETED),
        TodoItem(id="3", content="c", status=TodoStatus.PENDING),
    ]
    merged = merge_todo_items(current, incoming, merge=True)
    assert [item.id for item in merged] == ["1", "2", "3"]
    assert merged[0].status == TodoStatus.COMPLETED


def test_merge_todo_items_preserves_status_when_status_omitted() -> None:
    """When merge=True and incoming payload only updates content, keep existing status."""
    current = [
        TodoItem(id="1", content="original content", status=TodoStatus.IN_PROGRESS),
        TodoItem(id="2", content="task 2", status=TodoStatus.COMPLETED),
    ]
    incoming = parse_todo_payload(
        [{"id": "1", "content": "refined content"}],
        allow_empty_content=True,
    )
    merged = merge_todo_items(current, incoming, merge=True)
    assert len(merged) == 2
    assert merged[0].id == "1"
    assert merged[0].content == "refined content"
    assert merged[0].status == TodoStatus.IN_PROGRESS  # Must not reset to PENDING
    assert merged[1].status == TodoStatus.COMPLETED


def test_parse_todo_payload_valid() -> None:
    items = parse_todo_payload([{"id": "1", "content": "step", "status": "in_progress"}])
    assert len(items) == 1
    assert items[0].status == TodoStatus.IN_PROGRESS


@pytest.mark.parametrize(
    ("payload", "match"),
    [
        ([1], "must be an object"),
        ([{"id": "1", "content": "x", "status": "bogus"}], "is invalid"),
    ],
)
def test_parse_todo_payload_validation_errors(payload: list[object], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        parse_todo_payload(payload)


def test_parse_todo_payload_tolerates_missing_id_and_synonym_keys() -> None:
    items = parse_todo_payload([{"task": "Auto task without explicit id", "status": "pending"}])
    assert len(items) == 1
    assert items[0].id == "task_1"
    assert items[0].content == "Auto task without explicit id"


def test_merge_todo_items_falls_back_to_id_when_content_empty() -> None:
    merged = merge_todo_items([], [TodoItem(id="1", content="")], merge=False)
    assert len(merged) == 1
    assert merged[0].content == "1"


def test_incomplete_todos_excludes_completed_and_cancelled() -> None:
    store = TodoStore(
        todos=[
            TodoItem(id="1", content="a", status=TodoStatus.COMPLETED),
            TodoItem(id="2", content="b", status=TodoStatus.CANCELLED),
            TodoItem(id="3", content="c", status=TodoStatus.IN_PROGRESS),
        ]
    )
    incomplete = store.incomplete_todos()
    assert len(incomplete) == 1
    assert incomplete[0].id == "3"


def test_to_plan_compat_maps_all_statuses() -> None:
    store = TodoStore(
        goal=None,
        revision=42,
        todos=[
            TodoItem(id="1", content="a", status=TodoStatus.IN_PROGRESS),
            TodoItem(id="2", content="b", status=TodoStatus.COMPLETED),
            TodoItem(id="3", content="c", status=TodoStatus.CANCELLED),
            TodoItem(id="4", content="d", status=TodoStatus.PENDING),
            TodoItem(id="5", content="e", status=TodoStatus.BLOCKED),
        ],
    )
    plan = store.to_plan_compat()
    assert plan["goal"] == "Task progress"
    assert plan["revision"] == 42
    assert plan["reasoning"] == ""
    steps = plan["steps"]
    assert len(steps) == 5
    assert steps[0] == {"step_id": "1", "description": "a", "expected_output": "", "status": "in_progress"}
    assert steps[1] == {"step_id": "2", "description": "b", "expected_output": "", "status": "completed"}
    assert steps[2] == {"step_id": "3", "description": "c", "expected_output": "", "status": "skipped"}
    assert steps[3] == {"step_id": "4", "description": "d", "expected_output": "", "status": "pending"}
    assert steps[4] == {"step_id": "5", "description": "e", "expected_output": "", "status": "blocked"}


def test_merge_todo_items_status_only_update_preserves_content() -> None:
    """When merge=True and incoming payload only updates status, keep existing content."""
    current = [
        TodoItem(id="step_a", content="Do step A carefully", status=TodoStatus.PENDING),
    ]
    incoming = parse_todo_payload(
        [{"id": "step_a", "status": "completed"}],
        allow_empty_content=True,
    )
    merged = merge_todo_items(current, incoming, merge=True)
    assert len(merged) == 1
    assert merged[0].id == "step_a"
    assert merged[0].content == "Do step A carefully"
    assert merged[0].status == TodoStatus.COMPLETED


def test_workspace_todos_exist_no_root() -> None:
    assert workspace_todos_exist(workspace_root=None) is False
    assert workspace_todos_exist(workspace_root="") is False


def test_workspace_todos_exist_is_false_for_a_workspace_without_lists(tmp_path) -> None:
    assert workspace_todos_exist(workspace_root=str(tmp_path)) is False
    (tmp_path / ".myrm" / "progress" / "empty_chat").mkdir(parents=True)
    assert workspace_todos_exist(workspace_root=str(tmp_path)) is False


def test_workspace_todos_exist_when_any_chat_has_a_list(tmp_path) -> None:
    store = TodoStore(todos=[TodoItem(id="1", content="x", status=TodoStatus.PENDING)])
    write_todos_sync_to_workspace(str(tmp_path), store, "some_chat")
    assert workspace_todos_exist(workspace_root=str(tmp_path)) is True


def test_a_list_in_the_old_flat_layout_is_not_a_chat_list(tmp_path) -> None:
    flat = tmp_path / ".myrm" / "progress" / "todos.json"
    flat.parent.mkdir(parents=True)
    flat.write_text('{"goal":"g","todos":[{"id":"1","content":"x","status":"pending"}]}', encoding="utf-8")
    assert workspace_todos_exist(workspace_root=str(tmp_path)) is False
    assert read_todos_sync_from_workspace(str(tmp_path), "any_chat") is None


def test_emit_todo_progress_events_dispatches_root_and_steps() -> None:
    store = TodoStore(
        goal="My goal",
        todos=[
            TodoItem(id="1", content="step one", status=TodoStatus.COMPLETED),
            TodoItem(id="2", content="step two", status=TodoStatus.CANCELLED),
            TodoItem(id="3", content="step three", status=TodoStatus.BLOCKED),
        ],
    )
    with patch("myrm_agent_harness.agent.meta_tools.progress.events.dispatch_custom_event") as mock_dispatch:
        emit_todo_progress_events(store)
    assert mock_dispatch.call_count == 4
    root_call = mock_dispatch.call_args_list[0].args
    assert root_call[0] == "tasks_steps"
    assert root_call[1]["step_key"] == "progress_root"
    assert "revision" in root_call[1]
    step_statuses = [call.args[1]["status"] for call in mock_dispatch.call_args_list[1:]]
    assert step_statuses == ["success", "skipped", "blocked"]
    assert all("revision" in call.args[1] for call in mock_dispatch.call_args_list[1:])


def test_emit_todo_progress_events_swallows_dispatch_errors() -> None:
    store = TodoStore(todos=[TodoItem(id="1", content="x", status=TodoStatus.PENDING)])
    with patch(
        "myrm_agent_harness.agent.meta_tools.progress.events.dispatch_custom_event",
        side_effect=RuntimeError("sse down"),
    ):
        emit_todo_progress_events(store)


def test_todo_status_to_plan_status_mapping() -> None:
    from myrm_agent_harness.agent.meta_tools.progress.schemas import _todo_status_to_plan_status

    assert _todo_status_to_plan_status(TodoStatus.BLOCKED) == "blocked"
    assert _todo_status_to_plan_status(TodoStatus.IN_PROGRESS) == "in_progress"
    assert _todo_status_to_plan_status(TodoStatus.COMPLETED) == "completed"
    assert _todo_status_to_plan_status(TodoStatus.CANCELLED) == "skipped"
    assert _todo_status_to_plan_status(TodoStatus.PENDING) == "pending"
