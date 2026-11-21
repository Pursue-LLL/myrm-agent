"""How an artifact row records the workspace file it tracks.

[INPUT]
- os, pathlib (POS: stdlib path resolution)

[OUTPUT]
- to_source_path: the value stored in ``Artifact.source_path`` for a file
- from_source_path: the file a stored ``source_path`` names under a workspace root

[POS]
One encoding for ``Artifact.source_path`` shared by its writer (the chat processor) and the deploy reader. A file
inside the workspace is stored relative to it, so the record survives the workspace being moved; a file outside it
is stored absolute. Either form is read back by the same join, because joining an absolute path onto a root yields
that path.
"""

from __future__ import annotations

import os
from pathlib import Path


def to_source_path(file_path: str, workspace_root: str) -> str:
    """The ``source_path`` of *file_path*: POSIX, relative to *workspace_root* when inside it, else absolute.

    Symlinks and ``..`` are resolved on both sides first, so every spelling of one file stores the same value.
    """
    real = Path(os.path.realpath(file_path))
    try:
        return real.relative_to(os.path.realpath(workspace_root)).as_posix()
    except ValueError:
        return real.as_posix()


def from_source_path(workspace_root: str | Path, source_path: str) -> Path:
    """The file a stored *source_path* names; an absolute *source_path* ignores *workspace_root*."""
    return Path(workspace_root) / source_path
