"""Progress middleware — inject the todo blueprint into the user's message when todos exist.

[INPUT]
- progress.schemas::TodoStore (POS: active todos)
- agent.middlewares._run_notices::frozen_for_run, run_scope (POS: Request-local notices that keep their place and their text for the whole run.)
- agent.middlewares._run_workspace::run_workspace (POS: the workspace of the current run)
- core.message_origin::last_user_authored_index, runtime_human_message (POS: Message-provenance primitives shared by the approval, security, memory-context and context-management layers.)
- core.message_tail::append_block_to_last_user_message (POS: Tail-of-turn injection primitive.)
- langchain.agents.middleware::ModelRequest, wrap_model_call (POS: LC middleware)

[OUTPUT]
- progress_middleware: Injects the non-persistent todo focus into the user's latest message, the same text on every request of a run

[POS]
Surfaces active todos to the model without polluting persistent message history. Which runs keep a todo list is
decided by the ``get_todos_fn`` the host passes (it returns None for a run that cannot update one).
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Sequence

from langchain.agents.middleware import AgentMiddleware, AgentState, ModelRequest, ModelResponse, wrap_model_call
from langchain_core.messages import AnyMessage

from myrm_agent_harness.agent.meta_tools.progress.schemas import TodoItem, TodoStatus, TodoStore
from myrm_agent_harness.agent.middlewares._run_notices import frozen_for_run, run_scope
from myrm_agent_harness.agent.middlewares._run_workspace import run_workspace
from myrm_agent_harness.core.message_origin import last_user_authored_index, runtime_human_message
from myrm_agent_harness.core.message_tail import append_block_to_last_user_message

# Run-context key of the focus the run rendered on its first request.
_FOCUS_KEY = "progress_focus_block"

_SNAPSHOT_NOTE = "(Snapshot from the start of this turn; todo_write results later in the conversation are newer.)"

_PROGRESS_BLOCK_PATTERN = re.compile(
    r"\n*\s*\[SYSTEM INSTRUCTION\]\s*\n## Task progress \(active todos\)[\s\S]*$",
    re.MULTILINE,
)


def _strip_previous_progress(content: str) -> str:
    """Remove any trailing progress injection block from previous turns."""
    return _PROGRESS_BLOCK_PATTERN.sub("", content).rstrip()


def _build_progress_injection(store: TodoStore, incomplete: list[TodoItem]) -> str:
    """Build compact and focus-preserving todo injection text."""
    lines: list[str] = [
        "[SYSTEM INSTRUCTION]",
        "## Task progress (active todos)",
        f"**Goal:** {store.goal or 'Multi-step task'}",
        "",
    ]

    completed_count = sum(1 for item in store.todos if item.status == TodoStatus.COMPLETED)
    cancelled_count = sum(1 for item in store.todos if item.status == TodoStatus.CANCELLED)
    blocked_count = sum(1 for item in store.todos if item.status == TodoStatus.BLOCKED)

    # Determine focused item: prefer currently in_progress item, then first pending item,
    # skip blocked items when executable items exist.
    active_in_progress = next((item for item in incomplete if item.status == TodoStatus.IN_PROGRESS), None)
    active_pending = next((item for item in incomplete if item.status == TodoStatus.PENDING), None)
    focus_item = active_in_progress or active_pending or (incomplete[0] if incomplete else None)
    all_incomplete_blocked = bool(incomplete and all(item.status == TodoStatus.BLOCKED for item in incomplete))

    # If there are completed/cancelled items and list is long (> 4 items), summarize completed
    if len(store.todos) > 4 and (completed_count > 0 or cancelled_count > 0):
        summary_parts: list[str] = []
        if completed_count > 0:
            summary_parts.append(f"{completed_count} completed")
        if cancelled_count > 0:
            summary_parts.append(f"{cancelled_count} cancelled")
        lines.append(f"[✓] {', '.join(summary_parts)}")

        # Show incomplete items (up to 4 items)
        max_visible_incomplete = 4
        for item in incomplete[:max_visible_incomplete]:
            marker = ">" if focus_item and item.id == focus_item.id else "-"
            lines.append(f"{marker} [{item.status.value}] {item.id}: {item.content}")

        if len(incomplete) > max_visible_incomplete:
            remaining = len(incomplete) - max_visible_incomplete
            lines.append(f"... and {remaining} more pending task(s)")
    else:
        # Full list for short plans (<= 4 items)
        for item in store.todos:
            marker = ">" if focus_item and item.id == focus_item.id else "-"
            lines.append(f"{marker} [{item.status.value}] {item.id}: {item.content}")

    if focus_item:
        lines.extend(
            [
                "",
                f"Current focus: `{focus_item.id}` — {focus_item.content}",
                "Mark items completed with `todo_write(merge=true)` as you finish them.",
            ]
        )

    if all_incomplete_blocked:
        lines.append(
            "[ALL REMAINING TASKS BLOCKED] All uncompleted tasks are blocked by external dependencies. "
            "You cannot proceed without resolution. Call `todo_write(merge=true)` to mark unachievable tasks as 'cancelled' "
            "or update steps before finishing."
        )
    elif blocked_count > 0:
        lines.append(
            "[BLOCKED TASKS DETECTED] Focus on unblocked tasks first, or use `todo_write(merge=true)` to replan/cancel unexecutable steps."
        )

    lines.append(_SNAPSHOT_NOTE)
    return "\n".join(lines)


def _without_previous_progress(message: AnyMessage) -> AnyMessage:
    """``message`` without a progress block an earlier request left in its content."""
    content = message.content
    if isinstance(content, str):
        return message.model_copy(update={"content": _strip_previous_progress(content)})
    cleaned_parts: list[str | dict[str, object]] = []
    for part in content:
        if isinstance(part, dict) and part.get("type") == "text" and isinstance(part.get("text"), str):
            cleaned_text = _strip_previous_progress(part["text"])
            if cleaned_text:
                cleaned_parts.append({**part, "text": cleaned_text})
        else:
            cleaned_parts.append(part)
    return message.model_copy(update={"content": cleaned_parts})


def _with_focus(messages: Sequence[AnyMessage], focus: str) -> list[AnyMessage]:
    """``messages`` with the todo focus at the tail of the user's latest message, or behind them all when the user wrote none.

    The SystemMessages that sit behind the user's message on the first model call (the boundary rules, the session
    directories) stay where they are: the focus belongs on the user's message, not after them.
    """
    index = last_user_authored_index(messages)
    if index == -1:
        return [*messages, runtime_human_message(focus)]
    cleaned = list(messages)
    cleaned[index] = _without_previous_progress(cleaned[index])
    return append_block_to_last_user_message(cleaned, focus)


async def _render_focus(
    get_todos_fn: Callable[[str | None], Awaitable[TodoStore | None]],
    request: ModelRequest,
) -> str | None:
    """The todo focus for the todos the run holds now, or None when there is nothing left to do."""
    store = await get_todos_fn(run_workspace(getattr(request, "runtime", None)))
    if store is None:
        return None
    incomplete = store.incomplete_todos()
    return _build_progress_injection(store, incomplete) if incomplete else None


def progress_middleware(
    get_todos_fn: Callable[[str | None], Awaitable[TodoStore | None]],
) -> AgentMiddleware[AgentState[object], None, object]:
    """Inject the todo focus into the user's latest message once per run (non-persistent).

    The focus is rendered on the first request of the run and shown unchanged on every later one: rewriting the
    user's message between two requests of a tool loop would change the prefix the provider caches and invalidate
    the reasoning blocks written under it. The model reads the todo state of the moment from the ``todo_write``
    results the loop produces. A run that holds no open todos when it starts shows no focus for the rest of it.
    """

    @wrap_model_call(name="progress_middleware")
    async def _middleware(
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        if not request.messages:
            return await handler(request)
        focus = await frozen_for_run(run_scope(request), _FOCUS_KEY, lambda: _render_focus(get_todos_fn, request))
        if focus is None:
            return await handler(request)
        return await handler(request.override(messages=_with_focus(request.messages, focus)))

    return _middleware


__all__ = ["progress_middleware"]
