"""Text-path reads for file_read_tool: preview, stream and paged full reads, plus the structure outline.

[INPUT]
- core.file_operation_service::FileOperationService, core.operation_context::OperationContext, OperationType (POS: file operation service)
- core.parked_file_view::is_parked_path, parked_page_chars (POS: page size of context-guard parked text)
- core.result_formatter::clamp_line (POS: per-line clamp)
- file_read.truncation::truncate_file_output (POS: output truncation)
- file_read.outline::extract_file_outline (POS: structure-mode outline)
- streaming::read_file_chunked, read_file_preview (POS: large-file streaming reader)
- utils.vault_read::path_base (POS: strips the ``:range`` suffix from a path)

[OUTPUT]
- process_text_paths: streaming/preview/all text path reads
- read_structure_outline: the symbol or heading outline of one text path (``parse_mode='structure'``)

[POS]
Text read execution for file_read_tool; multimodal.py delegates its text paths and structure outlines here.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from langchain_core.runnables import RunnableConfig

from myrm_agent_harness.agent.config import DEFAULT_FILE_IO_CONFIG

from ...streaming import read_file_chunked, read_file_preview
from ...utils.vault_read import path_base
from ..file_integrity_guard import get_file_integrity_guard
from ..file_operation_service import FileOperationService
from ..operation_context import OperationContext, OperationType
from ..parked_file_view import is_parked_path, parked_page_chars
from ..result_formatter import clamp_line
from .outline import extract_file_outline
from .truncation import truncate_file_output

if TYPE_CHECKING:
    from myrm_agent_harness.backends.skills.types import SkillMetadata
    from myrm_agent_harness.toolkits.code_execution.executors.base import CodeExecutor

logger = logging.getLogger(__name__)

# The outline is read from the whole file, so it reads past the display line cap.
_STRUCTURE_READ_MAX_LINES = 5000
_OUTLINE_MAX_SYMBOLS = 100


async def _dispatch_truncation_event(
    meta: dict[str, object],
    *,
    tool: str,
    config: RunnableConfig,
) -> None:
    from myrm_agent_harness.utils.event_utils import dispatch_custom_event

    await dispatch_custom_event(
        "agent_status",
        {"event": "tool_truncated", "tool": tool, "metadata": meta},
        config=config,
    )


def _clamp_multiline(text: str, max_line_length: int | None) -> str:
    """Apply per-line clamp to raw (non-gutter) text on display only.

    Preview/stream branches bypass ``ResultFormatter``, so clamp each line here
    to keep a minified/wide line from blowing the context budget in any read
    mode. Never touches the file on disk, so read/version hashes stay intact.
    """
    if max_line_length is None or not text:
        return text
    lines = text.split("\n")
    return "\n".join(clamp_line(line, max_line_length) for line in lines)


async def _read_via_service(
    path_str: str,
    executor: CodeExecutor | None,
    skills: list[SkillMetadata] | None,
    reason: str | None,
    *,
    is_dir: bool = False,
    config: RunnableConfig,
    max_lines: int | None = None,
) -> str:
    op_context = OperationContext(
        operation=OperationType.VIEW,
        executor=executor,
        skills=skills or [],
        paths=[path_str],
        reason=reason,
    )
    service = FileOperationService(op_context)
    raw_out = await service.execute()
    if max_lines is None:
        max_lines = DEFAULT_FILE_IO_CONFIG.max_read_lines
    # The continuation hint appends its own ``:<line>-``; the requested range must not ride along (``doc.md:254-:506-``).
    hint_path = path_str if is_dir else path_base(path_str)
    # Text the context guard parked is read in pages sized in o200k tokens, not the code-file character cap.
    parked = not is_dir and is_parked_path(hint_path)
    truncated_text, was_truncated, meta = truncate_file_output(
        raw_out,
        max_chars=parked_page_chars(raw_out) if parked else DEFAULT_FILE_IO_CONFIG.max_read_chars,
        is_dir=is_dir,
        path_str=hint_path,
        max_lines=max_lines,
    )
    if was_truncated:
        await _dispatch_truncation_event(meta, tool="file_read" if not is_dir else "list_dir", config=config)
    return truncated_text


async def read_structure_outline(
    path_str: str,
    executor: CodeExecutor | None,
    skills: list[SkillMetadata] | None,
    reason: str | None,
    *,
    config: RunnableConfig,
) -> str:
    """The symbol or heading outline of one text path, with line ranges."""
    base_path_str = path_base(path_str)
    raw_out = await _read_via_service(
        path_str, executor, skills, reason, config=config, max_lines=_STRUCTURE_READ_MAX_LINES
    )
    outline = extract_file_outline(raw_out, base_path_str, max_symbols=_OUTLINE_MAX_SYMBOLS)
    return outline or f"[DOCUMENT STRUCTURE OUTLINE: {base_path_str}]:\n  (No structural symbols detected)"


async def process_text_paths(
    text_paths: list[str],
    executor: CodeExecutor | None,
    skills: list[SkillMetadata] | None,
    reason: str | None,
    mode: str,
    chunk_size_mb: int,
    *,
    config: RunnableConfig,
    parse_mode: str | None = None,
) -> list[str]:
    """Read plain text paths with preview/stream/all modes and truncation."""
    max_lines = DEFAULT_FILE_IO_CONFIG.max_read_lines
    text_content_parts: list[str] = []

    for path_str in text_paths:
        base_path_str = path_base(path_str)

        if parse_mode == "structure":
            text_content_parts.append(await read_structure_outline(path_str, executor, skills, reason, config=config))
            continue

        if ":" in path_str or not executor:
            text_content_parts.append(
                await _read_via_service(path_str, executor, skills, reason, config=config, max_lines=max_lines)
            )
            continue

        try:
            if base_path_str.startswith("/mcp/"):
                text_content_parts.append(
                    await _read_via_service(path_str, executor, skills, reason, config=config, max_lines=max_lines)
                )
                continue

            workspace_path = Path(base_path_str)
            if not workspace_path.is_absolute():
                cwd = Path(executor.workspace_path) if executor else Path.cwd()
                workspace_path = cwd / workspace_path

            if not workspace_path.exists() or workspace_path.is_dir():
                text_content_parts.append(
                    await _read_via_service(
                        path_str,
                        executor,
                        skills,
                        reason,
                        is_dir=workspace_path.is_dir(),
                        config=config,
                        max_lines=max_lines,
                    )
                )
                continue

            file_size_mb = workspace_path.stat().st_size / (1024 * 1024)
            # preview and stream bypass the page cap and clamp long lines: a parked paste is always read as pages.
            effective_mode = "all" if is_parked_path(base_path_str) else mode
            if file_size_mb > 100 and effective_mode == "all":
                effective_mode = "preview"
                logger.warning(
                    "File %s is %.1fMB (>100MB). Auto-fallback to preview mode to prevent OOM.",
                    base_path_str,
                    file_size_mb,
                )

            if effective_mode == "preview":
                guard = get_file_integrity_guard(executor)
                if guard is not None:
                    guard.record_read_marker(str(workspace_path))
                content = await read_file_preview(workspace_path)
                content = _clamp_multiline(content, DEFAULT_FILE_IO_CONFIG.max_read_line_length)
                text_content_parts.append(f"=== {base_path_str} (preview mode) ===\n{content}")
            elif effective_mode == "stream":
                guard = get_file_integrity_guard(executor)
                if guard is not None:
                    guard.record_read_marker(str(workspace_path))
                content = await read_file_chunked(workspace_path, chunk_size_mb=chunk_size_mb)
                content = _clamp_multiline(content, DEFAULT_FILE_IO_CONFIG.max_read_line_length)
                text_content_parts.append(f"=== {base_path_str} ===\n{content}")
            else:
                text_content_parts.append(
                    await _read_via_service(path_str, executor, skills, reason, config=config, max_lines=max_lines)
                )

        except Exception as e:
            logger.exception("Error processing %s with mode=%s: %s", path_str, mode, e)
            text_content_parts.append(
                await _read_via_service(path_str, executor, skills, reason, config=config, max_lines=max_lines)
            )

    return text_content_parts
