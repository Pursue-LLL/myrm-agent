"""File integrity guard: read-before-write gate, content version matching and the masked write-back check.

Provides four complementary protections for file mutation operations:
1. Read-gate: refuses mutations on files never read in the current session.
2. Full-read gate: refuses edits after partial/range reads (marker-only).
3. Version gate: hard-rejects when on-disk content hash differs from the
   hash recorded at full-read time (external or concurrent modification).
4. Masked write-back gate: refuses a write that carries a mask the redactor puts in place of a secret
   (``***``, ``sk-pro...7890``). A read shows the mask, the file holds the real value, and text copied from the
   read would replace it.

Self-writes update the recorded hash via ``record_write`` so consecutive
edits by the same agent on content it just wrote remain allowed.

[INPUT]
- agent.middlewares._session_context::get_subagent_task_id (POS: ContextVar for subagent task ID)
- core.security.redact::redact_sensitive_text (POS: the redactor, whose masks a read and a command output show)
- utils.errors::ToolError (POS: tool error type)

[OUTPUT]
- FileIntegrityGuard: Per-executor file integrity guard (agent-aware)
- get_file_integrity_guard: Module-level factory function
- raise_if_integrity_rejection: raises the read, full-read and version rejections of a mutation as a ToolError
- raise_if_masked_writeback: raises when new content carries a mask the file does not

[POS]
File integrity guard for sandbox file mutations. Agent-aware per-agent buckets.
Per-executor isolation via module-level factory.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Sequence
from typing import TYPE_CHECKING

from myrm_agent_harness.core.security.redact import redact_sensitive_text
from myrm_agent_harness.utils.errors import ToolError

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.code_execution.executors.base import CodeExecutor

_DEFAULT_AGENT_ID = "__main__"

# Every mask of the redactor holds one of these: ``***``, ``head...tail`` and the ``...redacted...`` line of a key block.
_MASK_MARKS = ("***", "...")

# How far a mask fragment reaches into the words around it; keeps a compact one-line JSON from becoming one fragment.
_CONTEXT_CHARS = 12
_MIN_FRAGMENT_CHARS = 8


def content_hash(content: str) -> str:
    return hashlib.md5(content.encode("utf-8")).hexdigest()


def _current_agent_id() -> str:
    try:
        from myrm_agent_harness.agent.middlewares._session_context import get_subagent_task_id

        return get_subagent_task_id() or _DEFAULT_AGENT_ID
    except Exception:
        return _DEFAULT_AGENT_ID


class FileIntegrityGuard:
    """Read-gate + full-read gate + version gate for file mutations."""

    __slots__ = ("_agent_read_hashes",)

    _PARTIAL_READ_SENTINEL = ""

    def __init__(self) -> None:
        self._agent_read_hashes: dict[str, dict[str, str]] = {}

    def record_read(self, path: str, content: str, agent_id: str | None = None) -> None:
        aid = agent_id or _current_agent_id()
        norm = os.path.normpath(path)
        bucket = self._agent_read_hashes.setdefault(aid, {})
        bucket[norm] = content_hash(content)

    def record_read_marker(self, path: str, agent_id: str | None = None) -> None:
        aid = agent_id or _current_agent_id()
        norm = os.path.normpath(path)
        bucket = self._agent_read_hashes.setdefault(aid, {})
        if norm not in bucket:
            bucket[norm] = self._PARTIAL_READ_SENTINEL

    def record_write(self, path: str, content: str, agent_id: str | None = None) -> None:
        aid = agent_id or _current_agent_id()
        norm = os.path.normpath(path)
        bucket = self._agent_read_hashes.setdefault(aid, {})
        bucket[norm] = content_hash(content)

    def require_read_before_write(self, path: str, agent_id: str | None = None) -> str | None:
        aid = agent_id or _current_agent_id()
        norm = os.path.normpath(path)
        bucket = self._agent_read_hashes.get(aid)
        if bucket is not None and norm in bucket:
            return None
        return (
            f"File '{norm}' has not been read in this session. "
            "You must call file_read_tool to read the file before editing it, "
            "so your SEARCH text matches the actual bytes on disk."
        )

    def require_full_read_before_edit(self, path: str, agent_id: str | None = None) -> str | None:
        """Reject edits when only a partial/range read marker exists."""
        aid = agent_id or _current_agent_id()
        norm = os.path.normpath(path)
        bucket = self._agent_read_hashes.get(aid)
        if bucket is None:
            return None
        expected = bucket.get(norm)
        if expected != self._PARTIAL_READ_SENTINEL:
            return None
        return (
            f"File '{norm}' was only partially read in this session. "
            "Call file_read_tool without a line range (or read the full file) "
            "before editing, so version checking can protect against stale edits."
        )

    def require_version_match(
        self,
        path: str,
        disk_content: str,
        agent_id: str | None = None,
        anchor: str | Sequence[str] | None = None,
    ) -> str | None:
        """Hard-reject when disk content hash differs from the last full-read hash."""
        aid = agent_id or _current_agent_id()
        norm = os.path.normpath(path)
        bucket = self._agent_read_hashes.get(aid)
        if bucket is None:
            return None
        expected = bucket.get(norm)
        if expected is None or expected == self._PARTIAL_READ_SENTINEL:
            return None
        current = content_hash(disk_content)
        if current == expected:
            return None

        if len(disk_content) <= 2000:
            preview = disk_content
        else:
            candidates: list[str] = []
            if isinstance(anchor, str):
                candidates = [anchor]
            elif anchor is not None:
                candidates = [c for c in anchor if isinstance(c, str)]

            anchor_pos = -1
            matched_len = 0
            for cand in candidates:
                clean_cand = cand.strip()
                if not clean_cand:
                    continue
                # 1. 优先整块精确匹配
                pos = disk_content.find(clean_cand)
                if pos != -1:
                    anchor_pos = pos
                    matched_len = len(clean_cand)
                    break
                # 2. 二级降级：提取首条有效特征行（非空、非注释、长度>=4）次级定位
                for line in clean_cand.splitlines():
                    sline = line.strip()
                    if sline and len(sline) >= 4 and not sline.startswith("#"):
                        pos = disk_content.find(sline)
                        if pos != -1:
                            anchor_pos = pos
                            matched_len = len(sline)
                            break
                if anchor_pos != -1:
                    break

            if anchor_pos != -1:
                start = max(0, anchor_pos - 800)
                end = min(len(disk_content), anchor_pos + matched_len + 800)
                prefix = "... [preceding content omitted]\n" if start > 0 else ""
                suffix = "\n... [following content omitted]" if end < len(disk_content) else ""
                preview = f"{prefix}{disk_content[start:end]}{suffix}"
            else:
                preview = disk_content[:2000] + "\n... [truncated]"

        # Advance recorded hash to current disk content exposed in rejection preview.
        # This breaks the infinite CAS rejection loop and enables 1-turn self-healing
        # without requiring a redundant file_read_tool call.
        bucket[norm] = current

        return (
            f"File '{norm}' has changed on disk since your last read (content hash mismatch).\n"
            f"Current disk content snippet:\n```\n{preview}\n```\n"
            "Rebase your edits directly on this current content without calling file_read_tool."
        )

    def clear_agent(self, agent_id: str) -> None:
        self._agent_read_hashes.pop(agent_id, None)

    def clear(self) -> None:
        self._agent_read_hashes.clear()


_integrity_guards: dict[int, FileIntegrityGuard] = {}


def get_file_integrity_guard(executor: CodeExecutor | None) -> FileIntegrityGuard | None:
    effective_executor = executor
    if effective_executor is None:
        from myrm_agent_harness.toolkits.code_execution.executors.base import (
            get_executor,
        )

        effective_executor = get_executor()

    if effective_executor is None:
        return None
    eid = id(effective_executor)
    if eid not in _integrity_guards:
        _integrity_guards[eid] = FileIntegrityGuard()
    return _integrity_guards[eid]


def raise_if_integrity_rejection(
    guard: FileIntegrityGuard | None,
    path: str,
    *,
    disk_content: str | None = None,
    require_version: bool,
    anchor: str | Sequence[str] | None = None,
) -> None:
    """Raise the read, full-read or version rejection of a mutation of ``path`` as a ToolError."""
    if guard is None:
        return

    read_rejection = guard.require_read_before_write(path)
    if read_rejection is not None:
        raise ToolError(
            message=read_rejection,
            user_hint="Read the file first with file_read_tool before editing.",
        )

    partial_rejection = guard.require_full_read_before_edit(path)
    if partial_rejection is not None:
        raise ToolError(
            message=partial_rejection,
            user_hint="Read the full file with file_read_tool before editing.",
        )

    if require_version and disk_content is not None:
        version_rejection = guard.require_version_match(path, disk_content, anchor=anchor)
        if version_rejection is not None:
            raise ToolError(
                message=version_rejection,
                user_hint="Directly adjust and rebase your edits on the current disk content provided above without calling file_read_tool.",
                error_code="FILE_VERSION_MISMATCH",
                diagnostic_info={"error_category": "version_conflict", "path": path},
                recovery_suggestions=[
                    "Inspect the current disk content snippet in the error message",
                    "Update the old_str in your edits array to match the actual lines on disk",
                    "Call file_edit_tool again directly (do not call file_read_tool)",
                ],
            )


def _common_prefix_len(first: str, second: str) -> int:
    return next(
        (i for i, (a, b) in enumerate(zip(first, second, strict=False)) if a != b), min(len(first), len(second))
    )


def _with_context(line: str, start: int, end: int) -> str:
    """``line[start:end]`` widened to the words it touches, at most ``_CONTEXT_CHARS`` on each side.

    A bare ``***`` or ``...`` is text that code and prose write everywhere, so a fragment that short also takes the
    key before it: ``password: ***``.
    """
    left, right = start, end
    while left > 0 and start - left < _CONTEXT_CHARS and not line[left - 1].isspace():
        left -= 1
    while right < len(line) and right - end < _CONTEXT_CHARS and not line[right].isspace():
        right += 1
    fragment = line[left:right]
    if len(fragment) < _MIN_FRAGMENT_CHARS:
        fragment = line[max(0, left - _CONTEXT_CHARS) : right].strip()
    return fragment


def _mask_fragments(disk_content: str) -> set[str]:
    """The text the redactor puts in place of what ``disk_content`` holds, with the words around each mask.

    A line is cut to the part between its unchanged head and tail, so ``api_key: sk-pro...7890`` yields
    ``sk-pro...7890`` and ``DB_PASSWORD=***`` yields ``DB_PASSWORD=***``. A block the redactor collapses (a private
    key) changes the line count, and its new lines are the fragments.
    """
    view = redact_sensitive_text(disk_content)
    if view == disk_content:
        return set()
    disk_lines, view_lines = disk_content.splitlines(), view.splitlines()
    if len(disk_lines) != len(view_lines):
        return set(view_lines) - set(disk_lines)
    fragments: set[str] = set()
    for disk_line, view_line in zip(disk_lines, view_lines, strict=True):
        if disk_line == view_line:
            continue
        head = _common_prefix_len(disk_line, view_line)
        tail = min(
            _common_prefix_len(disk_line[::-1], view_line[::-1]),
            len(disk_line) - head,
            len(view_line) - head,
        )
        if head < len(view_line) - tail:
            fragments.add(_with_context(view_line, head, len(view_line) - tail))
    return fragments


def raise_if_masked_writeback(path: str, disk_content: str, new_content: str) -> None:
    """Raise when ``new_content`` carries a mask of the redactor that ``disk_content`` of ``path`` does not.

    A read, a search and a command output show a secret as a mask, so text copied from them carries the mask, and a
    write of it replaces the real value on disk. A mask counts when the new content holds more of it than the file.
    """
    if all(new_content.count(mark) <= disk_content.count(mark) for mark in _MASK_MARKS):
        return
    for fragment in _mask_fragments(disk_content):
        if new_content.count(fragment) > disk_content.count(fragment):
            raise ToolError(
                message=(
                    f"The new content of '{os.path.normpath(path)}' contains text that tools show in place of a secret "
                    "(for example '***'), while the file on disk holds the original text there. "
                    "Writing it would replace that text with the mask."
                ),
                user_hint=(
                    "Do not copy masked values from a read into an edit. Change only the lines that show no mask, "
                    "or tell the user to change the secret themselves."
                ),
                error_code="MASKED_VALUE_WRITEBACK",
                diagnostic_info={"error_category": "masked_writeback", "path": path},
                recovery_suggestions=[
                    "Repeat the edit with an old_str that leaves out every line showing a mask",
                    "If the secret itself must change, write the new real value, not the mask",
                ],
            )
