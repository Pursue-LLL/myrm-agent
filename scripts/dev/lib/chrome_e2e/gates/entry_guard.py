"""Fail-closed guards for Chrome MCP entry on the Myrm E2E profile (:9333).

[INPUT]
- MYRM_BROWSER_ORCHESTRATOR, MYRM_CHROME_MCP_DIAGNOSTIC env

[OUTPUT]
- assert_chrome_mcp_mux_entry_allowed(): block mux shim spawn outside diagnostic mode
- is_e2e_chrome_mcp_diagnostic_mode(): explicit diagnostic bypass

[POS]
Dev Gate SSOT for §19.10 D3 — prevents ad-hoc Agent scripts from spawning mux on E2E Chrome.
"""

from __future__ import annotations

import os

from dev_gate_contract import E2E_CHROME_MCP_ENTRY_DENIED_TOKEN


def is_e2e_chrome_mcp_diagnostic_mode() -> bool:
    return os.environ.get("MYRM_CHROME_MCP_DIAGNOSTIC", "").strip() == "1"


def assert_chrome_mcp_mux_entry_allowed() -> None:
    """Refuse mux shim spawn unless explicit diagnostic mode."""
    if is_e2e_chrome_mcp_diagnostic_mode():
        return
    if os.environ.get("MYRM_BROWSER_ORCHESTRATOR", "").strip() == "1":
        return
    raise RuntimeError(
        f"{E2E_CHROME_MCP_ENTRY_DENIED_TOKEN}: mux Chrome MCP is disabled on the E2E "
        "profile — use MYRM_BROWSER_ORCHESTRATOR=1 ./myrm test -m chrome_e2e, or set "
        "MYRM_CHROME_MCP_DIAGNOSTIC=1 for one-shot manual diagnosis only"
    )
