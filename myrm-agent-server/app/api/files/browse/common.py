"""[INPUT]
- fastapi.APIRouter (POS: 路由容器)

[OUTPUT]
- router / logger / constants / response models / shared path helpers

[POS]
Shared primitives of the workspace browse API.
"""

from __future__ import annotations

import logging
import os
from urllib.parse import quote

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter()
logger = logging.getLogger(__name__)


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
    is_text: bool | None = Field(
        None,
        description="True for text files, False for binary files (null for directories)",
    )
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


def _content_disposition(disposition: str, filename: str) -> str:
    """Build a header-safe Content-Disposition value.

    Strips CR/LF (header injection) and escapes quotes for the ASCII fallback
    while RFC 5987 ``filename*`` carries the original bytes (non-ASCII names).
    """
    cleaned = filename.replace("\r", "").replace("\n", "")
    ascii_name = cleaned.encode("ascii", "ignore").decode("ascii")
    if not ascii_name:
        ascii_name = "file"
    safe = ascii_name.replace("\\", "\\\\").replace('"', '\\"')
    encoded = quote(cleaned.encode("utf-8"))
    return f"{disposition}; filename=\"{safe}\"; filename*=UTF-8''{encoded}"
