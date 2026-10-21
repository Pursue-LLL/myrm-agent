"""Claude Code JSONL transcript parser.

[INPUT]
Raw JSONL lines from a Claude Code session transcript, pre-parsed by the
frontend into a list of dicts.

[OUTPUT]
ClaudeCodeParseResult: deduplicated entries, conversation turns, and
normalized memory buckets (semantic / episodic / procedural).

[POS]
Stateless parser for Claude Code JSONL transcripts.  Handles streaming
duplicate dedup (last-write-wins by ``id``), entry classification, and
mapping to the native memory bucket schema consumed by
``import_adapters._dry_run_claude_code_jsonl``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

MAX_CLAUDE_CODE_LINES = 200_000
MAX_CLAUDE_CODE_ENTRIES = 50_000
MAX_CONTENT_CHARS = 800
MAX_TOOL_SUMMARY_CHARS = 400
MAX_TURNS_FOR_EPISODIC = 500
MAX_SUMMARIES_FOR_SEMANTIC = 200
MAX_ERRORS_FOR_PROCEDURAL = 100

WARNING_TOO_MANY_LINES = "claude_code_too_many_lines"
WARNING_TOO_MANY_ENTRIES = "claude_code_too_many_entries"
WARNING_NO_CONVERSATION_ENTRIES = "claude_code_no_conversation_entries"

_KNOWN_ENTRY_TYPES = frozenset(
    {
        "user",
        "assistant",
        "system",
        "summary",
        "file-history-snapshot",
        "pr-link",
        "progress",
        "queue-operation",
        "saved_hook_context",
    }
)


@dataclass(slots=True)
class ConversationTurn:
    """A paired user→assistant exchange."""

    user_content: str
    assistant_content: str
    tool_names: list[str] = field(default_factory=list)
    timestamp: str = ""


@dataclass(slots=True)
class ClaudeCodeParseResult:
    """Result of parsing a Claude Code JSONL transcript."""

    total_lines: int = 0
    deduplicated_entries: int = 0
    user_entries: int = 0
    assistant_entries: int = 0
    summary_entries: int = 0
    system_entries: int = 0
    skipped_entries: int = 0
    turns: list[ConversationTurn] = field(default_factory=list)
    summaries: list[dict[str, object]] = field(default_factory=list)
    errors: list[dict[str, object]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def parse_claude_code_lines(
    lines: list[object],
) -> ClaudeCodeParseResult:
    """Parse pre-deserialized JSONL lines into a structured result."""

    result = ClaudeCodeParseResult(total_lines=len(lines))

    if len(lines) > MAX_CLAUDE_CODE_LINES:
        result.warnings.append(WARNING_TOO_MANY_LINES)
        lines = lines[:MAX_CLAUDE_CODE_LINES]

    entries = _dedup_by_id(lines)
    result.deduplicated_entries = len(entries)

    if len(entries) > MAX_CLAUDE_CODE_ENTRIES:
        result.warnings.append(WARNING_TOO_MANY_ENTRIES)
        entries = entries[:MAX_CLAUDE_CODE_ENTRIES]

    user_msgs: list[dict[str, object]] = []
    assistant_msgs: list[dict[str, object]] = []

    for entry in entries:
        entry_type = _str(entry.get("type"))
        if entry_type == "user":
            result.user_entries += 1
            user_msgs.append(entry)
        elif entry_type == "assistant":
            result.assistant_entries += 1
            assistant_msgs.append(entry)
        elif entry_type == "summary":
            result.summary_entries += 1
            if len(result.summaries) < MAX_SUMMARIES_FOR_SEMANTIC:
                result.summaries.append(entry)
        elif entry_type == "system":
            result.system_entries += 1
            if _is_error_system_entry(entry) and len(result.errors) < MAX_ERRORS_FOR_PROCEDURAL:
                result.errors.append(entry)
        elif entry_type in _KNOWN_ENTRY_TYPES:
            result.skipped_entries += 1
        else:
            result.skipped_entries += 1

    if result.user_entries == 0 and result.assistant_entries == 0:
        result.warnings.append(WARNING_NO_CONVERSATION_ENTRIES)

    result.turns = _build_turns(user_msgs, assistant_msgs)
    return result


def turns_to_episodic(turns: list[ConversationTurn]) -> list[dict[str, object]]:
    """Map conversation turns to episodic memory entries."""

    now = datetime.now(UTC).isoformat()
    capped = turns[:MAX_TURNS_FOR_EPISODIC]
    memories: list[dict[str, object]] = []

    for turn in capped:
        user_preview = turn.user_content[:MAX_CONTENT_CHARS]
        assistant_preview = turn.assistant_content[:MAX_CONTENT_CHARS]
        content_parts = [f"User: {user_preview}"]
        if turn.tool_names:
            content_parts.append(f"Tools: {', '.join(turn.tool_names[:10])}")
        content_parts.append(f"Assistant: {assistant_preview}")

        memories.append(
            {
                "content": "\n".join(content_parts),
                "event_type": "claude_code_conversation_turn",
                "timestamp": turn.timestamp or now,
                "related_entities": turn.tool_names[:10],
                "importance": 0.5,
                "metadata": {
                    "external_source": "claude_code_jsonl",
                    "tool_count": len(turn.tool_names),
                },
            }
        )

    return memories


def summaries_to_semantic(summaries: list[dict[str, object]]) -> list[dict[str, object]]:
    """Map Claude Code summary entries to semantic memory."""

    now = datetime.now(UTC).isoformat()
    memories: list[dict[str, object]] = []

    for entry in summaries[:MAX_SUMMARIES_FOR_SEMANTIC]:
        content = _extract_summary_content(entry)
        if not content:
            continue
        memories.append(
            {
                "content": content[: MAX_CONTENT_CHARS * 2],
                "importance": 0.75,
                "confidence": 0.8,
                "created_at": now,
                "updated_at": now,
                "metadata": {"external_source": "claude_code_jsonl", "entry_type": "summary"},
            }
        )

    return memories


def errors_to_procedural(errors: list[dict[str, object]]) -> list[dict[str, object]]:
    """Map system error entries to procedural memory rules."""

    now = datetime.now(UTC).isoformat()
    memories: list[dict[str, object]] = []

    for entry in errors[:MAX_ERRORS_FOR_PROCEDURAL]:
        error_text = _extract_error_content(entry)
        if not error_text:
            continue
        memories.append(
            {
                "content": f"Avoid this error: {error_text[:MAX_TOOL_SUMMARY_CHARS]}",
                "trigger": "When encountering similar error patterns",
                "action": f"Review and avoid: {error_text[:MAX_TOOL_SUMMARY_CHARS]}",
                "priority": 5,
                "trigger_keywords": [],
                "created_at": now,
                "updated_at": now,
                "metadata": {"external_source": "claude_code_jsonl", "entry_type": "system_error"},
            }
        )

    return memories


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _dedup_by_id(lines: list[object]) -> list[dict[str, object]]:
    """Deduplicate entries by ``id`` field (last write wins)."""

    seen: dict[str, int] = {}
    entries: list[dict[str, object]] = []

    for raw in lines:
        if not isinstance(raw, dict):
            continue
        entry = {str(k): v for k, v in raw.items()}
        entry_id = _str(entry.get("id"))
        if entry_id:
            if entry_id in seen:
                entries[seen[entry_id]] = entry
            else:
                seen[entry_id] = len(entries)
                entries.append(entry)
        else:
            entries.append(entry)

    return entries


def _build_turns(
    user_msgs: list[dict[str, object]],
    assistant_msgs: list[dict[str, object]],
) -> list[ConversationTurn]:
    """Pair user and assistant messages into conversation turns."""

    turns: list[ConversationTurn] = []
    assistant_idx = 0

    for user_msg in user_msgs:
        user_content = _extract_message_content(user_msg)
        if not user_content:
            continue

        assistant_content = ""
        tool_names: list[str] = []
        timestamp = _str(user_msg.get("timestamp")) or datetime.now(UTC).isoformat()

        if assistant_idx < len(assistant_msgs):
            a_msg = assistant_msgs[assistant_idx]
            assistant_content = _extract_message_content(a_msg)
            tool_names = _extract_tool_names(a_msg)
            assistant_idx += 1

        turns.append(
            ConversationTurn(
                user_content=user_content,
                assistant_content=assistant_content,
                tool_names=tool_names,
                timestamp=timestamp,
            )
        )

    return turns


def _extract_message_content(entry: dict[str, object]) -> str:
    """Extract text content from a user or assistant entry."""

    message = entry.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, dict):
                    text = block.get("text")
                    if isinstance(text, str):
                        parts.append(text.strip())
            return "\n".join(parts)

    content = entry.get("content")
    if isinstance(content, str):
        return content.strip()
    return ""


def _extract_tool_names(entry: dict[str, object]) -> list[str]:
    """Extract tool names from an assistant entry's content blocks."""

    names: list[str] = []
    message = entry.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    name = block.get("name")
                    if isinstance(name, str) and name not in names:
                        names.append(name)
    return names


def _extract_summary_content(entry: dict[str, object]) -> str:
    """Extract text from a summary entry."""

    summary = entry.get("summary")
    if isinstance(summary, str):
        return summary.strip()
    message = entry.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
    content = entry.get("content")
    if isinstance(content, str):
        return content.strip()
    return ""


def _extract_error_content(entry: dict[str, object]) -> str:
    """Extract error description from a system entry."""

    error = entry.get("error")
    if isinstance(error, str):
        return error.strip()
    message = entry.get("message")
    if isinstance(message, str):
        return message.strip()
    return ""


def _is_error_system_entry(entry: dict[str, object]) -> bool:
    """Check if a system entry represents an API or tool error."""

    subtype = _str(entry.get("subtype"))
    return subtype in {"api_error", "error", "tool_error"} or bool(entry.get("error"))


def _str(value: object) -> str:
    return str(value).strip() if isinstance(value, str) else ""
