"""Directory and file browse API for workspace management.

[INPUT]
- myrm_agent_harness.agent.security.path_security::is_within_boundary
  (POS: Path security — boundary check immune to symlink escape)
- myrm_agent_harness.agent.security.path_security::is_dangerous_path
  (POS: Path security — single source of truth for dangerous paths)
- myrm_agent_harness.agent.security.path_security::is_sensitive_file
  (POS: Path security — sensitive file pattern matching)
- app.core.utils.errors::validation_error (POS: HTTP error helpers)
- app.core.utils.response_utils::success_response (POS: Standard response wrapper)

[OUTPUT]
- GET /browse — Directory-only listing for workspace directory picker
- GET /browse/files — File+directory listing with metadata for workspace file browser
- GET /browse/content — File content read for preview/download (workspace root and/or chat_id boundary)

[POS]
Workspace browse API. Provides read-only directory/file listing and content
retrieval. Used by the frontend WorkspaceDirPicker (dirs only) and
WorkspaceFileBrowser (files+dirs with metadata).
"""

import logging
import mimetypes
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from app.core.utils.errors import validation_error
from app.core.utils.response_utils import success_response

logger = logging.getLogger(__name__)

router = APIRouter()

_MAX_DEPTH = 3
_MAX_ENTRIES = 500
_MAX_CONTENT_SIZE = 1 * 1024 * 1024  # 1MB
_SEARCH_MAX_RESULTS = 20
_SEARCH_MAX_WALK_DEPTH = 6

_IGNORED_DIRS: frozenset[str] = frozenset(
    {
        "node_modules",
        ".git",
        ".next",
        "__pycache__",
        ".venv",
        "venv",
        "dist",
        "build",
        ".cache",
        ".DS_Store",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "egg-info",
        ".eggs",
    }
)

_TEXT_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".txt",
        ".md",
        ".rst",
        ".py",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".ini",
        ".cfg",
        ".conf",
        ".html",
        ".htm",
        ".css",
        ".scss",
        ".less",
        ".xml",
        ".svg",
        ".sh",
        ".bash",
        ".zsh",
        ".fish",
        ".bat",
        ".cmd",
        ".ps1",
        ".sql",
        ".graphql",
        ".gql",
        ".csv",
        ".tsv",
        ".java",
        ".kt",
        ".scala",
        ".go",
        ".rs",
        ".c",
        ".cpp",
        ".h",
        ".hpp",
        ".cs",
        ".rb",
        ".php",
        ".swift",
        ".r",
        ".m",
        ".lua",
        ".pl",
        ".pm",
        ".ex",
        ".exs",
        ".erl",
        ".hs",
        ".clj",
        ".dockerfile",
        ".gitignore",
        ".env.example",
        ".editorconfig",
        ".prettierrc",
        ".eslintrc",
        ".babelrc",
        "Makefile",
        "Dockerfile",
        "Procfile",
        "Gemfile",
        "Rakefile",
    }
)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class DirectoryEntry(BaseModel):
    """Single directory entry returned by the browse endpoint."""

    name: str = Field(..., description="Directory name")
    path: str = Field(..., description="Full absolute path")
    is_dir: bool = Field(True, description="Always true (only dirs returned)")


class BrowseResponse(BaseModel):
    """Response for directory browse."""

    current: str = Field(..., description="Current absolute path")
    parent: str | None = Field(None, description="Parent directory path (null at root)")
    entries: list[DirectoryEntry] = Field(default_factory=list, description="Child directories")


class FileEntry(BaseModel):
    """Single file/directory entry with metadata."""

    name: str
    path: str
    type: str = Field(..., description="'file' or 'directory'")
    size: int | None = Field(None, description="File size in bytes (null for directories)")
    mtime: str | None = Field(None, description="Last modified time ISO 8601")
    children: list["FileEntry"] | None = Field(None, description="Child entries (directories only)")


class FileTreeResponse(BaseModel):
    """Response for file tree browse."""

    root: str = Field(..., description="Root directory path")
    entries: list[FileEntry]
    truncated: bool = Field(False, description="True if entry count hit the limit")


class FileSearchResult(BaseModel):
    """Single file match from fuzzy search."""

    name: str = Field(..., description="File name")
    path: str = Field(..., description="Absolute path")
    relative_path: str = Field(..., description="Path relative to workspace root")
    size: int | None = Field(None, description="File size in bytes")


class FileSearchResponse(BaseModel):
    """Response for file search endpoint."""

    results: list[FileSearchResult]
    total: int = Field(..., description="Number of matches returned")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_within_boundary(target: str, boundary: str) -> bool:
    """Check that *target* is equal to or inside *boundary* directory.

    Delegates to the unified path security module.
    """
    from myrm_agent_harness.agent.security.path_security import is_within_boundary

    return is_within_boundary(target, boundary)


def _is_text_file(filename: str) -> bool:
    """Heuristic check whether a file is likely text-based."""
    name_lower = filename.lower()
    if name_lower in _TEXT_EXTENSIONS:
        return True
    _, ext = os.path.splitext(name_lower)
    return ext in _TEXT_EXTENSIONS


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
                        )
                    )
    except PermissionError:
        pass
    except OSError as e:
        logger.warning("Failed to scan %s: %s", dir_path, e)

    return entries


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


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


