"""[INPUT]
- .common (POS: shared router, models and helpers)

[OUTPUT]
- _search_files, search_files

[POS]
Workspace browse API: file-name fuzzy search.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import Query
from fastapi.responses import JSONResponse

from app.core.utils.errors import validation_error
from app.core.utils.response_utils import success_response

from .common import (
    _SEARCH_MAX_RESULTS,
    FileSearchResponse,
    FileSearchResult,
    router,
)


def _search_files(
    root: str,
    query_lower: str,
    max_results: int,
) -> list[FileSearchResult]:
    """Retrieve workspace files and perform fuzzy scoring."""
    from myrm_agent_harness.core.security.path import is_dangerous_path, is_sensitive_file
    from myrm_agent_harness.toolkits.filesystem_suggest import WorkspacePathIndexer, rank_basename

    root_path = Path(root).expanduser().resolve()
    all_files = WorkspacePathIndexer.list_files(root_path)

    scored_files: list[tuple[int, str, Path, str]] = []
    for rel_path in all_files:
        fname = os.path.basename(rel_path)
        rank = rank_basename(fname, query_lower)
        if rank is None:
            continue
        _tier, score, _ranges = rank

        full_path = root_path / rel_path
        if is_dangerous_path(str(full_path)) or is_sensitive_file(str(full_path)):
            continue

        scored_files.append((score, fname, full_path, rel_path))

    scored_files.sort(key=lambda item: (-item[0], item[3]))

    results: list[FileSearchResult] = []
    for _score, fname, full_path, rel_path in scored_files[:max_results]:
        try:
            size = full_path.stat().st_size
        except OSError:
            size = None

        results.append(
            FileSearchResult(
                name=fname,
                path=str(full_path),
                relative_path=rel_path,
                size=size,
            )
        )

    return results


@router.get("/browse/search", response_model=None)
async def search_files(
    q: str = Query("", description="Fuzzy search query (matches against file names)"),
    workspace: str = Query(..., description="Workspace root directory"),
    limit: int = Query(_SEARCH_MAX_RESULTS, ge=1, le=50, description="Max results"),
) -> JSONResponse:
    """Search for files by name within a workspace directory.

    Used by the frontend @-file mention autocomplete in the chat input.
    Returns file names, absolute paths, and relative paths.
    Filters out hidden files, dangerous paths, and sensitive files.
    """
    from myrm_agent_harness.agent.security.path_security import is_dangerous_path

    resolved = os.path.realpath(os.path.expanduser(workspace))

    if is_dangerous_path(resolved):
        raise validation_error(f"Access denied for path: {workspace}")

    if not os.path.isdir(resolved):
        raise validation_error(f"Path is not a directory: {workspace}")

    query_lower = q.strip().lower()
    results = _search_files(resolved, query_lower, limit)

    data = FileSearchResponse(results=results, total=len(results))
    return success_response(data=data.model_dump())
