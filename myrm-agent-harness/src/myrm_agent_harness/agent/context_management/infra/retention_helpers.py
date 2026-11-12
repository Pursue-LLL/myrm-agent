"""Shared retention helpers for context pipeline processors.

[INPUT]
- infra.message_priority::_is_tool_error
- strategies.priority_signals::group_matches_focus_signals, group_matches_goal_hint (POS: compression priority signal matchers)
- strategies.tool_call_groups::build_tool_call_groups

[OUTPUT]
- extract_failed_tool_call_ids / extract_focus_files / extract_focus_modules / extract_user_goal_hint: read compression intent fields
- build_tool_call_group_by_id: map tool_call_id to ToolCallGroup for Filter retention
- tool_message_matches_focus_signals: body-only fallback when group pairing is unavailable
- should_retain_tool_message: skip LLM semantic filter for failed/error/focus/goal tool outputs (group-aware)
- effective_keep_recent_calls: eco-adjusted keep_recent_calls shared by ActivePrune + Compress
- find_keep_recent_prune_cutoff: ActivePrune's positional protection window (the newest keep_recent_calls groups)
- is_tool_result_consumed: whether the model has read a tool result yet (an AIMessage follows it)
- format_retained_tool_trim_message / structure_trim_tokens_saved: deterministic trim helpers

[POS]
Cross-processor retention contract. Filter and Compress read the same failed-tool, focus-file, and goal-hint
intent without a separate planner processor. ActivePrune and Compress share the keep_recent_calls window and the
rule that a result the model has not read yet is not rewritten.
"""

from __future__ import annotations

from collections.abc import Sequence

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

from myrm_agent_harness.utils.text_utils import get_token_count

from ..strategies.priority_signals import group_matches_focus_signals, group_matches_goal_hint
from ..strategies.tool_call_groups import ToolCallGroup, build_tool_call_groups
from .message_priority import _is_tool_error

_ECO_KEEP_RECENT_REDUCTION = 2
_ECO_KEEP_RECENT_MIN = 2


def _read_compression_intent(metadata: dict[str, object]) -> dict[str, object]:
    raw_intent = metadata.get("compression_intent")
    if isinstance(raw_intent, dict):
        return raw_intent
    return {}


def extract_failed_tool_call_ids(metadata: dict[str, object]) -> frozenset[str]:
    """Read failed tool-call IDs from pipeline metadata compression intent."""
    raw_failed_ids = _read_compression_intent(metadata).get("failed_tool_call_ids")
    if not isinstance(raw_failed_ids, list):
        return frozenset()

    return frozenset(tool_call_id for tool_call_id in raw_failed_ids if isinstance(tool_call_id, str) and tool_call_id)


def extract_focus_files(metadata: dict[str, object]) -> frozenset[str]:
    """Read focus and pinned file paths from pipeline metadata compression intent."""
    raw_focus_files = _read_compression_intent(metadata).get("focus_files")
    raw_pinned_files = _read_compression_intent(metadata).get("pinned_files")
    merged: set[str] = set()
    if isinstance(raw_focus_files, list):
        merged.update(file_path for file_path in raw_focus_files if isinstance(file_path, str) and file_path)
    if isinstance(raw_pinned_files, list):
        merged.update(file_path for file_path in raw_pinned_files if isinstance(file_path, str) and file_path)
    return frozenset(merged)


def extract_pinned_files(metadata: dict[str, object]) -> frozenset[str]:
    """Read pinned file paths from pipeline metadata compression intent."""
    raw_pinned_files = _read_compression_intent(metadata).get("pinned_files")
    if not isinstance(raw_pinned_files, list):
        return frozenset()
    return frozenset(file_path for file_path in raw_pinned_files if isinstance(file_path, str) and file_path)


def extract_focus_modules(metadata: dict[str, object]) -> frozenset[str]:
    """Read focus module paths from pipeline metadata compression intent."""
    raw_focus_modules = _read_compression_intent(metadata).get("focus_modules")
    if not isinstance(raw_focus_modules, list):
        return frozenset()

    return frozenset(module_name for module_name in raw_focus_modules if isinstance(module_name, str) and module_name)


def extract_user_goal_hint(metadata: dict[str, object]) -> str:
    """Read user goal hint from pipeline metadata compression intent."""
    raw_goal_hint = _read_compression_intent(metadata).get("user_goal_hint")
    if not isinstance(raw_goal_hint, str):
        return ""
    return raw_goal_hint.strip()


