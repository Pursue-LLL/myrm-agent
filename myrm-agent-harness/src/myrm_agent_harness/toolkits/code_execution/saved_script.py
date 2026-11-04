"""Saved scripts: ``python file.py`` read as the workspace file it runs.

A script saved to a file and started as a plain ``python file.py`` runs in a child shell, so the host cannot give it
the per-execution services that inline Python gets (the ``skills`` import hook and the MCP IPC channel). Only code the
host reads itself can be given them. This module recognises the one command shape whose code is fully determined by
a workspace file, ``[cd <workspace root> &&] python[3] <script>.py``, and reads that file. Any other shape (flags,
arguments, pipes, other directories, env prefixes) is left to the shell, where its effects cannot be predicted.

[INPUT]
- utils.workspace_path::WorkspacePathResolver (POS: ``/workspace`` container paths <-> workspace-relative paths)

[OUTPUT]
- MAX_SAVED_SCRIPT_BYTES: Largest script the host reads and embeds.
- SavedScript: Resolved path, argv0 and source of one script; ``launcher`` runs source as ``__main__`` in-process.
- resolve_saved_script: command + workspace root -> SavedScript, or None when the command is not that shape.

[POS]
Command-shape and path-containment rules for routing a saved script into the skill runtime.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from myrm_agent_harness.toolkits.code_execution.utils.workspace_path import WorkspacePathResolver

MAX_SAVED_SCRIPT_BYTES = 256 * 1024
"""Scripts the model writes are a few KiB; the cap bounds the read and the code embedded in the launcher."""

# Path arguments are limited to characters the shell passes through untouched, so what is matched here is exactly
# what the shell would run: no quoting, expansion, globbing or `~`.
_PATH = r"[\w./-]+"
_INVOCATION_RE = re.compile(rf"\s*(?:cd\s+(?P<cd>{_PATH})\s*&&\s*)?python3?\s+(?P<script>{_PATH}\.py)\s*")

_LAUNCHER = """\
import sys
sys.argv = [{argv0!r}]
sys.path.insert(0, {script_dir!r})
exec(compile({source!r}, {path!r}, "exec", dont_inherit=True), {{"__name__": "__main__", "__file__": {path!r}}})
"""


@dataclass(frozen=True, slots=True)
class SavedScript:
    """One workspace script that ``python file.py`` would run."""

    path: Path
    """Absolute, symlinks resolved, inside the workspace root."""
    argv0: str
    """The script argument as typed, which is what ``sys.argv[0]`` holds under ``python file.py``."""
    source: str

    def launcher(self, source: str) -> str:
        """Code that runs ``source`` as this script would run under ``python file.py``.

        ``source`` is a parameter so the caller can run a rewritten form of the script. It is executed in a fresh
        namespace of its own, compiled with the script's filename, so tracebacks name the real file and line and the
        launcher's names never reach the script.
        """
        return _LAUNCHER.format(argv0=self.argv0, script_dir=str(self.path.parent), source=source, path=str(self.path))


def resolve_saved_script(command: str, workspace_root: str | None) -> SavedScript | None:
    """Read the script ``command`` runs, or return None when ``command`` is not a plain script invocation.

    The script must be a regular UTF-8 file of at most ``MAX_SAVED_SCRIPT_BYTES`` that, with symlinks resolved, lies
    inside ``workspace_root``; a ``cd`` prefix must name the workspace root itself.
    """
    if not workspace_root:
        return None
    match = _INVOCATION_RE.fullmatch(command)
    if match is None:
        return None

    root = Path(workspace_root).resolve()
    if match["cd"] is not None and _locate(match["cd"], root) != root:
        return None
    path = _locate(match["script"], root)
    if path is None or not path.is_file():
        return None
    try:
        if path.stat().st_size > MAX_SAVED_SCRIPT_BYTES:
            return None
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    return SavedScript(path=path, argv0=match["script"], source=source)


def _locate(reference: str, root: Path) -> Path | None:
    """Resolve a path as typed, relative to the workspace root, to a real path inside it (else None)."""
    below_container_root = WorkspacePathResolver.container_relative(reference)
    if below_container_root is not None:
        candidate = root / below_container_root
    else:
        candidate = Path(reference) if reference.startswith("/") else root / reference
    try:
        resolved = candidate.resolve()
    except (OSError, RuntimeError):  # an unreadable component or a symlink loop
        return None
    return resolved if resolved == root or root in resolved.parents else None
