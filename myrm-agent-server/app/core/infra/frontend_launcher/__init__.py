"""Frontend launcher.

[INPUT]
- .launcher / .checks / .assets / .ports / .common (POS: launcher stages)

[OUTPUT]
- FrontendLauncher, launch_frontend, FrontendEnvironmentError and the node/build checks

[POS]
Aggregate exit of the frontend launcher package; import path unchanged.
"""

from __future__ import annotations

from .assets import ensure_standalone_assets, patch_nextjs_rewrites
from .checks import check_build_artifacts, check_node_environment
from .common import (
    _HEALTH_CHECK_INTERVAL as _HEALTH_CHECK_INTERVAL,
)
from .common import (
    _HEALTH_CHECK_TIMEOUT as _HEALTH_CHECK_TIMEOUT,
)
from .common import (
    _MAX_RESTART_ATTEMPTS as _MAX_RESTART_ATTEMPTS,
)
from .common import (
    _MIN_NODE_VERSION as _MIN_NODE_VERSION,
)
from .common import (
    _TOXIC_NODE_ENV_VARS as _TOXIC_NODE_ENV_VARS,
)
from .common import (
    FrontendEnvironmentError,
)
from .common import (
    _resolve_standalone_dir as _resolve_standalone_dir,
)
from .common import (
    _resolve_standalone_server as _resolve_standalone_server,
)
from .launcher import FrontendLauncher, launch_frontend
from .launcher import _LogPrefixPipe as _LogPrefixPipe
from .ports import _wait_for_health as _wait_for_health
from .ports import find_available_port as find_available_port

__all__ = [
    "FrontendEnvironmentError",
    "FrontendLauncher",
    "check_build_artifacts",
    "check_node_environment",
    "ensure_standalone_assets",
    "launch_frontend",
    "patch_nextjs_rewrites",
]
