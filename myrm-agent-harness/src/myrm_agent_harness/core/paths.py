"""Persistent-volume root primitives shared across layers.

The deployment layer relocates the persistent volume by setting ``MYRM_PERSISTENT_ROOT``;
everything else derives its directory from the root this module reports. Both ``runtime/``
and ``toolkits/`` need the root, and ``toolkits/`` may not import ``runtime/`` (see
``toolkits/_ARCH.md``), so the primitives live here in the foundation layer and
``runtime.paths.execution_paths`` re-exports them.

[INPUT]
- MYRM_PERSISTENT_ROOT (optional infra env): persistent volume root; default /persistent

[OUTPUT]
- PERSISTENT_ROOT_ENV: Name of the environment variable that relocates the persistent volume root.
- DEFAULT_PERSISTENT_ROOT: The volume root used when the environment variable is unset.
- get_persistent_root: The persistent volume root currently in effect.
- get_workspace_root: The workspace root under the persistent volume.
- get_context_root: The context offload root currently in effect.
- get_memories_root: The memory storage root under the persistent volume.

[POS]
Foundation-layer path roots. Read on every call so a root configured after import is honoured
by every caller; never snapshot the value into a constant.
"""

from __future__ import annotations

import os

# Environment variable the deployment layer sets when the volume is not mounted at /persistent.
PERSISTENT_ROOT_ENV = "MYRM_PERSISTENT_ROOT"

DEFAULT_PERSISTENT_ROOT = "/persistent"


def get_persistent_root() -> str:
    """Return the persistent volume root currently in effect.

    A blank value and a bare ``/`` count as unset.
    """
    configured = os.environ.get(PERSISTENT_ROOT_ENV, "").strip().rstrip("/")
    return configured or DEFAULT_PERSISTENT_ROOT


def get_workspace_root() -> str:
    """Return the workspace root (user files, projects, artifacts)."""
    return f"{get_persistent_root()}/workspace"


def get_context_root() -> str:
    """Return the context offload root (compressed tool outputs, scratchpad)."""
    return f"{get_persistent_root()}/.context"


def get_memories_root() -> str:
    """Return the memory storage root."""
    return f"{get_persistent_root()}/.memories"
