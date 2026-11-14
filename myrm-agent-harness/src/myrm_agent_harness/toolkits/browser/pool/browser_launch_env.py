"""Environment handed to the browser processes the launcher starts.

[INPUT]
- myrm_agent_harness.core.security.process_env::sanitize_env (POS: host environment secret filter)
- ..process_owner::owner_stamp_env (POS: ownership stamp naming the launching process)
- .driver_leftovers::DRIVER_ENV_VAR (POS: variable carrying the token of the driver that starts the browser)

[OUTPUT]
- chromium_launch_env: sanitized host environment plus the ownership stamp and the driver token, for Patchright Chromium
- camoufox_launch_env: sanitized host environment plus the fingerprint keys, for Camoufox

[POS]
Single place where a launched browser's environment is built, so no engine inherits the host's
secrets by accident and the Chromium process always carries the stamp the orphan check reads and the
token that names it among the browsers of one driver.
"""

from __future__ import annotations

import os

from ..process_owner import owner_stamp_env
from .driver_leftovers import DRIVER_ENV_VAR


def chromium_launch_env(driver_token: str) -> dict[str, str]:
    """Host environment without secrets, stamped with the launching process as the owner and the starting driver."""
    from myrm_agent_harness.core.security.process_env import sanitize_env

    return {**sanitize_env(os.environ.copy()), **owner_stamp_env(), DRIVER_ENV_VAR: driver_token}


def camoufox_launch_env(fingerprint_env: object | None) -> dict[str, str]:
    """Host environment without secrets, overlaid with the string-valued fingerprint keys."""
    from myrm_agent_harness.core.security.process_env import sanitize_env

    merged = sanitize_env(os.environ.copy())
    if isinstance(fingerprint_env, dict):
        for key, value in fingerprint_env.items():
            if isinstance(key, str) and isinstance(value, str):
                merged[key] = value
    return merged
