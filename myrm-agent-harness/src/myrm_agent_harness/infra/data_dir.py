"""Single resolver for the directory that holds all Myrm-owned persistent state.

Every on-disk location Myrm owns (caches, indexes, snapshots, user skills, ...) hangs off one root,
so a process pointed at its own root with ``MYRM_DATA_DIR`` cannot read or write another process's
data. A path built from ``Path.home() / ".myrm"`` bypasses that root: an isolated test runtime then
reads and writes the real user's directory. ``tests/architecture/test_state_paths_follow_data_dir.py``
rejects such paths.

Usage::

    from myrm_agent_harness.infra.data_dir import resolve_data_dir  # inside the harness
    from myrm_agent_harness.api import resolve_data_dir  # server and other consumers

    cache_file = resolve_data_dir() / "cache" / "index.json"

[INPUT]
- MYRM_DATA_DIR (optional env): state root, ``~`` expanded; default ``~/.myrm``

[OUTPUT]
- DATA_DIR_ENV: Name of the environment variable that relocates the state root.
- resolve_data_dir: The state root for this process (not created, not resolved through symlinks).
- resolve_workspace_state_dir: The state root for data that persists with a cloud sandbox workspace.

[POS]
Single entry point for the Myrm state root; harness and server code derive every state path from it.
"""

import os
from pathlib import Path

DATA_DIR_ENV = "MYRM_DATA_DIR"
_DEFAULT_DIR_NAME = ".myrm"
_SANDBOX_WORKSPACE = "/workspace/"
_SANDBOX_STATE_DIR = Path("/workspace/.myrm")


def resolve_data_dir() -> Path:
    """Return the state root: ``$MYRM_DATA_DIR`` when set, otherwise ``~/.myrm``."""
    raw = os.environ.get(DATA_DIR_ENV, "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / _DEFAULT_DIR_NAME


def resolve_workspace_state_dir() -> Path:
    """Return the state root for data that must live with a cloud sandbox's workspace volume.

    Precedence: an explicit ``MYRM_DATA_DIR``, then ``/workspace/.myrm`` inside a sandbox, then ``~/.myrm``.
    """
    if os.environ.get(DATA_DIR_ENV, "").strip() or not os.path.exists(_SANDBOX_WORKSPACE):
        return resolve_data_dir()
    return _SANDBOX_STATE_DIR