@router.get("/browse/content", response_model=None)
async def browse_content(
    path: str = Query(
        ...,
        description="Absolute file path, or path relative to the resolved workspace when using chat_id/workspace",
    ),
    workspace: str | None = Query(None, description="Workspace root boundary (omit when chat_id is provided)"),
    chat_id: str | None = Query(
        None,
        description="Chat id — resolves workspace root via Chat metadata (JIT sandbox bind when unset)",
    ),
    download: bool = Query(False, description="True to trigger download instead of inline preview"),
) -> Response:
    """Read file content for preview or download.

    Restricted to text files within the workspace boundary. Binary files
    and files exceeding the size limit are rejected.

    Either ``workspace`` or ``chat_id`` must be provided so the server can
    establish the allowed root (matches Active Working Memory previews when the
    UI has not yet synced ``workspace_dir`` into client state).
    """
    from myrm_agent_harness.agent.security.path_security import is_dangerous_path, is_sensitive_file

    from app.services.chat.chat_service import ChatService

    workspace_resolved: str | None = None
    if workspace and workspace.strip():
        workspace_resolved = os.path.realpath(os.path.expanduser(workspace.strip()))
    elif chat_id and chat_id.strip():
        meta = await ChatService.get_chat_metadata(chat_id.strip())
        if meta is None:
            raise validation_error("Unknown chat_id")
        ws = meta.workspace_dir or await ChatService.ensure_default_workspace_dir(chat_id.strip())
        if not ws:
            raise validation_error("Could not resolve workspace for chat")
        workspace_resolved = os.path.realpath(os.path.expanduser(ws.strip()))
    else:
        raise validation_error("Either workspace or chat_id is required")

    raw_path = os.path.expanduser(path)
    if os.path.isabs(raw_path):
        resolved = os.path.realpath(raw_path)
    else:
        resolved = os.path.realpath(os.path.join(workspace_resolved, raw_path))

    if is_dangerous_path(resolved):
        raise validation_error(f"Access denied: {path}")

    if not _is_within_boundary(resolved, workspace_resolved):
        raise validation_error("File is outside workspace boundary")

    if is_sensitive_file(resolved):
        raise validation_error("Access denied: sensitive file")

    if not os.path.isfile(resolved):
        raise validation_error(f"Not a file: {path}")

    file_size = os.path.getsize(resolved)
    is_truncated = False
    if file_size > _MAX_CONTENT_SIZE:
        is_truncated = True

    filename = os.path.basename(resolved)
    content_type, _ = mimetypes.guess_type(filename)
    if content_type is None:
        content_type = "text/plain" if _is_text_file(filename) else "application/octet-stream"

    try:
        with open(resolved, "rb") as f:
            if is_truncated:
                content = f.read(_MAX_CONTENT_SIZE)
            else:
                content = f.read()
    except PermissionError:
        raise validation_error(f"Permission denied: {path}") from None
    except OSError as e:
        raise validation_error(f"Cannot read file: {e}") from e

    disposition = "attachment" if download else "inline"
    headers = {
        "Content-Disposition": f'{disposition}; filename="{filename}"',
        "Content-Length": str(len(content)),
    }
    if is_truncated:
        headers["X-Content-Truncated"] = "true"

    return Response(
        content=content,
        media_type=content_type,
        headers=headers,
    )


def fuzzy_score(query_lower: str, target: str) -> float:
    """Calculate a fuzzy match score (0-100) between query and target.

    Higher score is better.
    - 100: Exact match
    - 80-99: Substring match
    - 10-79: Subsequence match
    - 0: No match
    """
    if not query_lower:
        return 100.0

    target = target.lower()

    if query_lower == target:
        return 100.0

    if query_lower in target:
        # Give higher score if it matches the beginning of the target
        base_score = 90.0 if target.startswith(query_lower) else 80.0
        return base_score + (len(query_lower) / len(target)) * 9.0

    # Subsequence match
    q_idx = 0
    t_idx = 0
    q_len = len(query_lower)
    t_len = len(target)

    match_indices = []
    while q_idx < q_len and t_idx < t_len:
        if query_lower[q_idx] == target[t_idx]:
            match_indices.append(t_idx)
            q_idx += 1
        t_idx += 1

    if q_idx < q_len:
        return 0.0  # not a subsequence

    # It is a subsequence. Calculate score based on compactness.
    spread = match_indices[-1] - match_indices[0] + 1
    compactness = len(query_lower) / spread if spread > 0 else 1.0

    return 10.0 + (compactness * 60.0) + (len(query_lower) / len(target)) * 9.0


def _search_files(
    root: str,
    query_lower: str,
    max_results: int,
) -> list[FileSearchResult]:
    """Retrieve workspace files and perform fuzzy scoring."""
    from myrm_agent_harness.agent.security.path_security import is_dangerous_path, is_sensitive_file
    from myrm_agent_harness.utils.workspace_indexer import WorkspaceFileIndexer

    root_real = os.path.realpath(root)
    all_files = WorkspaceFileIndexer.list_all_files(root_real)

    scored_files = []
    for rel_path in all_files:
        fname = os.path.basename(rel_path)
        # Score based on filename
        score = fuzzy_score(query_lower, fname)
        if score <= 0:
            continue

        full_path = os.path.join(root_real, rel_path)
        if is_dangerous_path(full_path) or is_sensitive_file(full_path):
            continue

        scored_files.append((score, fname, full_path, rel_path))

    # Sort by score descending, then by relative path ascending
    scored_files.sort(key=lambda x: (-x[0], x[3]))

    results: list[FileSearchResult] = []
    for _score, fname, full_path, rel_path in scored_files[:max_results]:
        try:
            size = os.path.getsize(full_path)
        except OSError:
            size = None

        results.append(
            FileSearchResult(
                name=fname,
                path=full_path,
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
