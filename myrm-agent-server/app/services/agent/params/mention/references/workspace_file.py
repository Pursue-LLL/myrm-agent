"""[INPUT]
- myrm_agent_harness.agent.security.path_security (POS: workspace-confined path join + dangerous/sensitive checks)
- ..context::MentionContext (POS: per-turn accumulation state)
- ..documents::_parse_document / _DOCUMENT_EXTENSIONS / _BINARY_EXTENSIONS (POS: Office parsing + file classification)
- ..xml (POS: XML fragment and inline budget primitives)

[OUTPUT]
- _read_file_lines: read a line range from a file
- _workspace_file_part: render one workspace file as a mention fragment
- workspace_file_part: @file handler

[POS]
Workspace-file @ references. The handler refuses paths outside the workspace and sensitive files
before reading a single byte, and never lets one file exceed the inline budget.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from ...models import MentionReferenceRequest
from ..context import MentionContext
from ..documents import _BINARY_EXTENSIONS, _DOCUMENT_EXTENSIONS, _parse_document
from ..xml import _can_inline, _format_size, _xml_error, _xml_metadata, _xml_part

logger = logging.getLogger(__name__)


def _read_file_lines(file_path: str, start_line: int | None, end_line: int | None) -> str:
    """Read specific lines from a file.

    Args:
        file_path: Absolute path to the file
        start_line: Starting line number (1-indexed), None for full file
        end_line: Ending line number (1-indexed, inclusive), None for full file

    Returns:
        File content or specified line range
    """
    with open(file_path, encoding="utf-8", errors="replace") as f:
        if start_line is None:
            return f.read()

        lines = f.readlines()
        total_lines = len(lines)

        start_idx = max(0, start_line - 1)
        end_idx = min(total_lines, end_line) if end_line else total_lines

        return "".join(lines[start_idx:end_idx])


def _workspace_file_part(
    abs_path: str,
    display_path: str,
    start_line: int | None,
    end_line: int | None,
    current_total_bytes: int,
) -> tuple[str, int]:
    from myrm_agent_harness.agent.security.path_security import (
        is_dangerous_path,
        is_sensitive_file,
    )

    if is_dangerous_path(abs_path) or is_sensitive_file(abs_path):
        return _xml_error(display_path, "access denied"), 0
    if not os.path.isfile(abs_path):
        return _xml_error(display_path, "file not found"), 0

    ext = Path(abs_path).suffix.lower()
    try:
        file_size = os.path.getsize(abs_path)
    except OSError:
        file_size = 0

    if ext in _BINARY_EXTENSIONS:
        return (
            _xml_metadata(
                display_path,
                "binary",
                f"Binary file ({_format_size(file_size)}), use file_read_tool to inspect if needed.",
            ),
            0,
        )

    if ext in _DOCUMENT_EXTENSIONS:
        if start_line is not None:
            return (
                _xml_error(display_path, "line range not supported for Office documents"),
                0,
            )
        content = _parse_document(abs_path, ext)
        if content:
            content_bytes = len(content.encode("utf-8"))
            if _can_inline(content_bytes, current_total_bytes):
                return _xml_part(display_path, "document", content), content_bytes
            return (
                _xml_metadata(
                    display_path,
                    "document",
                    f"Document too large ({_format_size(content_bytes)}), use file_read_tool to inspect if needed.",
                ),
                0,
            )
        return (
            _xml_metadata(
                display_path,
                "document",
                f"No extractable text ({_format_size(file_size)}), use file_read_tool to inspect if needed.",
            ),
            0,
        )

    try:
        content = _read_file_lines(abs_path, start_line, end_line)
    except Exception as exc:
        logger.warning("Failed to read mentioned file %s: %s", display_path, exc)
        return _xml_error(display_path, "read failed"), 0

    content_bytes = len(content.encode("utf-8"))
    if _can_inline(content_bytes, current_total_bytes):
        line_range = f" lines {start_line}-{end_line or start_line}" if start_line else ""
        return _xml_part(display_path, f"text{line_range}", content), content_bytes
    return (
        _xml_metadata(
            display_path,
            "text",
            f"Content too large to inline ({_format_size(content_bytes)})",
        ),
        0,
    )


async def workspace_file_part(ref: MentionReferenceRequest, ctx: MentionContext) -> None:
    from myrm_agent_harness.agent.security.path_security import safe_join_path

    rel_path = ref.path
    if not rel_path:
        ctx.parts.append(_xml_error(ref.label or "@file", "missing path"))
        return
    try:
        abs_path = safe_join_path(ctx.workspace_real, rel_path)
    except ValueError:
        ctx.parts.append(_xml_error(ref.label or rel_path, "path outside workspace"))
        return
    display_path = ref.label or rel_path
    part, consumed_bytes = _workspace_file_part(
        str(abs_path),
        display_path,
        ref.start_line,
        ref.end_line,
        ctx.total_bytes,
    )
    ctx.parts.append(part)
    ctx.total_bytes += consumed_bytes
