"""[INPUT]
- .common (POS: shared router, models and helpers)

[OUTPUT]
- _scan_tree, browse_directory, browse_files

[POS]
Workspace browse API: directory and file listing.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import Query
from fastapi.responses import JSONResponse

from app.core.utils.errors import validation_error
from app.core.utils.response_utils import success_response

from .common import (
    _IGNORED_DIRS,
    _MAX_DEPTH,
    _MAX_ENTRIES,
    BrowseResponse,
    DirectoryEntry,
    FileEntry,
    FileTreeResponse,
    _is_text_file,
    _is_within_boundary,
    logger,
    router,
)


def _scan_tree(
    dir_path: str,
    boundary: str,
    depth: int,
    max_depth: int,
    counter: list[int],
    max_entries: int,
) -> list[FileEntry]:
    """Recursively scan directory tree returning FileEntry list."""
    from myrm_agent_harness.agent.security.path_security import is_dangerous_path, is_sensitive_file

    if counter[0] >= max_entries:
        return []

    entries: list[FileEntry] = []
    try:
        with os.scandir(dir_path) as scanner:
            items = sorted(scanner, key=lambda e: (not e.is_dir(follow_symlinks=False), e.name.lower()))
            for entry in items:
                if counter[0] >= max_entries:
                    break

                if entry.name.startswith("."):
                    continue

                full_path = os.path.realpath(entry.path)

                if is_dangerous_path(full_path):
                    continue
                if not _is_within_boundary(full_path, boundary):
                    continue

                is_dir = entry.is_dir(follow_symlinks=False)

                if is_dir:
                    if entry.name in _IGNORED_DIRS:
                        continue

                    counter[0] += 1
                    children: list[FileEntry] | None = None
                    if depth < max_depth:
                        children = _scan_tree(full_path, boundary, depth + 1, max_depth, counter, max_entries)

                    entries.append(
                        FileEntry(
                            name=entry.name,
                            path=full_path,
                            type="directory",
                            children=children,
                        )
                    )
                else:
                    if is_sensitive_file(full_path):
                        continue

                    counter[0] += 1
                    try:
                        stat = entry.stat(follow_symlinks=False)
                        mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
                        size = stat.st_size
                    except OSError:
                        mtime = None
                        size = None

                    entries.append(
                        FileEntry(
                            name=entry.name,
                            path=full_path,
                            type="file",
                            size=size,
                            mtime=mtime,
                            is_text=_is_text_file(entry.name),
                        )
                    )
    except PermissionError:
        pass
    except OSError as e:
        logger.warning("Failed to scan %s: %s", dir_path, e)

    return entries


@router.get("/browse", response_model=None)
async def browse_directory(
    path: str = Query("~", description="Directory path to browse (supports ~ expansion)"),
) -> JSONResponse:
    """List subdirectories of the given path for workspace selection.

    Only returns directories (not files). Filters out hidden dirs and
    dangerous system paths. Used by the frontend folder picker.
    """
    from myrm_agent_harness.agent.security.path_security import is_dangerous_path

    resolved = os.path.realpath(os.path.expanduser(path))

    if is_dangerous_path(resolved):
        raise validation_error(f"Access denied for path: {path}")

    if not os.path.isdir(resolved):
        raise validation_error(f"Path is not a directory: {path}")

    parent: str | None = None
    parent_candidate = os.path.dirname(resolved)
    if parent_candidate != resolved:
        parent = parent_candidate

    entries: list[DirectoryEntry] = []
    try:
        with os.scandir(resolved) as scanner:
            for entry in sorted(scanner, key=lambda e: e.name.lower()):
                if not entry.is_dir(follow_symlinks=False):
                    continue
                if entry.name.startswith("."):
                    continue
                full_path = os.path.realpath(entry.path)
                if is_dangerous_path(full_path):
                    continue
                entries.append(DirectoryEntry(name=entry.name, path=full_path, is_dir=True))
    except PermissionError:
        raise validation_error(f"Permission denied: {path}") from None
    except OSError as e:
        logger.warning("Failed to scan directory %s: %s", resolved, e)
        raise validation_error(f"Cannot read directory: {path}") from e

    data = BrowseResponse(current=resolved, parent=parent, entries=entries)
    return success_response(data=data.model_dump())


@router.get("/browse/files", response_model=None)
async def browse_files(
    path: str = Query(..., description="Root directory path to browse"),
    depth: int = Query(1, ge=1, le=_MAX_DEPTH, description="Max recursion depth (1-3)"),
) -> JSONResponse:
    """List files and directories with metadata for the workspace file browser.

    Returns a recursive file tree limited by depth and entry count.
    Filters out hidden files, dangerous paths, sensitive files, and
    common build/cache directories.
    """
    from myrm_agent_harness.agent.security.path_security import is_dangerous_path

    resolved = os.path.realpath(os.path.expanduser(path))

    if is_dangerous_path(resolved):
        raise validation_error(f"Access denied for path: {path}")

    if not os.path.isdir(resolved):
        raise validation_error(f"Path is not a directory: {path}")

    counter = [0]
    entries = _scan_tree(resolved, resolved, 1, depth, counter, _MAX_ENTRIES)
    truncated = counter[0] >= _MAX_ENTRIES

    data = FileTreeResponse(root=resolved, entries=entries, truncated=truncated)
    return success_response(data=data.model_dump())
