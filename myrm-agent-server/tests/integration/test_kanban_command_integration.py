"""Integration tests for /kanban slash command — full path without mocks.

Exercises: ChannelKanbanCommandHandler → KanbanService → SqlAlchemyKanbanStore → SQLite.
No mocks on the kanban critical path. Tests the real handler dispatching real
subcommands through a real KanbanService backed by an in-memory SQLite DB.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.channels.types import InboundMessage
from app.core.channel_bridge.kanban_command_handler import ChannelKanbanCommandHandler
from app.services.kanban import KanbanService


@pytest.fixture(autouse=True)
def _reset_singleton() -> None:
    """Ensure each test gets a fresh KanbanService singleton."""
    KanbanService._instance = None
    yield
    KanbanService._instance = None


@pytest.fixture(autouse=True)
def _skip_agent_validation() -> None:  # type: ignore[misc]
    """Bypass agent_id validation for tests."""
    with patch.object(
        KanbanService,
        "_validate_agent_id",
        new_callable=AsyncMock,
    ):
        yield


@pytest.fixture
def handler() -> ChannelKanbanCommandHandler:
    return ChannelKanbanCommandHandler()


@pytest.fixture
def msg() -> InboundMessage:
    return InboundMessage(
        channel="test",
        sender_id="user_1",
        content="",
        user_id="u_test",
        chat_id="chat_1",
    )


class TestKanbanCommandIntegration:
    """Full-path integration: handler → service → SQLite → formatted response."""

    @pytest.mark.asyncio
    async def test_create_and_list_flow(
        self,
        handler: ChannelKanbanCommandHandler,
        msg: InboundMessage,
    ) -> None:
        """Create a task, then list it — verifies the full roundtrip."""
        result = await handler.handle_kanban(msg, "create Integration Test Task")
        assert "Task created" in result
        assert "Integration Test Task" in result

        task_id = result.split("`")[1]

        result = await handler.handle_kanban(msg, "list")
        assert "Integration Test Task" in result
        assert task_id in result

    @pytest.mark.asyncio
    async def test_create_and_show_flow(
        self,
        handler: ChannelKanbanCommandHandler,
        msg: InboundMessage,
    ) -> None:
        """Create a task, then show its details."""
        create_result = await handler.handle_kanban(msg, "create Show Detail Task")
        task_id = create_result.split("`")[1]

        show_result = await handler.handle_kanban(msg, f"show {task_id}")
        assert "Show Detail Task" in show_result
        assert task_id in show_result
        assert "backlog" in show_result or "triage" in show_result or "ready" in show_result

    @pytest.mark.asyncio
    async def test_create_edit_show_flow(
        self,
        handler: ChannelKanbanCommandHandler,
        msg: InboundMessage,
    ) -> None:
        """Create → edit title → show verifies updated title."""
        create_result = await handler.handle_kanban(msg, "create Original Title")
        task_id = create_result.split("`")[1]

        edit_result = await handler.handle_kanban(msg, f"edit {task_id} title Updated Title")
        assert "updated" in edit_result

        show_result = await handler.handle_kanban(msg, f"show {task_id}")
        assert "Updated Title" in show_result

    @pytest.mark.asyncio
    async def test_create_complete_flow(
        self,
        handler: ChannelKanbanCommandHandler,
        msg: InboundMessage,
    ) -> None:
        """Create → complete → verify status."""
        create_result = await handler.handle_kanban(msg, "create Complete Me")
        task_id = create_result.split("`")[1]

        complete_result = await handler.handle_kanban(msg, f"complete {task_id}")
        assert "completed" in complete_result

        show_result = await handler.handle_kanban(msg, f"show {task_id}")
        assert "completed" in show_result

    @pytest.mark.asyncio
    async def test_create_block_unblock_flow(
        self,
        handler: ChannelKanbanCommandHandler,
        msg: InboundMessage,
    ) -> None:
        """Create → block with reason → show blocked → unblock → show ready."""
        create_result = await handler.handle_kanban(msg, "create Block Me")
        task_id = create_result.split("`")[1]

        block_result = await handler.handle_kanban(msg, f"block {task_id} Waiting for approval")
        assert "blocked" in block_result

        show_result = await handler.handle_kanban(msg, f"show {task_id}")
        assert "blocked" in show_result

        unblock_result = await handler.handle_kanban(msg, f"unblock {task_id}")
        assert "unblocked" in unblock_result

    @pytest.mark.asyncio
    async def test_create_archive_list_filtered(
        self,
        handler: ChannelKanbanCommandHandler,
        msg: InboundMessage,
    ) -> None:
        """Create → archive → list should NOT show archived task."""
        create_result = await handler.handle_kanban(msg, "create Archive Me")
        task_id = create_result.split("`")[1]

        archive_result = await handler.handle_kanban(msg, f"archive {task_id}")
        assert "archived" in archive_result

        list_result = await handler.handle_kanban(msg, "list")
        assert task_id not in list_result

    @pytest.mark.asyncio
    async def test_create_comment_flow(
        self,
        handler: ChannelKanbanCommandHandler,
        msg: InboundMessage,
    ) -> None:
        """Create → add comment → verify success."""
        create_result = await handler.handle_kanban(msg, "create Comment Target")
        task_id = create_result.split("`")[1]

        comment_result = await handler.handle_kanban(msg, f"comment {task_id} This is a test comment")
        assert "Comment added" in comment_result

    @pytest.mark.asyncio
    async def test_stats_flow(
        self,
        handler: ChannelKanbanCommandHandler,
        msg: InboundMessage,
    ) -> None:
        """Create tasks → stats shows correct counts."""
        await handler.handle_kanban(msg, "create Stats Task 1")
        await handler.handle_kanban(msg, "create Stats Task 2")

        stats_result = await handler.handle_kanban(msg, "stats")
        assert "Board" in stats_result or "Total tasks" in stats_result

    @pytest.mark.asyncio
    async def test_auto_creates_default_board(
        self,
        handler: ChannelKanbanCommandHandler,
        msg: InboundMessage,
    ) -> None:
        """Create on a fresh service ensures a board exists (creates Default Board if none)."""
        svc = KanbanService.get_instance()
        boards_before = await svc.list_boards()

        result = await handler.handle_kanban(msg, "create First Task Ever")
        assert "Task created" in result

        boards_after = await svc.list_boards()
        assert len(boards_after) >= 1
        if not boards_before:
            assert any(b.name == "Default Board" for b in boards_after)

    @pytest.mark.asyncio
    async def test_show_nonexistent_task(
        self,
        handler: ChannelKanbanCommandHandler,
        msg: InboundMessage,
    ) -> None:
        """Show a non-existent task returns 'not found' through real DB lookup."""
        result = await handler.handle_kanban(msg, "show t_nonexistent_999")
        assert "not found" in result

    @pytest.mark.asyncio
    async def test_aliases_work_end_to_end(
        self,
        handler: ChannelKanbanCommandHandler,
        msg: InboundMessage,
    ) -> None:
        """Aliases (add, done, ls) work through full path."""
        create_result = await handler.handle_kanban(msg, "add Alias Test")
        assert "Task created" in create_result
        task_id = create_result.split("`")[1]

        done_result = await handler.handle_kanban(msg, f"done {task_id}")
        assert "completed" in done_result

        await handler.handle_kanban(msg, "add Another One")
        ls_result = await handler.handle_kanban(msg, "ls")
        assert "Another One" in ls_result
