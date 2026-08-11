"""Unit tests for kanban_attach_handler — path bounds, HTTPS, SSRF, and limits."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.core.security.guards.ssrf import SSRFResult
from myrm_agent_harness.toolkits.kanban.stores import InMemoryKanbanStore
from myrm_agent_harness.toolkits.kanban.types import KanbanBoard, KanbanTask, TaskStatus
from myrm_agent_harness.toolkits.storage.types import FilePurpose

from app.core.storage.models import File
from app.services.kanban.kanban_attach_handler import create_kanban_attach_handler


def _sample_file(*, source_chat_id: str | None = None) -> File:
    return File(
        id="file_test123",
        purpose=FilePurpose.GENERATED,
        filename="out.txt",
        content_type="text/plain",
        size=4,
        storage_path="/tmp/out.txt",
        source_chat_id=source_chat_id,
        created_at=datetime.utcnow(),
    )


async def _seed_task_with_workspace(
    store: InMemoryKanbanStore,
    workspace: str,
    *,
    task_id: str = "task_attach",
    branch: str | None = None,
) -> KanbanTask:
    await store.save_board(KanbanBoard(board_id="b1", name="Board"))
    task = KanbanTask(
        task_id=task_id,
        board_id="b1",
        title="Attach task",
        status=TaskStatus.RUNNING,
        workspace_path=workspace,
        branch=branch,
    )
    return await store.save_task(task)


@pytest.mark.asyncio
async def test_attach_path_happy_path(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    sample = workspace / "report.txt"
    sample.write_text("data", encoding="utf-8")

    store = InMemoryKanbanStore()
    await _seed_task_with_workspace(store, str(workspace))

    saved_file = _sample_file(source_chat_id="kanban:task_attach")
    handler = create_kanban_attach_handler(store)

    with (
        patch(
            "app.services.kanban.task_attachment_ids.load_task_attachment_ids",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "app.services.kanban.task_attachment_ids.save_task_attachment_ids",
            new_callable=AsyncMock,
        ) as save_ids,
        patch(
            "app.core.storage.files_service.save_generated_file",
            new_callable=AsyncMock,
            return_value=saved_file,
        ) as save_file,
    ):
        result = await handler("task_attach", "path", "report.txt")

    assert result["file_id"] == "file_test123"
    assert result["attachment_count"] == 1
    save_file.assert_awaited_once()
    assert save_file.await_args.kwargs["source_chat_id"] == "kanban:task_attach"
    save_ids.assert_awaited_once_with("task_attach", ["file_test123"])


@pytest.mark.asyncio
async def test_attach_path_rejects_escape_outside_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "inside.txt").write_text("ok", encoding="utf-8")

    store = InMemoryKanbanStore()
    await _seed_task_with_workspace(store, str(workspace))
    handler = create_kanban_attach_handler(store)

    with patch(
        "app.services.kanban.task_attachment_ids.load_task_attachment_ids",
        new_callable=AsyncMock,
        return_value=[],
    ):
        with pytest.raises(ValueError, match="inside the task workspace"):
            await handler("task_attach", "path", "../outside.txt")


@pytest.mark.asyncio
async def test_attach_path_relative_in_worktree(tmp_path: Path) -> None:
    """Relative paths resolve against the worktree when branch isolation is on."""
    base = tmp_path / "repo"
    base.mkdir()
    worktree = tmp_path / "wt_feat"
    worktree.mkdir()
    (worktree / "report.txt").write_text("data", encoding="utf-8")

    store = InMemoryKanbanStore()
    await _seed_task_with_workspace(store, str(base), branch="feat", task_id="task_wt")
    handler = create_kanban_attach_handler(store)
    saved_file = _sample_file(source_chat_id="kanban:task_wt")

    with (
        patch(
            "app.services.kanban.kanban_attach_handler.resolve_workspace",
            new_callable=AsyncMock,
            return_value=str(worktree),
        ),
        patch(
            "app.services.kanban.task_attachment_ids.load_task_attachment_ids",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "app.services.kanban.task_attachment_ids.save_task_attachment_ids",
            new_callable=AsyncMock,
        ) as save_ids,
        patch(
            "app.core.storage.files_service.save_generated_file",
            new_callable=AsyncMock,
            return_value=saved_file,
        ) as save_file,
    ):
        result = await handler("task_wt", "path", "report.txt")

    assert result["file_id"] == "file_test123"
    save_file.assert_awaited_once()
    assert save_file.await_args.kwargs["source_chat_id"] == "kanban:task_wt"
    assert save_file.await_args.kwargs["filename"] == "report.txt"
    save_ids.assert_awaited_once_with("task_wt", ["file_test123"])


@pytest.mark.asyncio
async def test_attach_path_container_abstract_in_worktree(tmp_path: Path) -> None:
    """Container-abstract /workspace/... paths resolve to the worktree."""
    base = tmp_path / "repo"
    base.mkdir()
    worktree = tmp_path / "wt_feat"
    worktree.mkdir()
    (worktree / "src").mkdir()
    (worktree / "src" / "auth.py").write_text("code", encoding="utf-8")

    store = InMemoryKanbanStore()
    await _seed_task_with_workspace(store, str(base), branch="feat", task_id="task_wt")
    handler = create_kanban_attach_handler(store)
    saved_file = _sample_file(source_chat_id="kanban:task_wt")

    with (
        patch(
            "app.services.kanban.kanban_attach_handler.resolve_workspace",
            new_callable=AsyncMock,
            return_value=str(worktree),
        ),
        patch(
            "app.services.kanban.task_attachment_ids.load_task_attachment_ids",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "app.services.kanban.task_attachment_ids.save_task_attachment_ids",
            new_callable=AsyncMock,
        ),
        patch(
            "app.core.storage.files_service.save_generated_file",
            new_callable=AsyncMock,
            return_value=saved_file,
        ) as save_file,
    ):
        result = await handler("task_wt", "path", "/workspace/src/auth.py")

    assert result["file_id"] == "file_test123"
    save_file.assert_awaited_once()
    assert save_file.await_args.kwargs["filename"] == "auth.py"


@pytest.mark.asyncio
async def test_attach_path_rejects_escape_from_worktree(tmp_path: Path) -> None:
    """Paths escaping the worktree stay rejected even when branch isolation is on."""
    base = tmp_path / "repo"
    base.mkdir()
    (base / "secret.txt").write_text("secret", encoding="utf-8")
    worktree = tmp_path / "wt_feat"
    worktree.mkdir()

    store = InMemoryKanbanStore()
    await _seed_task_with_workspace(store, str(base), branch="feat", task_id="task_wt")
    handler = create_kanban_attach_handler(store)

    with (
        patch(
            "app.services.kanban.kanban_attach_handler.resolve_workspace",
            new_callable=AsyncMock,
            return_value=str(worktree),
        ),
        patch(
            "app.services.kanban.task_attachment_ids.load_task_attachment_ids",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        with pytest.raises(ValueError, match="inside the task workspace"):
            await handler("task_wt", "path", "../secret.txt")


@pytest.mark.asyncio
async def test_attach_url_rejects_non_https() -> None:
    store = InMemoryKanbanStore()
    await _seed_task_with_workspace(store, "/tmp/ws")
    handler = create_kanban_attach_handler(store)

    with patch(
        "app.services.kanban.task_attachment_ids.load_task_attachment_ids",
        new_callable=AsyncMock,
        return_value=[],
    ):
        with pytest.raises(ValueError, match="Only HTTPS"):
            await handler("task_attach", "url", "http://example.com/file.txt")


@pytest.mark.asyncio
async def test_attach_url_rejects_ssrf_blocked() -> None:
    store = InMemoryKanbanStore()
    await _seed_task_with_workspace(store, "/tmp/ws")
    handler = create_kanban_attach_handler(store)

    with (
        patch(
            "app.services.kanban.task_attachment_ids.load_task_attachment_ids",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "app.services.kanban.kanban_attach_handler.async_validate_url_for_ssrf",
            new_callable=AsyncMock,
            return_value=SSRFResult(safe=False, error="blocked host"),
        ),
    ):
        with pytest.raises(ValueError, match="blocked host"):
            await handler("task_attach", "url", "https://evil.example/file.txt")


@pytest.mark.asyncio
async def test_attach_url_happy_path_sets_source_chat_id() -> None:
    store = InMemoryKanbanStore()
    await _seed_task_with_workspace(store, "/tmp/ws")
    handler = create_kanban_attach_handler(store)
    saved_file = _sample_file(source_chat_id="kanban:task_attach")
    response = SimpleNamespace(status_code=200, content=b"body", content_type="text/plain")

    with (
        patch(
            "app.services.kanban.task_attachment_ids.load_task_attachment_ids",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "app.services.kanban.task_attachment_ids.save_task_attachment_ids",
            new_callable=AsyncMock,
        ),
        patch(
            "app.services.kanban.kanban_attach_handler.async_validate_url_for_ssrf",
            new_callable=AsyncMock,
            return_value=SSRFResult(safe=True),
        ),
        patch(
            "app.services.kanban.kanban_attach_handler.secure_get",
            new_callable=AsyncMock,
            return_value=response,
        ),
        patch(
            "app.core.storage.files_service.save_generated_file",
            new_callable=AsyncMock,
            return_value=saved_file,
        ) as save_file,
    ):
        result = await handler("task_attach", "url", "https://cdn.example/report.pdf")

    assert result["file_id"] == "file_test123"
    save_file.assert_awaited_once()
    assert save_file.await_args.kwargs["source_chat_id"] == "kanban:task_attach"


@pytest.mark.asyncio
async def test_attach_rejects_when_attachment_limit_reached() -> None:
    store = InMemoryKanbanStore()
    await _seed_task_with_workspace(store, "/tmp/ws")
    handler = create_kanban_attach_handler(store)
    existing = [f"f{i}" for i in range(10)]

    with patch(
        "app.services.kanban.task_attachment_ids.load_task_attachment_ids",
        new_callable=AsyncMock,
        return_value=existing,
    ):
        with pytest.raises(ValueError, match="maximum of 10"):
            await handler("task_attach", "url", "https://cdn.example/x.bin")