def build_tool_call_group_by_id(messages: list[BaseMessage]) -> dict[str, ToolCallGroup]:
    """Map tool_call_id to its ToolCallGroup for Filter retention lookups."""
    return {group.tool_call_id: group for group in build_tool_call_groups(messages)}


def effective_keep_recent_calls(*, keep_recent_calls: int, eco_mode: bool) -> int:
    """Mirror CompressProcessor eco adjustment for keep_recent_calls."""
    if not eco_mode:
        return max(keep_recent_calls, 0)
    return max(_ECO_KEEP_RECENT_MIN, keep_recent_calls - _ECO_KEEP_RECENT_REDUCTION)


def tool_message_matches_focus_signals(
    msg: ToolMessage,
    *,
    focus_files: frozenset[str],
    focus_modules: frozenset[str],
) -> bool:
    """Return True when tool output references a structured focus file/module signal."""
    if not focus_files and not focus_modules:
        return False

    content = msg.content if isinstance(msg.content, str) else str(msg.content or "")
    haystack = content.lower()
    for signal in (*focus_files, *focus_modules):
        normalized = signal.removeprefix("./").lower()
        if normalized and normalized in haystack:
            return True
    return False


def should_retain_tool_message(
    msg: ToolMessage,
    failed_tool_call_ids: frozenset[str],
    *,
    focus_files: frozenset[str] | None = None,
    focus_modules: frozenset[str] | None = None,
    user_goal_hint: str = "",
    group: ToolCallGroup | None = None,
) -> bool:
    """Return True when Filter should use deterministic trim instead of LLM summary."""
    tool_call_id = getattr(msg, "tool_call_id", None)
    if isinstance(tool_call_id, str) and tool_call_id and tool_call_id in failed_tool_call_ids:
        return True

    normalized_focus_files = focus_files or frozenset()
    normalized_focus_modules = focus_modules or frozenset()

    if group is not None:
        if group_matches_focus_signals(
            group,
            focus_files=normalized_focus_files,
            focus_modules=normalized_focus_modules,
        ):
            return True
        if user_goal_hint and group_matches_goal_hint(group, user_goal_hint):
            return True
    elif tool_message_matches_focus_signals(
        msg,
        focus_files=normalized_focus_files,
        focus_modules=normalized_focus_modules,
    ):
        return True

    return _is_tool_error(msg)


def format_retained_tool_trim_message(trimmed_content: str, *, saved_path: str | None) -> str:
    """Format a deterministic trim preview for retained error/failed tool output."""
    if not saved_path:
        return f"[RETAINED TOOL OUTPUT - deterministic trim; no full copy was saved]\n{trimmed_content}"
    return "\n".join(
        [
            "[RETAINED TOOL OUTPUT - deterministic trim; full content preserved on disk]",
            trimmed_content,
            f"Full output saved to: {saved_path}",
            "Use file_read_tool to read specific portions of the saved file.",
        ]
    )


def is_tool_result_consumed(messages: Sequence[BaseMessage], tool_idx: int) -> bool:
    """Return True once an AIMessage follows the ToolMessage, i.e. the model has read the result.

    A result with no AIMessage after it is the unread tail of the step in progress, which the next model call still
    needs verbatim: ActivePrune leaves it alone unless the runtime forces the prune, and Compress counts it against
    its keep_recent_calls slots instead of rewriting it.
    """
    return any(isinstance(messages[i], AIMessage) for i in range(tool_idx + 1, len(messages)))


def find_keep_recent_prune_cutoff(messages: list[BaseMessage], keep_recent_calls: int) -> int:
    """Return the max ToolMessage index that may be pruned (exclusive upper bound).

    Tool messages at index >= cutoff are within the keep_recent tool-call window
    and must not be active-pruned. Falls back to 0 when all groups are protected.
    """
    if keep_recent_calls <= 0:
        return len(messages)

    groups = build_tool_call_groups(messages)
    if not groups:
        return 0

    if len(groups) <= keep_recent_calls:
        return groups[0].tool_index

    first_protected = groups[-keep_recent_calls]
    return first_protected.tool_index


def structure_trim_tokens_saved(original: str, trimmed: str) -> int:
    """Estimate tokens saved by deterministic structure trim."""
    return max(0, get_token_count(original) - get_token_count(trimmed))
