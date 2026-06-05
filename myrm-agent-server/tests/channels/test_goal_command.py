"""Tests for /goal slash command — command_defs, protocol, subcommand parsing, dispatch."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.protocols.goal_command import (
    GoalCommandHandler,
    GoalSubcommand,
    SubgoalSubcommand,
)
from app.channels.routing.command_defs import (
    SYSTEM_COMMANDS,
    CommandAction,
)
from app.channels.routing.command_registry import (
    CommandRegistry,
)
from app.channels.types import InboundMessage, OutboundMessage


def _make_msg(content: str = "", channel: str = "test", sender: str = "user1") -> InboundMessage:
    return InboundMessage(channel=channel, sender_id=sender, content=content)


# ---- command_defs tests ----


class TestGoalCommandDef:
    """Tests for /goal CommandDef registration."""

    def test_goal_action_exists(self) -> None:
        assert hasattr(CommandAction, "GOAL")
        assert CommandAction.GOAL.value == "goal"

    def test_goal_in_system_commands(self) -> None:
        goal_cmds = [c for c in SYSTEM_COMMANDS if c.action == CommandAction.GOAL]
        assert len(goal_cmds) == 1

    def test_goal_command_properties(self) -> None:
        goal_cmd = next(c for c in SYSTEM_COMMANDS if c.action == CommandAction.GOAL)
        assert goal_cmd.name == "goal"
        assert goal_cmd.category == "Goals"
        assert goal_cmd.parse_args is True
        assert goal_cmd.args_pattern != ""

    def test_goal_registered_in_registry(self) -> None:
        registry = CommandRegistry()
        result = registry.resolve("/goal")
        assert result is not None
        assert result.command_def.action == CommandAction.GOAL


# ---- GoalSubcommand tests ----


class TestGoalSubcommand:
    """Tests for GoalSubcommand enum."""

    def test_all_subcommands_exist(self) -> None:
        assert len(GoalSubcommand) == 6
        for name in ("SET", "STATUS", "PAUSE", "RESUME", "CLEAR", "BUDGET"):
            assert hasattr(GoalSubcommand, name)

    def test_subcommand_values(self) -> None:
        assert GoalSubcommand.SET == "set"
        assert GoalSubcommand.STATUS == "status"
        assert GoalSubcommand.PAUSE == "pause"
        assert GoalSubcommand.RESUME == "resume"
        assert GoalSubcommand.CLEAR == "clear"
        assert GoalSubcommand.BUDGET == "budget"


# ---- GoalCommandHandler Protocol tests ----


class TestGoalCommandHandlerProtocol:
    """Tests for GoalCommandHandler protocol compliance."""

    def test_protocol_is_runtime_checkable(self) -> None:
        class MockHandler:
            async def handle_goal(self, msg: InboundMessage, subcommand: GoalSubcommand, args: str) -> str:
                return "ok"

            async def handle_subgoal(self, msg: InboundMessage, subcommand: SubgoalSubcommand, args: str) -> str:
                return "ok"

            async def get_kickoff_message(self, msg: InboundMessage, goal_text: str) -> InboundMessage | None:
                return None

        handler = MockHandler()
        assert isinstance(handler, GoalCommandHandler)

    def test_non_handler_fails_check(self) -> None:
        class NotAHandler:
            pass

        assert not isinstance(NotAHandler(), GoalCommandHandler)


# ---- Subcommand parsing tests (testing the parsing logic in router_commands) ----


class TestGoalSubcommandParsing:
    """Tests for the subcommand parsing logic in _handle_goal_command."""

    def _parse(self, raw_args: str) -> tuple[GoalSubcommand, str]:
        """Replicate the parsing logic from router_commands._handle_goal_command."""
        args = raw_args.strip()
        lower = args.lower()

        if not args or lower == "status":
            return GoalSubcommand.STATUS, ""
        if lower == "pause":
            return GoalSubcommand.PAUSE, ""
        if lower == "resume":
            return GoalSubcommand.RESUME, ""
        if lower in {"clear", "stop", "done"}:
            return GoalSubcommand.CLEAR, ""
        if lower == "budget" or lower.startswith("budget "):
            return GoalSubcommand.BUDGET, args[6:].strip()
        return GoalSubcommand.SET, args

    def test_empty_args_is_status(self) -> None:
        sub, args = self._parse("")
        assert sub == GoalSubcommand.STATUS
        assert args == ""

    def test_explicit_status(self) -> None:
        sub, args = self._parse("status")
        assert sub == GoalSubcommand.STATUS

    def test_pause(self) -> None:
        sub, args = self._parse("pause")
        assert sub == GoalSubcommand.PAUSE

    def test_resume(self) -> None:
        sub, args = self._parse("resume")
        assert sub == GoalSubcommand.RESUME

    def test_clear(self) -> None:
        sub, args = self._parse("clear")
        assert sub == GoalSubcommand.CLEAR

    def test_stop_alias_maps_to_clear(self) -> None:
        sub, args = self._parse("stop")
        assert sub == GoalSubcommand.CLEAR

    def test_done_alias_maps_to_clear(self) -> None:
        sub, args = self._parse("done")
        assert sub == GoalSubcommand.CLEAR

    def test_budget_no_value(self) -> None:
        sub, args = self._parse("budget")
        assert sub == GoalSubcommand.BUDGET
        assert args == ""

    def test_budget_with_value(self) -> None:
        sub, args = self._parse("budget 10")
        assert sub == GoalSubcommand.BUDGET
        assert args == "10"

    def test_budget_boundary_no_false_match(self) -> None:
        """budgetfix should be parsed as SET, not BUDGET."""
        sub, args = self._parse("budgetfix my server")
        assert sub == GoalSubcommand.SET
        assert args == "budgetfix my server"

    def test_set_goal_text(self) -> None:
        sub, args = self._parse("Organize project documentation")
        assert sub == GoalSubcommand.SET
        assert args == "Organize project documentation"

    def test_set_preserves_original_case(self) -> None:
        sub, args = self._parse("Fix Bug #123 in AuthModule")
        assert sub == GoalSubcommand.SET
        assert args == "Fix Bug #123 in AuthModule"

    def test_whitespace_trimmed(self) -> None:
        sub, args = self._parse("  pause  ")
        assert sub == GoalSubcommand.PAUSE


# ---- _handle_goal_command integration tests ----


class TestHandleGoalCommand:
    """Tests for _handle_goal_command mixin method."""

    def _make_host(
        self,
        goal_handler: GoalCommandHandler | None = None,
        has_active_task: bool = False,
    ) -> MagicMock:
        host = MagicMock()
        host._goal_handler = goal_handler
        host._bus = MagicMock()
        host._bus.publish_outbound = AsyncMock()
        host._gate = MagicMock()
        host._gate.submit = MagicMock()
        host._active_tasks = {"test:user1": MagicMock()} if has_active_task else {}
        return host

    @pytest.mark.asyncio
    async def test_no_handler_returns_not_available_zh(self) -> None:
        from app.channels.routing.router_commands import (
            RouterCommandsMixin,
        )

        host = self._make_host(goal_handler=None)
        msg = InboundMessage(
            channel="test",
            sender_id="user1",
            content="/goal",
            metadata={"locale": "zh-CN"},
        )
        await RouterCommandsMixin._handle_goal_command(host, msg, "test goal")

        host._bus.publish_outbound.assert_called_once()
        reply: OutboundMessage = host._bus.publish_outbound.call_args[0][0]
        assert "目标管理" in reply.content or "不可用" in reply.content

    @pytest.mark.asyncio
    async def test_status_publishes_handler_response_zh(self) -> None:
        from app.channels.routing.router_commands import (
            RouterCommandsMixin,
        )

        handler = MagicMock()
        handler.handle_goal = AsyncMock(return_value="**目标：** 整理文档\n**状态：** 运行中")
        host = self._make_host(goal_handler=handler)
        msg = InboundMessage(
            channel="feishu",
            sender_id="user1",
            content="/goal status",
            metadata={"locale": "zh-CN"},
        )
        await RouterCommandsMixin._handle_goal_command(host, msg, "status")

        handler.handle_goal.assert_called_once()
        host._bus.publish_outbound.assert_called_once()
        reply: OutboundMessage = host._bus.publish_outbound.call_args[0][0]
        assert "目标" in reply.content

    @pytest.mark.asyncio
    async def test_no_handler_returns_not_available(self) -> None:
        from app.channels.routing.router_commands import (
            RouterCommandsMixin,
        )

        host = self._make_host(goal_handler=None)
        msg = _make_msg()
        await RouterCommandsMixin._handle_goal_command(host, msg, "test goal")

        host._bus.publish_outbound.assert_called_once()
        reply: OutboundMessage = host._bus.publish_outbound.call_args[0][0]
        assert "not available" in reply.content.lower()

    @pytest.mark.asyncio
    async def test_set_during_active_task_blocked(self) -> None:
        from app.channels.routing.router_commands import (
            RouterCommandsMixin,
        )

        handler = MagicMock()
        handler.handle_goal = AsyncMock(return_value="ok")
        host = self._make_host(goal_handler=handler, has_active_task=True)
        msg = _make_msg()
        await RouterCommandsMixin._handle_goal_command(host, msg, "new goal text")

        handler.handle_goal.assert_not_called()
        host._bus.publish_outbound.assert_called_once()
        reply: OutboundMessage = host._bus.publish_outbound.call_args[0][0]
        assert "running" in reply.content.lower()

    @pytest.mark.asyncio
    async def test_status_during_active_task_allowed(self) -> None:
        from app.channels.routing.router_commands import (
            RouterCommandsMixin,
        )

        handler = MagicMock()
        handler.handle_goal = AsyncMock(return_value="Goal: test\nStatus: Active")
        host = self._make_host(goal_handler=handler, has_active_task=True)
        msg = _make_msg()
        await RouterCommandsMixin._handle_goal_command(host, msg, "status")

        handler.handle_goal.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_triggers_kickoff(self) -> None:
        from app.channels.routing.router_commands import (
            RouterCommandsMixin,
        )

        kickoff_msg = _make_msg("goal text")
        handler = MagicMock()
        handler.handle_goal = AsyncMock(return_value="Goal set")
        handler.get_kickoff_message = AsyncMock(return_value=kickoff_msg)
        host = self._make_host(goal_handler=handler)
        msg = _make_msg()
        await RouterCommandsMixin._handle_goal_command(host, msg, "goal text")

        handler.get_kickoff_message.assert_called_once()
        host._gate.submit.assert_called_once_with(kickoff_msg)

    @pytest.mark.asyncio
    async def test_set_no_kickoff_when_none(self) -> None:
        from app.channels.routing.router_commands import (
            RouterCommandsMixin,
        )

        handler = MagicMock()
        handler.handle_goal = AsyncMock(return_value="Goal set")
        handler.get_kickoff_message = AsyncMock(return_value=None)
        host = self._make_host(goal_handler=handler)
        msg = _make_msg()
        await RouterCommandsMixin._handle_goal_command(host, msg, "goal text")

        host._gate.submit.assert_not_called()

    @pytest.mark.asyncio
    async def test_pause_does_not_trigger_kickoff(self) -> None:
        from app.channels.routing.router_commands import (
            RouterCommandsMixin,
        )

        handler = MagicMock()
        handler.handle_goal = AsyncMock(return_value="Goal paused")
        host = self._make_host(goal_handler=handler)
        msg = _make_msg()
        await RouterCommandsMixin._handle_goal_command(host, msg, "pause")

        handler.handle_goal.assert_called_once()
        host._gate.submit.assert_not_called()


# ---- dispatch_system_command GOAL case ----


class TestDispatchGoalCommand:
    """Tests for GOAL action in _dispatch_system_command."""

    def test_goal_command_resolves(self) -> None:
        registry = CommandRegistry()
        result = registry.resolve("/goal")
        assert result is not None
        assert result.command_def.action == CommandAction.GOAL

    def test_goal_with_args_resolves(self) -> None:
        registry = CommandRegistry()
        result = registry.resolve("/goal organize docs")
        assert result is not None
        assert result.command_def.action == CommandAction.GOAL
        assert result.raw_args == "organize docs"

    def test_goal_status_resolves(self) -> None:
        registry = CommandRegistry()
        result = registry.resolve("/goal status")
        assert result is not None
        assert result.raw_args == "status"

    def test_goal_pause_resolves(self) -> None:
        registry = CommandRegistry()
        result = registry.resolve("/goal pause")
        assert result is not None
        assert result.raw_args == "pause"

    def test_goal_budget_resolves(self) -> None:
        registry = CommandRegistry()
        result = registry.resolve("/goal budget 10")
        assert result is not None
        assert result.raw_args == "budget 10"


# ---- Edge cases and robustness tests ----


class TestGoalEdgeCases:
    """Tests for edge cases and robustness."""

    @pytest.mark.asyncio
    async def test_goal_subcommand_case_insensitive(self) -> None:
        """Subcommand parsing should be case-insensitive."""
        from app.channels.routing.router_commands import (
            RouterCommandsMixin,
        )

        handler = MagicMock()
        handler.handle_goal = AsyncMock(return_value="ok")

        host = MagicMock()
        host._goal_handler = handler
        host._bus = MagicMock()
        host._bus.publish_outbound = AsyncMock()
        host._gate = MagicMock()
        host._active_tasks = {}

        msg = _make_msg()
        await RouterCommandsMixin._handle_goal_command(host, msg, "PAUSE")
        call_args = handler.handle_goal.call_args
        assert call_args[0][1] == GoalSubcommand.PAUSE

    @pytest.mark.asyncio
    async def test_goal_reply_includes_correct_channel_info(self) -> None:
        """Reply should go to correct channel and recipient."""
        from app.channels.routing.router_commands import (
            RouterCommandsMixin,
        )

        handler = MagicMock()
        handler.handle_goal = AsyncMock(return_value="Goal paused")

        host = MagicMock()
        host._goal_handler = handler
        host._bus = MagicMock()
        host._bus.publish_outbound = AsyncMock()
        host._gate = MagicMock()
        host._active_tasks = {}

        msg = _make_msg(channel="telegram", sender="user42")
        await RouterCommandsMixin._handle_goal_command(host, msg, "pause")

        reply: OutboundMessage = host._bus.publish_outbound.call_args[0][0]
        assert reply.channel == "telegram"
        assert reply.recipient_id == "user42"

    @pytest.mark.asyncio
    async def test_goal_clear_aliases(self) -> None:
        """clear, stop, and done should all map to CLEAR."""
        from app.channels.routing.router_commands import (
            RouterCommandsMixin,
        )

        for alias in ("clear", "stop", "done"):
            handler = MagicMock()
            handler.handle_goal = AsyncMock(return_value="ok")

            host = MagicMock()
            host._goal_handler = handler
            host._bus = MagicMock()
            host._bus.publish_outbound = AsyncMock()
            host._gate = MagicMock()
            host._active_tasks = {}

            msg = _make_msg()
            await RouterCommandsMixin._handle_goal_command(host, msg, alias)
            call_args = handler.handle_goal.call_args
            assert call_args[0][1] == GoalSubcommand.CLEAR, f"'{alias}' should map to CLEAR"

    @pytest.mark.asyncio
    async def test_mid_run_allows_safe_commands(self) -> None:
        """pause, clear, status, budget should work during active task."""
        from app.channels.routing.router_commands import (
            RouterCommandsMixin,
        )

        for cmd in ("status", "pause", "clear", "budget 5"):
            handler = MagicMock()
            handler.handle_goal = AsyncMock(return_value="ok")

            host = MagicMock()
            host._goal_handler = handler
            host._bus = MagicMock()
            host._bus.publish_outbound = AsyncMock()
            host._gate = MagicMock()
            host._active_tasks = {"test:user1": MagicMock()}

            msg = _make_msg()
            await RouterCommandsMixin._handle_goal_command(host, msg, cmd)
            handler.handle_goal.assert_called_once()

    @pytest.mark.asyncio
    async def test_mid_run_blocks_resume(self) -> None:
        """resume is parsed as SET (not a known subcommand when active task), but resume IS known."""
        from app.channels.routing.router_commands import (
            RouterCommandsMixin,
        )

        handler = MagicMock()
        handler.handle_goal = AsyncMock(return_value="ok")

        host = MagicMock()
        host._goal_handler = handler
        host._bus = MagicMock()
        host._bus.publish_outbound = AsyncMock()
        host._gate = MagicMock()
        host._active_tasks = {"test:user1": MagicMock()}

        msg = _make_msg()
        await RouterCommandsMixin._handle_goal_command(host, msg, "resume")
        # resume is a known subcommand (not SET), so it should be allowed
        handler.handle_goal.assert_called_once()

    @pytest.mark.asyncio
    async def test_group_message_goal(self) -> None:
        """Goal command should work in group chats using chat_id."""
        from app.channels.routing.router_commands import (
            RouterCommandsMixin,
        )

        handler = MagicMock()
        handler.handle_goal = AsyncMock(return_value="Goal set")
        handler.get_kickoff_message = AsyncMock(return_value=None)

        host = MagicMock()
        host._goal_handler = handler
        host._bus = MagicMock()
        host._bus.publish_outbound = AsyncMock()
        host._gate = MagicMock()
        host._active_tasks = {}

        msg = InboundMessage(
            channel="telegram",
            sender_id="user1",
            content="",
            chat_id="group123",
            is_group=True,
        )
        await RouterCommandsMixin._handle_goal_command(host, msg, "test goal")

        reply: OutboundMessage = host._bus.publish_outbound.call_args[0][0]
        assert reply.recipient_id == "group123"
