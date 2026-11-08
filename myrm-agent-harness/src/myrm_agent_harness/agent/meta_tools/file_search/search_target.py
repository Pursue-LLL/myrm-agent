"""Preflight for the path a file search is aimed at.

[INPUT]
- utils.errors::ToolError (POS: Framework-level error handling: ToolError with the format_for_llm protocol, and ModelOutputValidator)
- path_hint::format_path_not_found_hint, suggest_similar_paths (POS: File-search and file-ops UX helper for mistyped, Unicode-decomposed, or moved workspace paths)

[OUTPUT]
- require_examinable_target: raise a ToolError when the search path is missing or this process is refused access

[POS]
Preflight that names a missing or unreadable search path instead of searching it. It runs in front of both tools and
both search tiers. An entry below the search root that cannot be examined is skipped and the search of the rest
stands; the search path itself has no such fallback. ripgrep ends a run whose root it cannot open with status 2 but
still prints its closing summary event, which passes for an answer, and the Python tier lists nothing, so both tiers
would report "no match" for a search that never looked. Opening the path the way a search does turns that into an
error the caller can act on, as ``file_read_tool`` does for a file it may not read.
"""

from __future__ import annotations

import errno
import os
import stat
from pathlib import Path

from myrm_agent_harness.utils.errors import ToolError

from .path_hint import format_path_not_found_hint, suggest_similar_paths

# What ``os.stat`` answers for a name that resolves to nothing: absent, below a file, a link that loops, or longer than
# the platform allows. EBADF is on the list because ``pathlib`` guards against macOS ``stat`` throwing it. Any other
# failure means the file system did not answer, which is not the same as absent.
_ABSENT_ERRNOS = frozenset({errno.ENOENT, errno.ENOTDIR, errno.EBADF, errno.ELOOP, errno.ENAMETOOLONG})
# Windows reports an invalid name (123) and a link that cannot be resolved (1921) as EINVAL, and ``pathlib`` reads both
# as absent. It reads a drive that is not ready (21) as absent too, but that error is a ``PermissionError``, which is a
# refusal, and it stays one.
_ABSENT_WINERRORS = frozenset({123, 1921})


def _says_absent(error: OSError) -> bool:
    # Only Windows sets ``winerror``.
    return error.errno in _ABSENT_ERRNOS or getattr(error, "winerror", None) in _ABSENT_WINERRORS


def _examine_as_a_search_does(target: Path, *, reads_a_file: bool) -> bool:
    """Return whether ``target`` exists, after opening it the way a search will: list and enter it, or read it.

    A directory needs both permissions: without the search permission its names can be listed and none of its
    entries examined. A regular file is opened only for a search that reads it (``reads_a_file``); one that lists
    directories rejects a file whatever its permissions. Any other kind of entry (a pipe, a device) is left alone:
    opening it can block or act on the device. The answer is read from the errors of ``os.stat`` itself because
    ``Path.exists`` raises for an over-long path on Python 3.13 and, from Python 3.14 on, answers False for every
    failure, permission included. A name that cannot exist (a missing entry, a name below a file, a link that loops, a
    NUL byte, a name or path longer than the platform allows) means there is nothing to examine. Any other failure is
    the file system not answering, not an absent entry: it propagates as the error it is.
    """
    try:
        mode = os.stat(target).st_mode
    except ValueError:  # a NUL byte
        return False
    except OSError as error:
        if _says_absent(error):
            return False
        raise
    if stat.S_ISDIR(mode):
        os.scandir(target).close()  # listing the names needs read permission
        os.stat(os.path.join(target, "."))  # examining an entry needs search permission
    elif reads_a_file and stat.S_ISREG(mode):
        with open(target, "rb"):
            pass
    return True


def require_examinable_target(resolved_path: str, requested_path: str, *, reads_a_file: bool) -> None:
    """Raise ``ToolError`` when the path a search is aimed at is missing or this process is refused access.

    ``resolved_path`` is what the executor made of ``requested_path``; the errors name the path as the caller wrote it.
    A file system that does not answer (an I/O error, a stale or dropped mount) is not an absent path: its ``OSError``
    propagates.
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
