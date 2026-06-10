"""Tests for /kanban (/kb) slash command — command_defs, protocol, handler dispatch, router mixin."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.protocols.kanban_command import KanbanCommandHandler
from app.channels.routing.command_defs import SYSTEM_COMMANDS, CommandAction
from app.channels.routing.command_registry import CommandRegistry
from app.channels.types import InboundMessage, OutboundMessage


def _make_msg(
    content: str = "",
    channel: str = "test",
    sender_id: str = "user1",
    chat_id: str | None = None,
    is_group: bool = False,
    thread_id: str | None = None,
    user_id: str | None = None,
    message_id: str | None = None,
) -> InboundMessage:
    return InboundMessage(
        channel=channel,
        sender_id=sender_id,
        content=content,
        chat_id=chat_id,
        is_group=is_group,
        thread_id=thread_id,
        user_id=user_id,
        message_id=message_id,
    )


# ── command_defs tests ─────────────────────────────────────────────────


class TestKanbanCommandDef:
    """Tests for /kanban CommandDef registration."""

    def test_kanban_action_exists(self) -> None:
        assert hasattr(CommandAction, "KANBAN")

    def test_kanban_in_system_commands(self) -> None:
        kb_cmds = [c for c in SYSTEM_COMMANDS if c.action == CommandAction.KANBAN]
        assert len(kb_cmds) == 1

    def test_kanban_command_properties(self) -> None:
        kb_cmd = next(c for c in SYSTEM_COMMANDS if c.action == CommandAction.KANBAN)
        assert kb_cmd.name == "kanban"
        assert kb_cmd.parse_args is True
        assert "kb" in kb_cmd.aliases
        assert kb_cmd.category == "Tasks"

    def test_kanban_registered_in_registry(self) -> None:
        registry = CommandRegistry()
        result = registry.resolve("/kanban")
        assert result is not None
        assert result.command_def.action == CommandAction.KANBAN

    def test_kb_alias_resolves(self) -> None:
        registry = CommandRegistry()
        result = registry.resolve("/kb list")
        assert result is not None
        assert result.command_def.action == CommandAction.KANBAN
        assert result.raw_args == "list"

    def test_kanban_with_subcommand(self) -> None:
        registry = CommandRegistry()
        result = registry.resolve("/kanban show t_abc123")
        assert result is not None
        assert result.raw_args == "show t_abc123"


# ── KanbanCommandHandler Protocol tests ────────────────────────────────


class TestKanbanCommandHandlerProtocol:
    """Tests for KanbanCommandHandler protocol compliance."""

    def test_protocol_is_runtime_checkable(self) -> None:
        class MockHandler:
            async def handle_kanban(self, msg: InboundMessage, raw_args: str) -> str:
                return "ok"

        assert isinstance(MockHandler(), KanbanCommandHandler)

    def test_non_handler_fails_check(self) -> None:
        class NotAHandler:
            pass

        assert not isinstance(NotAHandler(), KanbanCommandHandler)

    def test_missing_method_fails_check(self) -> None:
        class MissingMethod:
            async def some_other_method(self) -> str:
                return "ok"

        assert not isinstance(MissingMethod(), KanbanCommandHandler)


# ── ChannelKanbanCommandHandler tests ──────────────────────────────────


def _mock_svc() -> MagicMock:
    """Create a mocked KanbanService with all methods as AsyncMock."""
    svc = MagicMock()
    svc.list_boards = AsyncMock(return_value=[])
    svc.list_tasks = AsyncMock(return_value=[])
    svc.get_task = AsyncMock(return_value=None)
    svc.add_task = AsyncMock()
    svc.add_comment = AsyncMock()
    svc.update_task = AsyncMock()
    svc.move_task = AsyncMock()
    svc.create_board = AsyncMock()
    svc.board_summary = AsyncMock(return_value=None)
    return svc


def _make_task(
    task_id: str = "t_abc",
    title: str = "Test Task",
    status: str = "ready",
    priority: str = "normal",
    description: str = "",
    agent_id: str | None = None,
    error: str = "",
    created_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> MagicMock:
    from myrm_agent_harness.toolkits.kanban.types import TaskPriority, TaskStatus

    task = MagicMock()
    task.task_id = task_id
    task.title = title
    task.status = TaskStatus(status)
    task.priority = TaskPriority(priority)
    task.description = description
    task.agent_id = agent_id
    task.error = error
    task.created_at = created_at
    task.completed_at = completed_at
    task.board_id = "board_1"
    return task


def _make_board(board_id: str = "board_1", name: str = "Test Board") -> MagicMock:
    board = MagicMock()
    board.board_id = board_id
    board.name = name
    return board


def _make_summary(
    board_name: str = "Test Board",
    total: int = 5,
    task_counts: dict[str, int] | None = None,
    by_agent: dict[str | None, dict[str, int]] | None = None,
    dispatcher_active: bool = True,
) -> MagicMock:
    summary = MagicMock()
    summary.board = _make_board(name=board_name)
    summary.total_tasks = total
    summary.task_counts = task_counts or {"ready": 3, "running": 2}
    summary.by_agent = by_agent or {}
    summary.dispatcher_active = dispatcher_active
    return summary


class TestChannelKanbanCommandHandler:
    """Tests for ChannelKanbanCommandHandler — all 10 subcommands + edge cases."""

    @pytest.fixture
    def handler(self) -> object:
        from app.core.channel_bridge.kanban_command_handler import ChannelKanbanCommandHandler

        return ChannelKanbanCommandHandler()

    @pytest.fixture
    def msg(self) -> InboundMessage:
        return _make_msg(user_id="u_test", sender_id="sender_1", chat_id="chat_1")

    @pytest.fixture
    def svc(self) -> MagicMock:
        return _mock_svc()

    # ── unknown subcommand → usage ──

    @pytest.mark.asyncio
    async def test_unknown_subcommand_returns_usage(self, handler: object, msg: InboundMessage) -> None:
        result = await handler.handle_kanban(msg, "foobar")  # type: ignore[union-attr]
        assert "/kanban list" in result
        assert "/kanban show" in result

    # ── list ──

    @pytest.mark.asyncio
    async def test_list_no_boards(self, handler: object, msg: InboundMessage, svc: MagicMock) -> None:
        svc.list_boards = AsyncMock(return_value=[])
        with patch("app.services.kanban.KanbanService.get_instance", return_value=svc):
            result = await handler.handle_kanban(msg, "list")  # type: ignore[union-attr]
            assert "No kanban boards" in result

    @pytest.mark.asyncio
    async def test_list_with_tasks(self, handler: object, msg: InboundMessage, svc: MagicMock) -> None:
        tasks = [
            _make_task("t_1", "Task One", "ready"),
            _make_task("t_2", "Task Two", "running"),
        ]
        svc.list_boards = AsyncMock(return_value=[_make_board()])
        svc.list_tasks = AsyncMock(return_value=tasks)
        with patch("app.services.kanban.KanbanService.get_instance", return_value=svc):
            result = await handler.handle_kanban(msg, "list")  # type: ignore[union-attr]
            assert "t_1" in result
            assert "Task One" in result
            assert "t_2" in result

    @pytest.mark.asyncio
    async def test_list_filters_archived(self, handler: object, msg: InboundMessage, svc: MagicMock) -> None:
        tasks = [
            _make_task("t_1", "Active", "ready"),
            _make_task("t_2", "Archived", "archived"),
        ]
        svc.list_boards = AsyncMock(return_value=[_make_board()])
        svc.list_tasks = AsyncMock(return_value=tasks)
        with patch("app.services.kanban.KanbanService.get_instance", return_value=svc):
            result = await handler.handle_kanban(msg, "list")  # type: ignore[union-attr]
            assert "Active" in result
            assert "Archived" not in result

    @pytest.mark.asyncio
    async def test_list_explicit_board_id(self, handler: object, msg: InboundMessage, svc: MagicMock) -> None:
        tasks = [_make_task("t_1", "Explicit Board Task", "running")]
        svc.list_tasks = AsyncMock(return_value=tasks)
        with patch("app.services.kanban.KanbanService.get_instance", return_value=svc):
            result = await handler.handle_kanban(msg, "list custom_board")  # type: ignore[union-attr]
            svc.list_tasks.assert_called_once_with("custom_board", limit=50)
            assert "t_1" in result

    # ── ls alias ──

    @pytest.mark.asyncio
    async def test_ls_alias(self, handler: object, msg: InboundMessage, svc: MagicMock) -> None:
        svc.list_boards = AsyncMock(return_value=[_make_board()])
        svc.list_tasks = AsyncMock(return_value=[])
        with patch("app.services.kanban.KanbanService.get_instance", return_value=svc):
            result = await handler.handle_kanban(msg, "ls")  # type: ignore[union-attr]
            assert "No active tasks" in result

    # ── show ──

    @pytest.mark.asyncio
    async def test_show_no_task_id(self, handler: object, msg: InboundMessage) -> None:
        result = await handler.handle_kanban(msg, "show")  # type: ignore[union-attr]
        assert "Usage" in result

    @pytest.mark.asyncio
    async def test_show_not_found(self, handler: object, msg: InboundMessage, svc: MagicMock) -> None:
        svc.get_task = AsyncMock(return_value=None)
        with patch("app.services.kanban.KanbanService.get_instance", return_value=svc):
            result = await handler.handle_kanban(msg, "show t_none")  # type: ignore[union-attr]
            assert "not found" in result

    @pytest.mark.asyncio
    async def test_show_success(self, handler: object, msg: InboundMessage, svc: MagicMock) -> None:
        task = _make_task(
            "t_abc",
            "Important Task",
            "running",
            "high",
            description="A detailed description",
            agent_id="agent_1",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        svc.get_task = AsyncMock(return_value=task)
        with patch("app.services.kanban.KanbanService.get_instance", return_value=svc):
            result = await handler.handle_kanban(msg, "show t_abc")  # type: ignore[union-attr]
            assert "Important Task" in result
            assert "t_abc" in result
            assert "running" in result
            assert "high" in result
            assert "A detailed description" in result
            assert "agent_1" in result

    # ── create ──

    @pytest.mark.asyncio
    async def test_create_no_title(self, handler: object, msg: InboundMessage) -> None:
        result = await handler.handle_kanban(msg, "create")  # type: ignore[union-attr]
        assert "Usage" in result

    @pytest.mark.asyncio
    async def test_create_success(self, handler: object, msg: InboundMessage, svc: MagicMock) -> None:
        new_task = _make_task("t_new", "My New Task")
        svc.list_boards = AsyncMock(return_value=[_make_board()])
        svc.add_task = AsyncMock(return_value=new_task)
        with patch("app.services.kanban.KanbanService.get_instance", return_value=svc):
            result = await handler.handle_kanban(msg, "create My New Task")  # type: ignore[union-attr]
            assert "t_new" in result
            assert "My New Task" in result

    @pytest.mark.asyncio
    async def test_create_auto_creates_board(self, handler: object, msg: InboundMessage, svc: MagicMock) -> None:
        new_task = _make_task("t_new2", "Auto Board Task")
        new_board = _make_board("board_auto", "Default Board")
        svc.list_boards = AsyncMock(return_value=[])
        svc.create_board = AsyncMock(return_value=new_board)
        svc.add_task = AsyncMock(return_value=new_task)
        with patch("app.services.kanban.KanbanService.get_instance", return_value=svc):
            result = await handler.handle_kanban(msg, "create Auto Board Task")  # type: ignore[union-attr]
            svc.create_board.assert_called_once_with(name="Default Board")
            assert "t_new2" in result

    # ── add alias ──

    @pytest.mark.asyncio
    async def test_add_alias(self, handler: object, msg: InboundMessage, svc: MagicMock) -> None:
        new_task = _make_task("t_add", "Alias Task")
        svc.list_boards = AsyncMock(return_value=[_make_board()])
        svc.add_task = AsyncMock(return_value=new_task)
        with patch("app.services.kanban.KanbanService.get_instance", return_value=svc):
            result = await handler.handle_kanban(msg, "add Alias Task")  # type: ignore[union-attr]
            assert "t_add" in result

    # ── comment ──

    @pytest.mark.asyncio
    async def test_comment_missing_args(self, handler: object, msg: InboundMessage) -> None:
        result = await handler.handle_kanban(msg, "comment t_abc")  # type: ignore[union-attr]
        assert "Usage" in result

    @pytest.mark.asyncio
    async def test_comment_task_not_found(self, handler: object, msg: InboundMessage, svc: MagicMock) -> None:
        svc.get_task = AsyncMock(return_value=None)
        with patch("app.services.kanban.KanbanService.get_instance", return_value=svc):
            result = await handler.handle_kanban(msg, "comment t_none hello")  # type: ignore[union-attr]
            assert "not found" in result

    @pytest.mark.asyncio
    async def test_comment_success(self, handler: object, msg: InboundMessage, svc: MagicMock) -> None:
        task = _make_task("t_abc")
        svc.get_task = AsyncMock(return_value=task)
        svc.add_comment = AsyncMock()
        with patch("app.services.kanban.KanbanService.get_instance", return_value=svc):
            result = await handler.handle_kanban(msg, "comment t_abc This is a comment")  # type: ignore[union-attr]
            assert "Comment added" in result
            svc.add_comment.assert_called_once_with("t_abc", "This is a comment", author="u_test")

    @pytest.mark.asyncio
    async def test_comment_uses_sender_id_fallback(self, handler: object, svc: MagicMock) -> None:
        msg_no_user = _make_msg(sender_id="fallback_sender")
        task = _make_task("t_abc")
        svc.get_task = AsyncMock(return_value=task)
        svc.add_comment = AsyncMock()
        with patch("app.services.kanban.KanbanService.get_instance", return_value=svc):
            await handler.handle_kanban(msg_no_user, "comment t_abc msg")  # type: ignore[union-attr]
            svc.add_comment.assert_called_once_with("t_abc", "msg", author="fallback_sender")

    # ── edit ──

    @pytest.mark.asyncio
    async def test_edit_missing_args(self, handler: object, msg: InboundMessage) -> None:
        result = await handler.handle_kanban(msg, "edit t_abc title")  # type: ignore[union-attr]
        assert "Usage" in result

    @pytest.mark.asyncio
    async def test_edit_title_success(self, handler: object, msg: InboundMessage, svc: MagicMock) -> None:
        svc.update_task = AsyncMock(return_value=True)
        with patch("app.services.kanban.KanbanService.get_instance", return_value=svc):
            result = await handler.handle_kanban(msg, "edit t_abc title New Title")  # type: ignore[union-attr]
            assert "updated" in result
            svc.update_task.assert_called_once_with("t_abc", title="New Title")

    @pytest.mark.asyncio
    async def test_edit_desc_success(self, handler: object, msg: InboundMessage, svc: MagicMock) -> None:
        svc.update_task = AsyncMock(return_value=True)
        with patch("app.services.kanban.KanbanService.get_instance", return_value=svc):
            result = await handler.handle_kanban(msg, "edit t_abc desc A new description")  # type: ignore[union-attr]
            svc.update_task.assert_called_once_with("t_abc", description="A new description")
            assert "updated" in result

    @pytest.mark.asyncio
    async def test_edit_unknown_field(self, handler: object, msg: InboundMessage) -> None:
        result = await handler.handle_kanban(msg, "edit t_abc priority high")  # type: ignore[union-attr]
        assert "Unknown field" in result

    @pytest.mark.asyncio
    async def test_edit_task_not_found(self, handler: object, msg: InboundMessage, svc: MagicMock) -> None:
        svc.update_task = AsyncMock(return_value=None)
        with patch("app.services.kanban.KanbanService.get_instance", return_value=svc):
            result = await handler.handle_kanban(msg, "edit t_abc title X")  # type: ignore[union-attr]
            assert "not found" in result

    # ── complete / done ──

    @pytest.mark.asyncio
    async def test_complete_no_id(self, handler: object, msg: InboundMessage) -> None:
        result = await handler.handle_kanban(msg, "complete")  # type: ignore[union-attr]
        assert "Usage" in result

    @pytest.mark.asyncio
    async def test_complete_success(self, handler: object, msg: InboundMessage, svc: MagicMock) -> None:
        svc.move_task = AsyncMock(return_value=True)
        with patch("app.services.kanban.KanbanService.get_instance", return_value=svc):
            result = await handler.handle_kanban(msg, "complete t_abc")  # type: ignore[union-attr]
            assert "completed" in result

    @pytest.mark.asyncio
    async def test_complete_not_found(self, handler: object, msg: InboundMessage, svc: MagicMock) -> None:
        svc.move_task = AsyncMock(return_value=None)
        with patch("app.services.kanban.KanbanService.get_instance", return_value=svc):
            result = await handler.handle_kanban(msg, "complete t_none")  # type: ignore[union-attr]
            assert "not found" in result

    @pytest.mark.asyncio
    async def test_done_alias(self, handler: object, msg: InboundMessage, svc: MagicMock) -> None:
        svc.move_task = AsyncMock(return_value=True)
        with patch("app.services.kanban.KanbanService.get_instance", return_value=svc):
            result = await handler.handle_kanban(msg, "done t_abc")  # type: ignore[union-attr]
            assert "completed" in result

    # ── block ──

    @pytest.mark.asyncio
    async def test_block_no_id(self, handler: object, msg: InboundMessage) -> None:
        result = await handler.handle_kanban(msg, "block")  # type: ignore[union-attr]
        assert "Usage" in result

    @pytest.mark.asyncio
    async def test_block_with_reason(self, handler: object, msg: InboundMessage, svc: MagicMock) -> None:
        svc.move_task = AsyncMock(return_value=True)
        with patch("app.services.kanban.KanbanService.get_instance", return_value=svc):
            result = await handler.handle_kanban(msg, "block t_abc Waiting for review")  # type: ignore[union-attr]
            assert "blocked" in result
            assert "Waiting for review" in result

    @pytest.mark.asyncio
    async def test_block_default_reason(self, handler: object, msg: InboundMessage, svc: MagicMock) -> None:
        svc.move_task = AsyncMock(return_value=True)
        with patch("app.services.kanban.KanbanService.get_instance", return_value=svc):
            result = await handler.handle_kanban(msg, "block t_abc")  # type: ignore[union-attr]
            assert "blocked" in result

    @pytest.mark.asyncio
    async def test_block_not_found(self, handler: object, msg: InboundMessage, svc: MagicMock) -> None:
        svc.move_task = AsyncMock(return_value=None)
        with patch("app.services.kanban.KanbanService.get_instance", return_value=svc):
            result = await handler.handle_kanban(msg, "block t_none")  # type: ignore[union-attr]
            assert "not found" in result

    # ── unblock ──

    @pytest.mark.asyncio
    async def test_unblock_no_id(self, handler: object, msg: InboundMessage) -> None:
        result = await handler.handle_kanban(msg, "unblock")  # type: ignore[union-attr]
        assert "Usage" in result

    @pytest.mark.asyncio
    async def test_unblock_success(self, handler: object, msg: InboundMessage, svc: MagicMock) -> None:
        svc.move_task = AsyncMock(return_value=True)
        with patch("app.services.kanban.KanbanService.get_instance", return_value=svc):
            result = await handler.handle_kanban(msg, "unblock t_abc")  # type: ignore[union-attr]
            assert "unblocked" in result

    # ── archive ──

    @pytest.mark.asyncio
    async def test_archive_no_id(self, handler: object, msg: InboundMessage) -> None:
        result = await handler.handle_kanban(msg, "archive")  # type: ignore[union-attr]
        assert "Usage" in result

    @pytest.mark.asyncio
    async def test_archive_success(self, handler: object, msg: InboundMessage, svc: MagicMock) -> None:
        svc.move_task = AsyncMock(return_value=True)
        with patch("app.services.kanban.KanbanService.get_instance", return_value=svc):
            result = await handler.handle_kanban(msg, "archive t_abc")  # type: ignore[union-attr]
            assert "archived" in result

    @pytest.mark.asyncio
    async def test_archive_not_found(self, handler: object, msg: InboundMessage, svc: MagicMock) -> None:
        svc.move_task = AsyncMock(return_value=None)
        with patch("app.services.kanban.KanbanService.get_instance", return_value=svc):
            result = await handler.handle_kanban(msg, "archive t_none")  # type: ignore[union-attr]
            assert "not found" in result

    # ── stats ──

    @pytest.mark.asyncio
    async def test_stats_no_boards(self, handler: object, msg: InboundMessage, svc: MagicMock) -> None:
        svc.list_boards = AsyncMock(return_value=[])
        with patch("app.services.kanban.KanbanService.get_instance", return_value=svc):
            result = await handler.handle_kanban(msg, "stats")  # type: ignore[union-attr]
            assert "No kanban boards" in result

    @pytest.mark.asyncio
    async def test_stats_board_not_found(self, handler: object, msg: InboundMessage, svc: MagicMock) -> None:
        svc.board_summary = AsyncMock(return_value=None)
        with patch("app.services.kanban.KanbanService.get_instance", return_value=svc):
            result = await handler.handle_kanban(msg, "stats custom_board")  # type: ignore[union-attr]
            assert "not found" in result

    @pytest.mark.asyncio
    async def test_stats_success(self, handler: object, msg: InboundMessage, svc: MagicMock) -> None:
        summary = _make_summary(
            board_name="My Board",
            total=10,
            task_counts={"ready": 5, "running": 3, "completed": 2},
            dispatcher_active=True,
        )
        svc.list_boards = AsyncMock(return_value=[_make_board()])
        svc.board_summary = AsyncMock(return_value=summary)
        with patch("app.services.kanban.KanbanService.get_instance", return_value=svc):
            result = await handler.handle_kanban(msg, "stats")  # type: ignore[union-attr]
            assert "My Board" in result
            assert "10" in result
            assert "active" in result

    @pytest.mark.asyncio
    async def test_stats_with_agents(self, handler: object, msg: InboundMessage, svc: MagicMock) -> None:
        summary = _make_summary(
            by_agent={"agent_1": {"running": 2}},
        )
        svc.list_boards = AsyncMock(return_value=[_make_board()])
        svc.board_summary = AsyncMock(return_value=summary)
        with patch("app.services.kanban.KanbanService.get_instance", return_value=svc):
            result = await handler.handle_kanban(msg, "stats")  # type: ignore[union-attr]
            assert "agent_1" in result

    @pytest.mark.asyncio
    async def test_stats_dispatcher_stopped(self, handler: object, msg: InboundMessage, svc: MagicMock) -> None:
        summary = _make_summary(dispatcher_active=False)
        svc.list_boards = AsyncMock(return_value=[_make_board()])
        svc.board_summary = AsyncMock(return_value=summary)
        with patch("app.services.kanban.KanbanService.get_instance", return_value=svc):
            result = await handler.handle_kanban(msg, "stats")  # type: ignore[union-attr]
            assert "stopped" in result

    # ── edge cases ──

    @pytest.mark.asyncio
    async def test_case_insensitive_subcommand(self, handler: object, msg: InboundMessage) -> None:
        result = await handler.handle_kanban(msg, "LIST")  # type: ignore[union-attr]
        assert "/kanban list" not in result or "No kanban" in result or "Kanban Tasks" in result

    @pytest.mark.asyncio
    async def test_show_truncates_long_description(self, handler: object, msg: InboundMessage, svc: MagicMock) -> None:
        task = _make_task("t_long", "Long Desc Task", description="A" * 500)
        svc.get_task = AsyncMock(return_value=task)
        with patch("app.services.kanban.KanbanService.get_instance", return_value=svc):
            result = await handler.handle_kanban(msg, "show t_long")  # type: ignore[union-attr]
            assert "..." in result
            assert len([line for line in result.split("\n") if "Description" in line][0]) < 400

    @pytest.mark.asyncio
    async def test_show_task_with_error(self, handler: object, msg: InboundMessage, svc: MagicMock) -> None:
        task = _make_task("t_err", "Error Task", status="failed", error="OOM killed")
        svc.get_task = AsyncMock(return_value=task)
        with patch("app.services.kanban.KanbanService.get_instance", return_value=svc):
            result = await handler.handle_kanban(msg, "show t_err")  # type: ignore[union-attr]
            assert "OOM killed" in result

    @pytest.mark.asyncio
    async def test_show_completed_task_with_timestamps(self, handler: object, msg: InboundMessage, svc: MagicMock) -> None:
        task = _make_task(
            "t_done",
            "Done Task",
            status="completed",
            created_at=datetime(2026, 6, 1, tzinfo=UTC),
            completed_at=datetime(2026, 6, 2, tzinfo=UTC),
        )
        svc.get_task = AsyncMock(return_value=task)
        with patch("app.services.kanban.KanbanService.get_instance", return_value=svc):
            result = await handler.handle_kanban(msg, "show t_done")  # type: ignore[union-attr]
            assert "Created" in result
            assert "Completed" in result

    @pytest.mark.asyncio
    async def test_list_shows_priority_tag_for_non_normal(self, handler: object, msg: InboundMessage, svc: MagicMock) -> None:
        tasks = [
            _make_task("t_u", "Urgent Task", "ready", "urgent"),
            _make_task("t_n", "Normal Task", "ready", "normal"),
        ]
        svc.list_boards = AsyncMock(return_value=[_make_board()])
        svc.list_tasks = AsyncMock(return_value=tasks)
        with patch("app.services.kanban.KanbanService.get_instance", return_value=svc):
            result = await handler.handle_kanban(msg, "list")  # type: ignore[union-attr]
            assert "`urgent`" in result
            assert "`normal`" not in result

    @pytest.mark.asyncio
    async def test_edit_title_alias_t(self, handler: object, msg: InboundMessage, svc: MagicMock) -> None:
        svc.update_task = AsyncMock(return_value=True)
        with patch("app.services.kanban.KanbanService.get_instance", return_value=svc):
            result = await handler.handle_kanban(msg, "edit t_abc t Short Title")  # type: ignore[union-attr]
            assert "updated" in result
            svc.update_task.assert_called_once_with("t_abc", title="Short Title")

    @pytest.mark.asyncio
    async def test_edit_desc_alias_d(self, handler: object, msg: InboundMessage, svc: MagicMock) -> None:
        svc.update_task = AsyncMock(return_value=True)
        with patch("app.services.kanban.KanbanService.get_instance", return_value=svc):
            result = await handler.handle_kanban(msg, "edit t_abc d New desc")  # type: ignore[union-attr]
            assert "updated" in result
            svc.update_task.assert_called_once_with("t_abc", description="New desc")

    @pytest.mark.asyncio
    async def test_list_respects_limit_20(self, handler: object, msg: InboundMessage, svc: MagicMock) -> None:
        tasks = [_make_task(f"t_{i}", f"Task {i}", "ready") for i in range(30)]
        svc.list_boards = AsyncMock(return_value=[_make_board()])
        svc.list_tasks = AsyncMock(return_value=tasks)
        with patch("app.services.kanban.KanbanService.get_instance", return_value=svc):
            result = await handler.handle_kanban(msg, "list")  # type: ignore[union-attr]
            task_lines = [line for line in result.split("\n") if line.startswith(("📥", "📋", "🟢", "🔄", "✅", "❌", "🚫", "📦", "•"))]
            assert len(task_lines) <= 20

    @pytest.mark.asyncio
    async def test_comment_only_task_id_no_body(self, handler: object, msg: InboundMessage) -> None:
        result = await handler.handle_kanban(msg, "comment")  # type: ignore[union-attr]
        assert "Usage" in result


# ── _format_time tests ─────────────────────────────────────────────────


class TestFormatTime:
    def test_just_now(self) -> None:
        from app.core.channel_bridge.kanban_command_handler import _format_time

        result = _format_time(datetime.now(UTC))
        assert result == "just now"

    def test_minutes_ago(self) -> None:
        from datetime import timedelta

        from app.core.channel_bridge.kanban_command_handler import _format_time

        dt = datetime.now(UTC) - timedelta(minutes=5)
        result = _format_time(dt)
        assert "m ago" in result

    def test_hours_ago(self) -> None:
        from datetime import timedelta

        from app.core.channel_bridge.kanban_command_handler import _format_time

        dt = datetime.now(UTC) - timedelta(hours=3)
        result = _format_time(dt)
        assert "h ago" in result

    def test_old_date_absolute(self) -> None:
        from app.core.channel_bridge.kanban_command_handler import _format_time

        dt = datetime(2025, 1, 15, 10, 30, tzinfo=UTC)
        result = _format_time(dt)
        assert "2025-01-15" in result

    def test_naive_datetime_handled(self) -> None:
        from datetime import timedelta

        from app.core.channel_bridge.kanban_command_handler import _format_time

        dt = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=2)
        result = _format_time(dt)
        assert "m ago" in result


# ── _handle_kanban_command router mixin tests ──────────────────────────


class TestHandleKanbanCommand:
    """Tests for _handle_kanban_command in RouterCommandsMixin."""

    def _make_host(
        self,
        kanban_handler: KanbanCommandHandler | None = None,
    ) -> MagicMock:
        host = MagicMock()
        host._kanban_handler = kanban_handler
        host._bus = MagicMock()
        host._bus.publish_outbound = AsyncMock()
        return host

    @pytest.mark.asyncio
    async def test_no_handler_returns_not_available(self) -> None:
        from app.channels.routing.router_commands import RouterCommandsMixin

        host = self._make_host(kanban_handler=None)
        msg = _make_msg(chat_id="chat_1")
        await RouterCommandsMixin._handle_kanban_command(host, msg, "list")
        host._bus.publish_outbound.assert_called_once()
        reply = host._bus.publish_outbound.call_args[0][0]
        assert isinstance(reply, OutboundMessage)

    @pytest.mark.asyncio
    async def test_empty_args_returns_usage(self) -> None:
        from app.channels.routing.router_commands import RouterCommandsMixin

        mock_handler = AsyncMock()
        host = self._make_host(kanban_handler=mock_handler)
        msg = _make_msg(chat_id="chat_1")
        await RouterCommandsMixin._handle_kanban_command(host, msg, "")
        host._bus.publish_outbound.assert_called_once()
        mock_handler.handle_kanban.assert_not_called()

    @pytest.mark.asyncio
    async def test_whitespace_args_returns_usage(self) -> None:
        from app.channels.routing.router_commands import RouterCommandsMixin

        mock_handler = AsyncMock()
        host = self._make_host(kanban_handler=mock_handler)
        msg = _make_msg(chat_id="chat_1")
        await RouterCommandsMixin._handle_kanban_command(host, msg, "   ")
        host._bus.publish_outbound.assert_called_once()
        mock_handler.handle_kanban.assert_not_called()

    @pytest.mark.asyncio
    async def test_success_delegates_to_handler(self) -> None:
        from app.channels.routing.router_commands import RouterCommandsMixin

        mock_handler = AsyncMock()
        mock_handler.handle_kanban = AsyncMock(return_value="Task list...")
        host = self._make_host(kanban_handler=mock_handler)
        msg = _make_msg(chat_id="chat_1")
        await RouterCommandsMixin._handle_kanban_command(host, msg, "list")
        mock_handler.handle_kanban.assert_called_once_with(msg, "list")
        reply = host._bus.publish_outbound.call_args[0][0]
        assert reply.content == "Task list..."

    @pytest.mark.asyncio
    async def test_exception_returns_error_message(self) -> None:
        from app.channels.routing.router_commands import RouterCommandsMixin

        mock_handler = AsyncMock()
        mock_handler.handle_kanban = AsyncMock(side_effect=RuntimeError("DB down"))
        host = self._make_host(kanban_handler=mock_handler)
        msg = _make_msg(chat_id="chat_1")
        await RouterCommandsMixin._handle_kanban_command(host, msg, "list")
        host._bus.publish_outbound.assert_called_once()

    @pytest.mark.asyncio
    async def test_reply_uses_chat_id(self) -> None:
        from app.channels.routing.router_commands import RouterCommandsMixin

        mock_handler = AsyncMock()
        mock_handler.handle_kanban = AsyncMock(return_value="ok")
        host = self._make_host(kanban_handler=mock_handler)
        msg = _make_msg(chat_id="target_chat", sender_id="sender_1")
        await RouterCommandsMixin._handle_kanban_command(host, msg, "stats")
        reply = host._bus.publish_outbound.call_args[0][0]
        assert reply.recipient_id == "target_chat"

    @pytest.mark.asyncio
    async def test_reply_falls_back_to_sender_id(self) -> None:
        from app.channels.routing.router_commands import RouterCommandsMixin

        mock_handler = AsyncMock()
        mock_handler.handle_kanban = AsyncMock(return_value="ok")
        host = self._make_host(kanban_handler=mock_handler)
        msg = _make_msg(chat_id=None, sender_id="dm_user")
        await RouterCommandsMixin._handle_kanban_command(host, msg, "list")
        reply = host._bus.publish_outbound.call_args[0][0]
        assert reply.recipient_id == "dm_user"

    @pytest.mark.asyncio
    async def test_group_reply_includes_reply_to_id(self) -> None:
        from app.channels.routing.router_commands import RouterCommandsMixin

        mock_handler = AsyncMock()
        mock_handler.handle_kanban = AsyncMock(return_value="ok")
        host = self._make_host(kanban_handler=mock_handler)
        msg = _make_msg(
            chat_id="group_1",
            sender_id="user_1",
            is_group=True,
            message_id="msg_123",
        )
        await RouterCommandsMixin._handle_kanban_command(host, msg, "list")
        reply = host._bus.publish_outbound.call_args[0][0]
        assert reply.reply_to_id == "msg_123"
