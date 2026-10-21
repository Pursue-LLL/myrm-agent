"""Catchup brief extraction: what happened in a chat while the user was away.

[INPUT]
- app.services.chat.chat_helpers::WAKEUP_MESSAGE_ID_PREFIX (POS: id prefix of system-injected wakeup rows)

[OUTPUT]
- CatchupStatus / NeedsFromUser: closed vocabularies; the frontend localizes them
- CatchupBrief: bounded, UI-ready summary of one chat
- extract_catchup_brief: build a brief from the unseen messages and their progress steps

[POS]
Pure business-layer projection behind the Catchup inbox. No I/O, no framework coupling.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal

from pydantic import BaseModel, Field

from app.services.chat.chat_helpers import WAKEUP_MESSAGE_ID_PREFIX

CatchupStatus = Literal["completed", "running", "waiting_for_approval", "error", "stopped"]
NeedsFromUser = Literal["approval", "error", "question"]

PROMPT_PREVIEW_MAX_CHARS = 160
RESULT_PREVIEW_MAX_CHARS = 240

_FILE_MUTATION_TOOLS = frozenset({"file_write_tool", "file_edit_tool", "file_replace_tool", "file_patch_tool"})
_QUESTION_MARKS = ("?", "？")


class CatchupBrief(BaseModel):
    """Summary of one chat's unseen activity, sized for a notification card."""

    last_user_prompt: str = Field(default="", description="What the person last asked, bounded for display")
    result_preview: str = Field(default="", description="Opening of the latest agent reply, bounded for display")
    files_touched: list[str] = Field(default_factory=list, description="Unique file paths the agent modified")
    tool_counts: dict[str, int] = Field(default_factory=dict, description="Invocation count per tool")
    needs_from_user: NeedsFromUser | None = Field(default=None, description="Why the agent needs the person, if it does")
    status: CatchupStatus = "completed"


def _preview(text: str, limit: int) -> str:
    """Collapse whitespace and cut to ``limit`` characters with an ellipsis."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1].rstrip() + "…"


def _needs_from_user(status: CatchupStatus, latest_reply: str) -> NeedsFromUser | None:
    if status == "waiting_for_approval":
        return "approval"
    if status == "error":
        return "error"
    if latest_reply.rstrip().endswith(_QUESTION_MARKS):
        return "question"
    return None


def _scan_progress_steps(progress_steps: Sequence[Mapping[str, object]]) -> tuple[dict[str, int], list[str]]:
    """Count tool invocations and collect the file paths that file-mutating tools touched."""
    tool_counts: dict[str, int] = {}
    files: set[str] = set()
    for step in progress_steps:
        tool_name = step.get("tool_name")
        if not isinstance(tool_name, str) or not tool_name:
            continue
        tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1
        items = step.get("items")
        if tool_name not in _FILE_MUTATION_TOOLS or not isinstance(items, list):
            continue
        for item in items:
            path = item.get("path") if isinstance(item, dict) else None
            if isinstance(path, str) and path:
                files.add(path)
    return tool_counts, sorted(files)


def extract_catchup_brief(
    messages: Sequence[Mapping[str, object]],
    progress_steps: Sequence[Mapping[str, object]],
    status: CatchupStatus,
) -> CatchupBrief:
    """Build the brief of a chat from its unseen messages (oldest first) and their progress steps.

    System wakeup rows are user-role rows the person never typed, so they never count as the prompt.
    """
    last_prompt = ""
    latest_reply = ""
    for message in reversed(messages):
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        role = message.get("role")
        if role == "assistant" and not latest_reply:
            latest_reply = content
        elif role == "user" and not last_prompt and not str(message.get("id", "")).startswith(WAKEUP_MESSAGE_ID_PREFIX):
            last_prompt = content
        if last_prompt and latest_reply:
            break

    tool_counts, files_touched = _scan_progress_steps(progress_steps)
    return CatchupBrief(
        last_user_prompt=_preview(last_prompt, PROMPT_PREVIEW_MAX_CHARS),
        result_preview=_preview(latest_reply, RESULT_PREVIEW_MAX_CHARS),
        files_touched=files_touched,
        tool_counts=tool_counts,
        needs_from_user=_needs_from_user(status, latest_reply),
        status=status,
    )
