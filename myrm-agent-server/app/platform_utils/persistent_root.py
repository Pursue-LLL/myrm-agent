"""Map harness persistent volume paths for local dev without /persistent mount.

[INPUT]
- myrm_agent_harness.runtime.paths.execution_paths (POS: PERSISTENT_ROOT and derived paths)

[OUTPUT]
- configure_persistent_root_for_local_dev() (POS: startup-time path mapper)

[POSITION] app.platform_utils — local dev persistent volume shim.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def configure_persistent_root_for_local_dev(state_dir: str) -> str:
    """Use MYRM_DATA_DIR/harness when /persistent is not mounted (local macOS dev)."""
    default_root = Path("/persistent")
    if default_root.is_dir():
        return str(default_root)

    root = Path(state_dir).expanduser().resolve() / "harness"
    root.mkdir(parents=True, exist_ok=True)
    root_str = str(root)

    import myrm_agent_harness.runtime.paths.execution_paths as execution_paths

    execution_paths.PERSISTENT_ROOT = root_str
    execution_paths.WORKSPACE_ROOT = f"{root_str}/workspace"
    execution_paths.CONTEXT_ROOT = f"{root_str}/.context"
    execution_paths.ARTIFACTS_ROOT = f"{execution_paths.WORKSPACE_ROOT}/artifacts"
    execution_paths.MEMORIES_ROOT = f"{root_str}/.memories"
    execution_paths.SYSTEM_CONFIG_ROOT = f"{execution_paths.CONTEXT_ROOT}/system"
    execution_paths.LEGACY_SYSTEM_CONFIG_ROOT = f"{root_str}/.claude"

    logger.info("[Startup] Local persistent root mapped to %s", root_str)
    return root_str
