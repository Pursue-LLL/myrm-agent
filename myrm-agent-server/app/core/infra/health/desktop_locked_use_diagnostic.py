"""[INPUT]
- app.services.locked_use.curtain_bridge (POS: curtain bridge + lease bit + shell liveness)
- myrm_agent_harness.toolkits.computer_use.capture_exclusion (POS: host overlay title injection)

[OUTPUT]
- DesktopLockedUseDiagnostic: Locked Use / Privacy Curtain / capture-exclusion readiness probe

[POS]
Server-layer health probe for `/health/doctor` — surfaces misconfiguration before unattended CU runs fail silently.
"""

from __future__ import annotations

import platform

from myrm_agent_harness.observability.diagnostics.protocols import DiagnosticProtocol, HealthReport


class DesktopLockedUseDiagnostic(DiagnosticProtocol):
    """Readiness of Locked Use, curtain state bridge, and capture-exclusion contract."""

    async def check_health(self) -> HealthReport:
        from app.services.locked_use.curtain_bridge import (
            EXCLUDED_CAPTURE_TITLES,
            curtain_state_path,
            locked_use_enabled,
            read_curtain_state,
            shell_alive,
        )

        system = platform.system()
        meta: dict[str, object] = {
            "platform": system,
            "locked_use_enabled": locked_use_enabled(),
            "curtain_titles": list(EXCLUDED_CAPTURE_TITLES),
        }
        bridge_path = curtain_state_path()
        meta["curtain_bridge_configured"] = bridge_path is not None

        if system != "Darwin":
            return HealthReport(
                component_name="DesktopLockedUse",
                status="pass",
                code="OK_DESKTOP_LOCKED_USE_N_A",
                meta_data=meta,
                message="Locked Use and Privacy Curtain are macOS desktop-shell features.",
                detail="Use the Myrm desktop app on macOS for unattended unlock and privacy curtain.",
            )

        if bridge_path is None:
            locked_on = locked_use_enabled()
            meta["locked_use_enabled"] = locked_on
            return HealthReport(
                component_name="DesktopLockedUse",
                status="fail" if locked_on else "warn",
                code="ERR_CURTAIN_BRIDGE_MISSING" if locked_on else "WARN_CURTAIN_BRIDGE_MISSING",
                meta_data=meta,
                message=(
                    "Locked Use is enabled but the privacy curtain bridge is missing."
                    if locked_on
                    else "Privacy curtain bridge is not configured."
                ),
                detail=(
                    "MYRM_CURTAIN_STATE_FILE is unset while Locked Use is on — "
                    "unattended unlock cannot coordinate with the desktop shell."
                    if locked_on
                    else "MYRM_CURTAIN_STATE_FILE is unset — server-side unattended unlock cannot coordinate with the desktop shell."
                ),
                fix_suggestion="Run the Myrm desktop app (Tauri) on this Mac so the curtain bridge file is created.",
            )

        state = read_curtain_state()
        shell_ok = shell_alive()
        meta["shell_alive"] = shell_ok
        if state is not None:
            meta["curtain_active"] = state.active
            meta["pending_auto_unlock"] = state.pending_auto_unlock

        issues: list[str] = []
        if locked_use_enabled() and not shell_ok:
            issues.append("Locked Use is enabled but the desktop shell process is not reachable")
        if state is not None and state.pending_auto_unlock and not shell_ok:
            issues.append("An unlock lease is held but the desktop shell is gone (re-lock may be delayed)")

        if issues:
            return HealthReport(
                component_name="DesktopLockedUse",
                status="fail",
                code="ERR_DESKTOP_SHELL_UNAVAILABLE",
                meta_data=meta,
                message="Desktop shell coordination for Locked Use / Privacy Curtain is unhealthy.",
                detail="; ".join(issues),
                fix_suggestion="Restart the Myrm desktop app and confirm Privacy Curtain settings in System settings.",
            )

        detail = f"Curtain bridge at {bridge_path.name}; shell alive={shell_ok}."
        if locked_use_enabled():
            detail += " Locked Use enabled."
        return HealthReport(
            component_name="DesktopLockedUse",
            status="pass",
            code="OK_DESKTOP_LOCKED_USE_READY",
            meta_data=meta,
            message="Locked Use / Privacy Curtain bridge is reachable.",
            detail=detail,
        )
