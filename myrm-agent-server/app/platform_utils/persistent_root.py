"""Point the harness at a local persistent volume when /persistent is not mounted.

[INPUT]
- myrm_agent_harness.runtime.paths.execution_paths (POS: PERSISTENT_ROOT_ENV and get_persistent_root)

[OUTPUT]
- configure_persistent_root_for_local_dev() (POS: startup-time persistent root selector)

[POSITION] app.platform_utils — local dev persistent volume shim.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from myrm_agent_harness.runtime.paths.execution_paths import PERSISTENT_ROOT_ENV, get_persistent_root

logger = logging.getLogger(__name__)


def configure_persistent_root_for_local_dev(state_dir: str) -> str:
    """Use MYRM_DATA_DIR/harness when /persistent is not mounted (local macOS dev).

    A root the deployment already set through ``MYRM_PERSISTENT_ROOT`` is left alone. Returns the
    persistent root the harness resolves to afterwards.
    """
    if not os.environ.get(PERSISTENT_ROOT_ENV, "").strip() and not Path("/persistent").is_dir():
        root = Path(state_dir).expanduser().resolve() / "harness"
        root.mkdir(parents=True, exist_ok=True)
        os.environ[PERSISTENT_ROOT_ENV] = str(root)
        logger.info("[Startup] Local persistent root mapped to %s", root)

    return get_persistent_root()
