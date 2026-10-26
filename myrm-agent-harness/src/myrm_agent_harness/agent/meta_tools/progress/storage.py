"""Workspace SSOT for chat todos (`.myrm/progress/<chat>/todos.json`).

Chats of one project share its workspace directory, so each chat keeps its own list under its own directory.

[INPUT]
- progress.schemas::TodoItem, TodoStore (POS: models)
- infra.atomic_write::atomic_write (POS: crash-safe writes)
- context_management.infra.evicted::normalize_delivery_chat_id (POS: session id to chat id, the same key the evicted-content directories use)
- core.context_vars::chat_id_var (POS: the chat of the running agent)

[OUTPUT]
- read/write/merge todos under workspace `.myrm/progress/<chat>/`
- todo_scope, todos_path, workspace_todos_exist helpers

[POS]
Persists main-agent todo state in chat workspace (atomic JSON).
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from myrm_agent_harness.agent.context_management.infra.evicted import normalize_delivery_chat_id
from myrm_agent_harness.agent.meta_tools.progress.schemas import TodoItem, TodoStatus, TodoStore
from myrm_agent_harness.core.context_vars import chat_id_var
from myrm_agent_harness.infra.atomic_write import atomic_write

logger = logging.getLogger(__name__)

PROGRESS_RELATIVE_DIR = ".myrm/progress"
TODOS_FILENAME = "todos.json"
DEFAULT_TODO_SCOPE = "default"

_UNSAFE_SCOPE_CHARS = re.compile(r"[^A-Za-z0-9_.-]")


def todo_scope(chat_id: str | None = None) -> str:
    """The directory a chat's todo list lives in, under the workspace's progress directory.

    ``None`` names the chat of the running agent. A run that has no chat identity at all shares the
    ``default`` list. The name is a single path component, so no id can point outside the progress directory.
    """
    raw = chat_id_var.get() if chat_id is None else chat_id
    scope = _UNSAFE_SCOPE_CHARS.sub("_", normalize_delivery_chat_id(raw)).lstrip(".")
    return scope or DEFAULT_TODO_SCOPE


def todos_path(workspace_root: str, chat_id: str | None = None) -> Path:
    return Path(workspace_root) / PROGRESS_RELATIVE_DIR / todo_scope(chat_id) / TODOS_FILENAME


def read_todos_sync_from_workspace(workspace_root: str, chat_id: str | None = None) -> TodoStore | None:
    path = todos_path(workspace_root, chat_id)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return None
        return TodoStore.model_validate(raw)
    except Exception as exc:
        logger.warning("Failed to read todos from %s: %s", path, exc)
        return None


def write_todos_sync_to_workspace(workspace_root: str, store: TodoStore, chat_id: str | None = None) -> None:
    path = todos_path(workspace_root, chat_id)
    atomic_write(path, store.model_dump_json(indent=2))


def workspace_todos_exist(*, workspace_root: str | None) -> bool:
    """True when any chat has a todo list in the workspace.

    Asked while an agent is built, before the chat it will serve is known, so it cannot name a chat.
    """
    if not workspace_root:
        return False
    progress_dir = Path(workspace_root) / PROGRESS_RELATIVE_DIR
    return any(progress_dir.glob(f"*/{TODOS_FILENAME}"))


def delete_todos_sync_from_workspace(workspace_root: str, chat_id: str | None = None) -> None:
    path = todos_path(workspace_root, chat_id)
    if path.is_file():
        path.unlink()


def merge_todo_items(
    current: list[TodoItem],
    incoming: list[TodoItem],
    *,
    merge: bool,
) -> list[TodoItem]:
    """Merge incoming items with existing ones.

    When merge=False, replaces the list with incoming items (which must each have valid content).
    When merge=True, updates existing items by id (inheriting previous content/status if omitted)
    or appends newly created items.
    """
    if not merge:
        for item in incoming:
            if not item.content:
                item.content = item.id
        return incoming

    by_id = {item.id: item for item in current}
    order: list[str] = [item.id for item in current]

    for item in incoming:
        if item.id in by_id:
            old_item = by_id[item.id]
            resolved_content = item.content if item.content else old_item.content
            # Inherit existing status on partial updates when incoming item omits status
            resolved_status = item.status if item.explicit_status else old_item.status
            by_id[item.id] = TodoItem(id=item.id, content=resolved_content, status=resolved_status)
        else:
            if not item.content:
                msg = f"content is required for new item '{item.id}'"
                raise ValueError(msg)
            order.append(item.id)
            by_id[item.id] = TodoItem(id=item.id, content=item.content, status=item.status)

    return [by_id[item_id] for item_id in order if item_id in by_id]


def parse_todo_payload(raw_items: list[object], *, allow_empty_content: bool = False) -> list[TodoItem]:
    """Parse raw todo objects into validated TodoItem instances.

    Args:
        raw_items: Raw list of dictionaries from tool arguments.
        allow_empty_content: When True (used in merge mode), content may be empty to allow
            partial status-only updates for existing items.
    """
    parsed: list[TodoItem] = []
    valid_statuses_str = ", ".join(f"'{s.value}'" for s in TodoStatus)

    for index, raw in enumerate(raw_items):
        if not isinstance(raw, dict):
            msg = f"todos[{index}] must be an object"
            raise ValueError(msg)
        item_id = str(raw.get("id") or raw.get("step_id") or raw.get("key") or "").strip()
        content = str(
            raw.get("content")
            or raw.get("description")
            or raw.get("title")
            or raw.get("task")
            or raw.get("name")
            or raw.get("todo")
            or ""
        ).strip()
        if not item_id:
            # If id is missing, assign a deterministic synthetic id from index
            item_id = f"task_{index + 1}"
        if not content and not allow_empty_content:
            # Fallback to item_id if content is still empty on initialization
            content = item_id
        has_status = "status" in raw and raw["status"] is not None
        if has_status:
            status_raw = str(raw["status"]).strip()
            try:
                status = TodoStatus(status_raw)
            except ValueError as exc:
                msg = f"todos[{index}].status '{status_raw}' is invalid. Valid statuses are: [{valid_statuses_str}]"
                raise ValueError(msg) from exc
            explicit_status = True
        else:
            status = TodoStatus.PENDING
            explicit_status = False
        parsed.append(TodoItem(id=item_id, content=content, status=status, explicit_status=explicit_status))
    return parsed
