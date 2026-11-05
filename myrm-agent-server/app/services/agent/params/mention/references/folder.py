"""[INPUT]
- myrm_agent_harness.agent.security.path_security::safe_join_path (POS: workspace-confined path join + dangerous/sensitive checks)
- ..context::MentionContext (POS: per-turn accumulation state)
- ..xml (POS: XML fragment and inline budget primitives)

[OUTPUT]
- _get_folder_tree: bounded workspace folder tree
- workspace_folder_part: @folder handler

[POS]
Folder-tree @ references. The handler keeps every reference either inside the workspace or refused,
and the tree is bounded so one @folder cannot dominate the prompt.
"""

from __future__ import annotations

import logging
import os

from ...models import MentionReferenceRequest
from ..context import MentionContext
from ..xml import _MENTION_MAX_TOTAL_BYTES, _format_size, _xml_error, _xml_metadata, _xml_part

logger = logging.getLogger(__name__)

_FOLDER_TREE_MAX_ENTRIES = 200
_FOLDER_TREE_EXCLUDED_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".pytest_cache",
    ".mypy_cache",
}


def _get_folder_tree(abs_path: str, workspace_dir: str) -> str:
    """Generate folder tree structure (limited to _FOLDER_TREE_MAX_ENTRIES).

    Filters out common excluded directories like .git, node_modules, __pycache__.
    Returns empty string if path doesn't exist or is not a directory.
    """
    if not os.path.exists(abs_path) or not os.path.isdir(abs_path):
        return ""

    lines: list[str] = []
    total_entries = 0

    try:
        for root, dirs, files in os.walk(abs_path):
            dirs[:] = [d for d in dirs if d not in _FOLDER_TREE_EXCLUDED_DIRS]

            rel_root = os.path.relpath(root, workspace_dir)
            if rel_root == ".":
                rel_root = ""

            for d in sorted(dirs):
                if total_entries >= _FOLDER_TREE_MAX_ENTRIES:
                    lines.append("... (truncated)")
                    return "\n".join(lines)
                dir_path = os.path.join(rel_root, d) if rel_root else d
                lines.append(f"- {dir_path}/")
                total_entries += 1

            for f in sorted(files):
                if total_entries >= _FOLDER_TREE_MAX_ENTRIES:
                    lines.append("... (truncated)")
                    return "\n".join(lines)
                if not f.startswith("."):
                    file_path = os.path.join(rel_root, f) if rel_root else f
                    lines.append(f"- {file_path}")
                    total_entries += 1
    except Exception as e:
        logger.warning("Failed to generate folder tree for %s: %s", abs_path, e)
        return ""

    return "\n".join(lines)


async def workspace_folder_part(ref: MentionReferenceRequest, ctx: MentionContext) -> None:
    from myrm_agent_harness.agent.security.path_security import (
        is_dangerous_path,
        is_sensitive_file,
        safe_join_path,
    )

    rel_path = ref.path or "."
    display_path = ref.label or f"@folder:{rel_path}"
    try:
        abs_folder = safe_join_path(ctx.workspace_real, rel_path)
    except ValueError:
        ctx.parts.append(_xml_error(display_path, "path outside workspace"))
        return
    abs_folder_str = str(abs_folder)
    if is_dangerous_path(abs_folder_str) or is_sensitive_file(abs_folder_str):
        ctx.parts.append(_xml_error(display_path, "access denied"))
        return

    tree_content = _get_folder_tree(abs_folder_str, ctx.workspace_real)
    if tree_content:
        tree_bytes = len(tree_content.encode("utf-8"))
        if ctx.total_bytes + tree_bytes <= _MENTION_MAX_TOTAL_BYTES:
            ctx.parts.append(_xml_part(display_path, "folder-tree", tree_content))
            ctx.total_bytes += tree_bytes
        else:
            ctx.parts.append(
                _xml_metadata(
                    display_path,
                    "folder-tree",
                    f"Tree too large ({_format_size(tree_bytes)})",
                )
            )
    else:
        ctx.parts.append(_xml_error(display_path, "folder not found or empty"))
