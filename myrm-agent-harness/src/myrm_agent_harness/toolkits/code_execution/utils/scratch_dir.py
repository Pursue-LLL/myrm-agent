"""Scratch directories of the harness inside a workspace.

[INPUT]
(none — standard library only)

[OUTPUT]
- scratch_dir: ``<workspace>/.myrm/<name>``, where the harness keeps its transient ``name`` files
- ensure_scratch_dir: that directory, created and hidden from git

[POS]
Where the harness puts transient files of its own into a workspace: command scripts and output logs. The workspace
is often a project under version control and the agent can run ``git add -A``, so each directory ignores itself with
a ``.gitignore`` that holds ``*``. Nothing of the user's own ignore rules is touched, and a file the harness never
meant to share (an output log holds whatever its command printed) cannot be committed by accident.
"""

from __future__ import annotations

import contextlib
from pathlib import Path

_ROOT_DIR_NAME = ".myrm"
_IGNORE_FILE_NAME = ".gitignore"
_IGNORE_EVERYTHING = "*\n"


def scratch_dir(work_dir: str | Path, name: str) -> Path:
    """The ``name`` scratch directory of the workspace ``work_dir``; it may not exist yet."""
    return Path(work_dir) / _ROOT_DIR_NAME / name


def ensure_scratch_dir(work_dir: str | Path, name: str) -> Path:
    """Create the ``name`` scratch directory of ``work_dir`` and make git skip everything that lies in it.

    A directory that cannot be created raises ``OSError``. An ignore file that cannot be written does not: the
    files in the directory work without it.
    """
    directory = scratch_dir(work_dir, name)
    directory.mkdir(parents=True, exist_ok=True)
    ignore_file = directory / _IGNORE_FILE_NAME
    if not ignore_file.exists():
        with contextlib.suppress(OSError):
            ignore_file.write_text(_IGNORE_EVERYTHING, encoding="utf-8")
    return directory
