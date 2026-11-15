"""Branch-bound todo state: folds the active message branch into the authoritative TodoStore.

[INPUT]
- progress.schemas::TodoStore (POS: Pydantic models of the per-chat todo list)
- Sequence of message-like objects or dicts whose extra_data may carry a todo_write snapshot

[OUTPUT]
- TOOL_DETAILS_KEY: extra_data slot holding a message's todo_write snapshot
- fold_branch_todo_state: pure fold of an active message branch into the TodoStore its latest snapshot describes

[POS]
Binds todo state to the message tree, so every branch yields its own plan and a rewind, retry or sibling switch
can realign the workspace todo file without cross-branch leakage. Only the snapshot slot is trusted: message text
and loose keys never become a plan.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from pydantic import ValidationError

if TYPE_CHECKING:
    from myrm_agent_harness.agent.meta_tools.progress.schemas import TodoStore

logger = logging.getLogger(__name__)

TOOL_DETAILS_KEY = "tool_result_details"


def _read_snapshot(msg: object) -> TodoStore | None:
    """Parse the todo_write snapshot a message carries in its extra_data slot, if any."""
    extra_data = msg.get("extra_data") if isinstance(msg, Mapping) else getattr(msg, "extra_data", None)
    if not isinstance(extra_data, dict):
        return None
    snapshot = extra_data.get(TOOL_DETAILS_KEY)
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("todos"), list):
        return None

    # Imported on first use: loading agent.meta_tools imports this package.
    from myrm_agent_harness.agent.meta_tools.progress.schemas import TodoStore

    try:
        return TodoStore.model_validate(snapshot)
    except ValidationError as exc:
        # Only the count is logged: the validation text echoes task content, which must not reach logs.
        logger.warning("Skipping malformed todo snapshot (%d validation errors)", exc.error_count())
        return None


def fold_branch_todo_state(messages: Sequence[object]) -> TodoStore | None:
    """Fold the active message branch (root to leaf) into the TodoStore its latest snapshot describes.

    A snapshot with a lower revision than the current state never overwrites it; an unversioned one always does.
    """
    current: TodoStore | None = None
    for msg in messages:
        snapshot = _read_snapshot(msg)
        if snapshot is None:
            continue
        if current is None or snapshot.revision >= current.revision or not snapshot.revision:
            current = snapshot
    return current


__all__ = [
    "TOOL_DETAILS_KEY",
    "fold_branch_todo_state",
]
