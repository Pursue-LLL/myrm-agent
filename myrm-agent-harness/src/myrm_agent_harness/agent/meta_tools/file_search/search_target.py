"""Preflight for the path a file search is aimed at.

[INPUT]
- utils.errors::ToolError (POS: Framework-level error handling: ToolError with the format_for_llm protocol, and ModelOutputValidator)
- path_hint::format_path_not_found_hint, suggest_similar_paths (POS: File-search and file-ops UX helper for mistyped, Unicode-decomposed, or moved workspace paths)

[OUTPUT]
- require_examinable_target: raise a ToolError unless the search path exists and this process can open it

[POS]
Preflight that names a missing or unreadable search path instead of searching it. It runs in front of both tools and
both search tiers. An entry below the search root that cannot be examined is skipped and the search of the rest
stands; the search path itself has no such fallback. ripgrep ends a run whose root it cannot open with status 2 but
still prints its closing summary event, which passes for an answer, and the Python tier lists nothing, so both tiers
would report "no match" for a search that never looked. Opening the path the way a search does turns that into an
error the caller can act on, as ``file_read_tool`` does for a file it may not read.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

from myrm_agent_harness.utils.errors import ToolError

from .path_hint import format_path_not_found_hint, suggest_similar_paths


def _examine_as_a_search_does(target: Path, *, reads_a_file: bool) -> bool:
    """Return whether ``target`` exists, after opening it the way a search will: list and enter it, or read it.

    A directory needs both permissions: without the search permission its names can be listed and none of its
    entries examined. A regular file is opened only for a search that reads it (``reads_a_file``); one that lists
    directories rejects a file whatever its permissions. Any other kind of entry (a pipe, a device) is left alone:
    opening it can block or act on the device. Permission is read from ``os.stat`` because ``Path.exists``
    answers False for it from Python 3.14 on; any other failure of ``os.stat`` (a missing entry, a name with a NUL
    byte) is left to ``Path.exists``, which decides what counts as not found.
    """
    try:
        mode = os.stat(target).st_mode
    except PermissionError:
        raise
    except (OSError, ValueError):
        return target.exists()
    if stat.S_ISDIR(mode):
        os.scandir(target).close()  # listing the names needs read permission
        os.stat(os.path.join(target, "."))  # examining an entry needs search permission
    elif reads_a_file and stat.S_ISREG(mode):
        with open(target, "rb"):
            pass
    return True


def require_examinable_target(resolved_path: str, requested_path: str, *, reads_a_file: bool) -> None:
    """Raise ``ToolError`` when the path a search is aimed at is missing or cannot be opened.

    ``resolved_path`` is what the executor made of ``requested_path``; the errors name the path as the caller wrote it.
    """
    try:
        found = _examine_as_a_search_does(Path(resolved_path), reads_a_file=reads_a_file)
    except PermissionError as e:
        raise ToolError(
            message=f"Permission denied: cannot read {requested_path}",
            user_hint=(
                f"The operating system refused access to this path ({e.strerror or 'no reason given'}). "
                "Search another path, or ask the user to grant access (file permissions, or an operating-system "
                "privacy setting)."
            ),
        ) from e
    if not found:
        raise ToolError(
            message=f"Path not found: {requested_path}",
            user_hint=format_path_not_found_hint(requested_path, suggest_similar_paths(resolved_path)),
        )
