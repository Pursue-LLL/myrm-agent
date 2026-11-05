"""[INPUT]
- ..context::MentionContext (POS: per-turn accumulation state)
- ..xml (POS: XML fragment and inline budget primitives)

[OUTPUT]
- _build_codebase_overview: bounded workspace file/extension scan
- _codebase_overview_part: render the overview fragment
- codebase_part: @codebase handler

[POS]
Codebase @ references. Deliberately index-free: a bounded os.walk keeps the turn cheap and points
the agent at the grep/glob meta tools instead of duplicating a code index.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from ...models import MentionReferenceRequest
from ..context import MentionContext
from ..xml import _can_inline, _xml_metadata, _xml_part

logger = logging.getLogger(__name__)

_CODEBASE_SCAN_EXCLUDED_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".pytest_cache",
    ".mypy_cache",
    ".myrm",
    "dist",
    "build",
    ".next",
    "target",
    "coverage",
}
_CODEBASE_SCAN_MAX_FILES = 10_000


def _build_codebase_overview(workspace_path: Path) -> str:
    """Lightweight workspace scan for @codebase mention (no index DB)."""
    file_count = 0
    ext_counts: dict[str, int] = {}
    truncated = False

    for _dirpath, dirnames, filenames in os.walk(workspace_path):
        dirnames[:] = [name for name in dirnames if name not in _CODEBASE_SCAN_EXCLUDED_DIRS and not name.startswith(".")]
        for filename in filenames:
            if filename.startswith("."):
                continue
            file_count += 1
            ext = Path(filename).suffix.lower() or "(no ext)"
            ext_counts[ext] = ext_counts.get(ext, 0) + 1
            if file_count >= _CODEBASE_SCAN_MAX_FILES:
                truncated = True
                break
        if truncated:
            break

    overview_parts = [f"Codebase Overview: {file_count} files"]
    if truncated:
        overview_parts.append(f"(scan capped at {_CODEBASE_SCAN_MAX_FILES} files)")
    if ext_counts:
        ext_summary = ", ".join(
            f"{ext}: {count}" for ext, count in sorted(ext_counts.items(), key=lambda item: (-item[1], item[0]))[:10]
        )
        overview_parts.append(f"Extensions: {ext_summary}")
    overview_parts.append("Use grep_tool / glob_tool for code exploration.")
    return "\n".join(overview_parts)


async def _codebase_overview_part(workspace_dir: str, current_total_bytes: int) -> tuple[str, int]:
    """Build a lightweight codebase overview for @codebase mention."""
    workspace_path = Path(workspace_dir)
    if not workspace_path.is_dir():
        return (
            _xml_metadata("@codebase", "codebase-overview", "Workspace unavailable"),
            0,
        )

    overview = await asyncio.to_thread(_build_codebase_overview, workspace_path)
    overview_bytes = len(overview.encode("utf-8"))
    if _can_inline(overview_bytes, current_total_bytes):
        return _xml_part("@codebase", "codebase-overview", overview), overview_bytes
    return (
        _xml_metadata("@codebase", "codebase-overview", overview.split("\n", maxsplit=1)[0]),
        0,
    )


async def codebase_part(ref: MentionReferenceRequest, ctx: MentionContext) -> None:
    codebase_part_content, codebase_bytes = await _codebase_overview_part(ctx.workspace_real, ctx.total_bytes)
    ctx.parts.append(codebase_part_content)
    ctx.total_bytes += codebase_bytes
