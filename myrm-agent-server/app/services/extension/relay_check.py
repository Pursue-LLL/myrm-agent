"""Browser Doctor check for the browser extension CDP relay.

Reads the live extension bridge in-process: the same state ``GET /extension/setup-hints`` reports.

[INPUT]
- app.services.extension.bridge::get_extension_bridge (POS: connection, access policy and relay state)
- app.config.deploy_mode::is_webui_remote_mode / app.config.settings::settings (POS: whether an extension auth token is required and set)
- myrm_agent_harness.toolkits.browser.doctor::CheckStatus/DoctorCheckResult (POS: doctor report contract)

[OUTPUT]
- check_extension_relay: one DoctorCheckResult named ``extension_relay``

[POS]
Server business layer. Adapter between the extension bridge and the harness Doctor report. The relay
belongs to this server, so the doctor endpoint passes the check to ``run_doctor`` as an extra check
and the framework needs no knowledge of this server's routes.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.toolkits.browser.doctor import CheckStatus, DoctorCheckResult

from app.config.deploy_mode import is_webui_remote_mode
from app.config.settings import settings
from app.services.extension.bridge import get_extension_bridge

logger = logging.getLogger(__name__)

_CHECK_NAME = "extension_relay"


def _warning(message: str, fix: str, *, optional: bool = False) -> DoctorCheckResult:
    return DoctorCheckResult(
        name=_CHECK_NAME,
        status=CheckStatus.WARNING,
        message=message,
        fix=fix,
        details={"optional": True} if optional else None,
    )


async def check_extension_relay() -> DoctorCheckResult:
    """Report whether the extension CDP relay can drive the user's signed-in browser.

    An extension that is simply not set up is an optional capability. A problem the user caused or can
    fix on a connected extension (no authorized sites, missing server token) is a real warning.
    """
    bridge = get_extension_bridge()
    try:
        if await bridge.relay_cdp_ready():
            return DoctorCheckResult(
                name=_CHECK_NAME,
                status=CheckStatus.OK,
                message="Extension CDP relay is ready for login-state automation",
            )
        connected = bridge.is_connected()
        policy_valid = bridge.is_access_policy_valid()
    except Exception as exc:
        logger.warning("Extension relay probe failed", exc_info=True)
        return _warning(
            f"Extension relay probe failed: {exc}",
            "Check server logs and extension connection settings",
        )

    if is_webui_remote_mode() and not settings.extension_auth_token.get_secret_value():
        return _warning(
            "Extension auth token missing on server",
            "Set EXTENSION_AUTH_TOKEN on the server, then pair the extension from WebUI",
        )
    if connected and not policy_valid:
        return _warning(
            "Extension is connected but its access policy is not configured",
            "Add authorized domains or enable allow-all in Settings → Browser Extension",
        )
    return _warning(
        "Browser extension is not connected or CDP relay is not ready",
        "Install the MV3 extension, generate a pairing code in WebUI, and connect",
        optional=True,
    )
