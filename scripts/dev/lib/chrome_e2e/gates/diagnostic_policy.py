"""Centralized diagnostic-only mux operation policy (§19.10 D2)."""

from __future__ import annotations

from dev_gate.contract import E2E_MUX_RECOVERY_REMOVED_TOKEN

from chrome_e2e.gates.entry_guard import is_e2e_chrome_mcp_diagnostic_mode


def assert_mux_diagnostic_only(*, operation: str) -> None:
    """Fail-closed unless MYRM_CHROME_MCP_DIAGNOSTIC=1."""
    if is_e2e_chrome_mcp_diagnostic_mode():
        return
    raise RuntimeError(
        f"{E2E_MUX_RECOVERY_REMOVED_TOKEN}: mux {operation} removed — "
        "use MYRM_BROWSER_ORCHESTRATOR=1 ./myrm test -m chrome_e2e"
    )
