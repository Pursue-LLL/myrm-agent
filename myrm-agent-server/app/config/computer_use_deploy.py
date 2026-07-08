"""Deploy-mode gates for computer_use (Semantic Desktop Control).

[INPUT] app.config.deploy_mode::is_local_mode, is_sandbox (POS: LOCAL vs SANDBOX deploy gate)
[INPUT] app.platform_utils.sandbox.entitlements::fetch_sandbox_entitlements (POS: VNC entitlement probe)
[OUTPUT] is_computer_use_deploy_supported: whether computer_use may mount for current deploy stack
[OUTPUT] is_visual_desktop_enabled: VISUAL_DESKTOP=1 sandbox desktop stack flag
[POS] Deploy-mode gates for computer_use. Local/Tauri controls native OS; sandbox requires VISUAL_DESKTOP + VNC entitlement.

Local/Tauri: controls the user's native OS desktop.
Sandbox: controls the sandbox VM virtual desktop (VISUAL_DESKTOP=1 + VNC entitlement).
"""

from __future__ import annotations

import logging
import os
import time

from app.config.deploy_mode import is_local_mode, is_sandbox

logger = logging.getLogger(__name__)

_VNC_ENTITLEMENT_CACHE_TTL_SEC = 30.0
_vnc_entitlement_cache: tuple[float, bool] | None = None


def is_visual_desktop_enabled() -> bool:
    """True when the sandbox entrypoint started Xvfb/VNC (DISPLAY=:99)."""
    return os.getenv("VISUAL_DESKTOP", "").strip() == "1"


def is_computer_use_infrastructure_ready() -> bool:
    """Cheap gate: sandbox needs VISUAL_DESKTOP stack; local always ready."""
    if is_local_mode():
        return True
    if is_sandbox():
        return is_visual_desktop_enabled()
    return True


def is_computer_use_deploy_supported() -> bool:
    """Whether this deployment can run desktop control tools (infra + VNC entitlement)."""
    if not is_computer_use_infrastructure_ready():
        return False
    if is_local_mode() or not is_sandbox():
        return True
    return _sandbox_vnc_entitlement_granted()


def _sandbox_vnc_entitlement_granted() -> bool:
    global _vnc_entitlement_cache  # noqa: PLW0603

    now = time.monotonic()
    if _vnc_entitlement_cache is not None:
        cached_at, cached_value = _vnc_entitlement_cache
        if now - cached_at < _VNC_ENTITLEMENT_CACHE_TTL_SEC:
            return cached_value

    from app.platform_utils.deployment_capabilities import get_deployment_capabilities

    if not get_deployment_capabilities().uses_cp_entitlements:
        result = is_visual_desktop_enabled()
    else:
        try:
            from app.platform_utils.sandbox.entitlements.entitlement_guard import fetch_sandbox_entitlements

            entitlements = fetch_sandbox_entitlements()
            if entitlements is None:
                result = False
            else:
                result = entitlements.enable_vnc
        except Exception as exc:
            logger.warning("VNC entitlement check failed (disabling computer_use): %s", exc)
            result = False

    _vnc_entitlement_cache = (now, result)
    return result


def clear_vnc_entitlement_cache() -> None:
    """Clear cached VNC entitlement (tests only)."""
    global _vnc_entitlement_cache  # noqa: PLW0603
    _vnc_entitlement_cache = None


__all__ = [
    "clear_vnc_entitlement_cache",
    "is_computer_use_deploy_supported",
    "is_computer_use_infrastructure_ready",
    "is_visual_desktop_enabled",
]
