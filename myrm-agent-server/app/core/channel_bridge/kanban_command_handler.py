"""ChannelKanbanCommandHandler — business-layer handler for /kanban slash commands.

Implements the KanbanCommandHandler protocol, dispatching subcommands
(list, show, create, comment, edit, complete, block, unblock, archive, stats)
to the KanbanService singleton and formatting results as Markdown.

[INPUT]
- app.channels.types::InboundMessage (POS: Channel message types)
- app.channels.protocols.kanban_command (POS: Kanban command handler protocol)
- app.services.kanban::KanbanService (POS: Kanban business service)

[OUTPUT]
- ChannelKanbanCommandHandler: KanbanCommandHandler protocol implementation

[POS]
Business-layer adapter connecting /kanban (/kb) slash commands to the
KanbanService. Each subcommand maps to a KanbanService API call; results
are formatted as readable Markdown for IM display.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from app.channels.types import InboundMessage

_SubcommandFn = Callable[[InboundMessage, str], Awaitable[str]]

logger = logging.getLogger(__name__)

_STATUS_EMOJI: dict[str, str] = {
    "triage": "📥",
    "backlog": "📋",
    "ready": "🟢",
    "running": "🔄",
    "completed": "✅",
    "failed": "❌",
    "blocked": "🚫",
    "archived": "📦",
}


class ChannelKanbanCommandHandler:
    """KanbanCommandHandler protocol implementation backed by KanbanService."""

    def __init__(self) -> None:
        self._dispatch: dict[str, _SubcommandFn] = {
            "list": self._list,
            "ls": self._list,
            "show": self._show,
            "create": self._create,
            "add": self._create,
            "comment": self._comment,
            "edit": self._edit,
            "complete": self._complete,
            "done": self._complete,
            "block": self._block,
            "unblock": self._unblock,
            "archive": self._archive,
            "stats": self._stats,
        }

    async def handle_kanban(
        self,
        msg: InboundMessage,
        raw_args: str,
    ) -> str:
        parts = raw_args.strip().split(maxsplit=1)
        sub = parts[0].lower()
        rest = parts[1].strip() if len(parts) > 1 else ""

        handler = self._dispatch.get(sub)
        if handler is None:
            return self._usage()

        return await handler(msg, rest)

    def _usage(self) -> str:
        return (
            "**📋 /kanban usage:**\n"
            "`/kanban list [board_id]` — list tasks\n"
            "`/kanban show <task_id>` — task details\n"
            "`/kanban create <title>` — create task\n"
            "`/kanban comment <task_id> <message>` — add comment\n"
            "`/kanban edit <task_id> title|desc <text>` — edit task\n"
            "`/kanban complete <task_id>` — mark done\n"
            "`/kanban block <task_id> [reason]` — block task\n"
            "`/kanban unblock <task_id>` — unblock task\n"
            "`/kanban archive <task_id>` — archive task\n"
            "`/kanban stats [board_id]` — board statistics"
        )

    async def _get_default_board_id(self) -> str | None:
        from app.services.kanban import KanbanService

        svc = KanbanService.get_instance()
        boards = await svc.list_boards()
        if not boards:
            return None
        return boards[0].board_id

    async def _list(self, msg: InboundMessage, rest: str) -> str:
        from myrm_agent_harness.toolkits.kanban.types import TaskStatus

        from app.services.kanban import KanbanService

        svc = KanbanService.get_instance()
        board_id = rest.strip() if rest.strip() else await self._get_default_board_id()
        if not board_id:
            return "No kanban boards exist yet. Create a task first with `/kanban create <title>`."

        all_tasks = await svc.list_tasks(board_id, limit=50)
        tasks = [t for t in all_tasks if t.status != TaskStatus.ARCHIVED][:20]
        if not tasks:
            return "📋 No active tasks on this board."

        lines: list[str] = ["**📋 Kanban Tasks:**\n"]
        for t in tasks:
            emoji = _STATUS_EMOJI.get(t.status, "•")
            priority_tag = f" `{t.priority}`" if t.priority and t.priority != "normal" else ""
            lines.append(f"{emoji} `{t.task_id}` {t.title}{priority_tag} — *{t.status}*")

        return "\n".join(lines)

    async def _show(self, msg: InboundMessage, rest: str) -> str:
        from app.services.kanban import KanbanService

        task_id = rest.strip()
        if not task_id:
            return "Usage: `/kanban show <task_id>`"

        svc = KanbanService.get_instance()
        task = await svc.get_task(task_id)
        if not task:
            return f"Task `{task_id}` not found."

        emoji = _STATUS_EMOJI.get(task.status, "•")
        lines = [
            f"**{emoji} Task: {task.title}**\n",
            f"**ID:** `{task.task_id}`",
            f"**Status:** {task.status}",
            f"**Priority:** {task.priority}",
        ]

        if task.description:
            desc = task.description[:300]
            if len(task.description) > 300:
                desc += "..."
            lines.append(f"**Description:** {desc}")

        if task.agent_id:
            lines.append(f"**Agent:** {task.agent_id}")

        if task.error:
            lines.append(f"**Error:** {task.error}")

        if task.created_at:
            lines.append(f"**Created:** {_format_time(task.created_at)}")

        if task.completed_at:
            lines.append(f"**Completed:** {_format_time(task.completed_at)}")

        return "\n".join(lines)

    async def _create(self, msg: InboundMessage, rest: str) -> str:
        from myrm_agent_harness.toolkits.kanban.types import TaskPriority

        from app.services.kanban import KanbanService

        title = rest.strip()
        if not title:
            return "Usage: `/kanban create <title>`"

        svc = KanbanService.get_instance()
        board_id = await self._get_default_board_id()
        if not board_id:
            board = await svc.create_board(name="Default Board")
            board_id = board.board_id

        task = await svc.add_task(
            board_id=board_id,
            title=title,
            priority=TaskPriority.NORMAL,
        )

        return f"✅ Task created: `{task.task_id}` — {task.title}"

    async def _comment(self, msg: InboundMessage, rest: str) -> str:
        from app.services.kanban import KanbanService

        parts = rest.strip().split(maxsplit=1)
        if len(parts) < 2:
            return "Usage: `/kanban comment <task_id> <message>`"

        task_id, body = parts[0], parts[1]
        svc = KanbanService.get_instance()
        task = await svc.get_task(task_id)
        if not task:
            return f"Task `{task_id}` not found."

        author = msg.user_id or msg.sender_id or "user"
        await svc.add_comment(task_id, body, author=author)
        return f"💬 Comment added to `{task_id}`."

    async def _edit(self, msg: InboundMessage, rest: str) -> str:
        from app.services.kanban import KanbanService

        parts = rest.strip().split(maxsplit=2)
        if len(parts) < 3:
            return "Usage: `/kanban edit <task_id> title|desc <text>`"

        task_id, field_name, value = parts[0], parts[1].lower(), parts[2]
        svc = KanbanService.get_instance()

        if field_name in ("title", "t"):
            result = await svc.update_task(task_id, title=value)
        elif field_name in ("desc", "description", "d"):
            result = await svc.update_task(task_id, description=value)
        else:
            return f"Unknown field `{field_name}`. Use `title` or `desc`."

        if not result:
            return f"Task `{task_id}` not found."

        return f"✏️ Task `{task_id}` updated."

    async def _complete(self, msg: InboundMessage, rest: str) -> str:
        from myrm_agent_harness.toolkits.kanban.types import TaskStatus

        from app.services.kanban import KanbanService

        task_id = rest.strip()
        if not task_id:
            return "Usage: `/kanban complete <task_id>`"

        svc = KanbanService.get_instance()
        result = await svc.move_task(task_id, TaskStatus.COMPLETED, force=True)
        if not result:
            return f"Task `{task_id}` not found."

        return f"✅ Task `{task_id}` marked as completed."

    async def _block(self, msg: InboundMessage, rest: str) -> str:
        from myrm_agent_harness.toolkits.kanban.types import BlockKind, TaskStatus

        from app.services.kanban import KanbanService

        parts = rest.strip().split(maxsplit=1)
        if not parts or not parts[0]:
            return "Usage: `/kanban block <task_id> [reason]`"

        task_id = parts[0]
        reason = parts[1] if len(parts) > 1 else "Blocked via /kanban"

        svc = KanbanService.get_instance()
        result = await svc.move_task(
            task_id,
            TaskStatus.BLOCKED,
            block_kind=BlockKind.HUMAN,
            blocked_reason=reason,
        )
        if not result:
            return f"Task `{task_id}` not found."

        return f"🚫 Task `{task_id}` blocked: {reason}"

    async def _unblock(self, msg: InboundMessage, rest: str) -> str:
        from myrm_agent_harness.toolkits.kanban.types import TaskStatus

        from app.services.kanban import KanbanService

        task_id = rest.strip()
        if not task_id:
            return "Usage: `/kanban unblock <task_id>`"

        svc = KanbanService.get_instance()
        result = await svc.move_task(task_id, TaskStatus.READY)
        if not result:
            return f"Task `{task_id}` not found."

        return f"🟢 Task `{task_id}` unblocked and moved to READY."

    async def _archive(self, msg: InboundMessage, rest: str) -> str:
        from myrm_agent_harness.toolkits.kanban.types import TaskStatus

        from app.services.kanban import KanbanService

        task_id = rest.strip()
        if not task_id:
            return "Usage: `/kanban archive <task_id>`"

        svc = KanbanService.get_instance()
        result = await svc.move_task(task_id, TaskStatus.ARCHIVED, force=True)
        if not result:
            return f"Task `{task_id}` not found."

        return f"📦 Task `{task_id}` archived."

    async def _stats(self, msg: InboundMessage, rest: str) -> str:
        from app.services.kanban import KanbanService

        svc = KanbanService.get_instance()
        board_id = rest.strip() if rest.strip() else await self._get_default_board_id()
        if not board_id:
            return "No kanban boards exist yet."

        summary = await svc.board_summary(board_id)
        if not summary:
            return f"Board `{board_id}` not found."

        lines = [
            f"**📊 Board: {summary.board.name}**\n",
            f"**Total tasks:** {summary.total_tasks}",
        ]

        if summary.task_counts:
            lines.append("**By status:**")
            for status, count in sorted(summary.task_counts.items()):
                emoji = _STATUS_EMOJI.get(status, "•")
                lines.append(f"  {emoji} {status}: {count}")

        if summary.by_agent:
            lines.append("**By agent:**")
            for agent_id, count in sorted(summary.by_agent.items()):
                lines.append(f"  🤖 {agent_id}: {count}")

        dispatcher_label = "✅ active" if summary.dispatcher_active else "⏸ stopped"
        lines.append(f"**Dispatcher:** {dispatcher_label}")

        return "\n".join(lines)


def _format_time(dt: datetime) -> str:
    """Format a datetime as a readable relative/absolute string."""
    now = datetime.now(UTC)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    delta = now - dt
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    return dt.strftime("%Y-%m-%d %H:%M")
