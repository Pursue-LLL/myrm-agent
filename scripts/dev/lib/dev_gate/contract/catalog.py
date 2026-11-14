"""Static contract tables: mux error-classification tokens, retry policy, the E2E stall tokens, the E2E skip allowlist
and the surface test ids."""

from __future__ import annotations

from typing import Final

CONTRACT_VERSION: Final[str] = "2"

# --- Mux error classification (substring match) ---

BENIGN_CLEANUP_TOKENS: Final[tuple[str, ...]] = (
    "No target with given id",
    "LEASE_NOT_ACTIVE",
    "LEASE_NOT_FOUND",
    "Target closed",
    "detached Frame",
    "No page found",
)

TRANSIENT_MUX_ERROR_TOKENS: Final[tuple[str, ...]] = (
    "page has been closed",
    "Target closed",
    "Target.attachToTarget",
    "No target with given id",
    "No page found",
    "upstream terminated",
    "upstream request timed out",
    "tools/call response timed out",
    "Chrome MCP response timed out",
    "Network.enable timed out",
    "Navigation timeout",
    "Timed out after waiting",
    "timed out after waiting",
    "protocolTimeout",
    "MUX_NOT_READY",
    "main frame too early",
    "Chrome MCP connection reset during",
    "Chrome MCP reconnect queue is full",
    "MUX_COLD_ATTACH_TIMEOUT",
    "MUX_UPSTREAM_WAIT_TIMEOUT",
    "Chrome MCP transport closed",
    "retry this call",
    "Could not connect to Chrome",
    "Unexpected server response: 404",
)

PAGE_OWNERSHIP_ERROR_TOKENS: Final[tuple[str, ...]] = (
    "not owned by this shim session",
    "Chrome MCP context reset",
    "call new_page before",
    "No McpPage found for the given page",
    "No page found",
)

# --- Retry policy ---

NEW_PAGE_TOOL_RETRY_ATTEMPTS: Final[int] = 5
TOOL_RETRY_ATTEMPTS: Final[int] = 3
LIVE_AGENT_TOOL_MIN_TIMEOUT_SEC: Final[float] = 15.0

E2E_NODE_STUCK_TOKEN: Final[str] = "E2E_NODE_STUCK"
E2E_BODY_WALL_EXCEEDED_TOKEN: Final[str] = "E2E_BODY_WALL_EXCEEDED"
E2E_TRANSPORT_PROGRESS_TOKEN: Final[str] = "E2E_TRANSPORT_PROGRESS"
E2E_BOOTSTRAP_OPEN_MCP_EXCEEDED_TOKEN: Final[str] = "E2E_BOOTSTRAP_OPEN_MCP_EXCEEDED"
E2E_SIGNOFF_NEW_PAGE_JOIN_EXCEEDED_TOKEN: Final[str] = (
    "E2E_SIGNOFF_NEW_PAGE_JOIN_EXCEEDED"
)

E2E_ADMIT_NODE_STUCK_TOKEN: Final[str] = "E2E_ADMIT_NODE_STUCK"
E2E_BOOTSTRAP_CREDIT_HOG_TOKEN: Final[str] = "E2E_BOOTSTRAP_CREDIT_HOG"

E2E_SHELL_SKELETON_STALL_TOKEN: Final[str] = "E2E_SHELL_SKELETON_STALL"
MUX_RECLAIM_STALL_TOKEN: Final[str] = "MUX_RECLAIM_STALL"
E2E_USER_CLOSED_TAB_TOKEN: Final[str] = "E2E_USER_CLOSED_TAB"
BROWSER_ORCHESTRATOR_REQUIRED_TOKEN: Final[str] = "BROWSER_ORCHESTRATOR_REQUIRED"
E2E_CHROME_MCP_ENTRY_DENIED_TOKEN: Final[str] = "E2E_CHROME_MCP_ENTRY_DENIED"
E2E_ORCHESTRATOR_LEASE_DENIED_TOKEN: Final[str] = "E2E_ORCHESTRATOR_LEASE_DENIED"
E2E_MUX_RECOVERY_REMOVED_TOKEN: Final[str] = "E2E_MUX_RECOVERY_REMOVED"
E2E_ORPHAN_BUDGET_EXCEEDED_TOKEN: Final[str] = "E2E_ORPHAN_BUDGET_EXCEEDED"

# refuse global mux shim teardown when other wave leases/contexts are active.
MUX_CROSS_SESSION_RECOVER_DENIED_TOKEN: Final[str] = (
    "E2E_MUX_CROSS_SESSION_RECOVER_DENIED"
)

SEND_TURN_LOG_TOKEN: Final[str] = "E2E_SEND_TURN"
SEND_TURN_GENERATION_WINDOW_KEY: Final[str] = "__MYRM_E2E_SEND_GENERATION__"

# --- Allowlisted Chrome E2E skips (test module suffix, reason substring) ---

ALLOWLISTED_E2E_SKIPS: Final[tuple[tuple[str, str], ...]] = (
    ("test_fork_chrome_e2e.py", "No sandbox-active chat found in live DB"),
)

# --- E2E surface probes (data-testid SSOT) ---

E2E_SURFACE_TESTIDS: Final[frozenset[str]] = frozenset(
    {
        "app-layout",
        "instinct-dismiss-btn",
        "instinct-draft-card",
        "instinct-inbox-empty",
        "instinct-inbox-panel",
        "kanban-board-row",
        "kanban-board-view",
        "subagent-cancel-btn",
        "subagent-dashboard-panel",
        "subagent-dashboard-trigger",
        "voice-settings-panel",
    }
)


def is_allowlisted_e2e_skip(*, test_path: str, reason: str) -> bool:
    normalized = test_path.replace("\\", "/")
    for suffix, expected_reason in ALLOWLISTED_E2E_SKIPS:
        if normalized.endswith(suffix) and expected_reason in reason:
            return True
    return False
