"""Dev Gate v2 contract SSOT for Chrome MCP E2E orchestration."""

from __future__ import annotations

from dataclasses import dataclass
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
    "MUX_NOT_READY",
    "main frame too early",
    "Chrome MCP connection reset during",
    "Chrome MCP reconnect queue is full",
    "MUX_COLD_ATTACH_TIMEOUT",
    "retry this call",
)

PAGE_OWNERSHIP_ERROR_TOKENS: Final[tuple[str, ...]] = (
    "not owned by this shim session",
    "Chrome MCP context reset",
    "call new_page before",
)

# --- Retry policy ---

NEW_PAGE_TOOL_RETRY_ATTEMPTS: Final[int] = 5
TOOL_RETRY_ATTEMPTS: Final[int] = 3
LIVE_AGENT_TOOL_MIN_TIMEOUT_SEC: Final[float] = 15.0

# --- Parallel caps ---

DEFAULT_XDIST_WORKERS: Final[int] = 2
STRESS_XDIST_WORKERS: Final[int] = 4
DEFAULT_BOOTSTRAP_SLOTS: Final[int] = 2
MUX_COLD_ATTACH_SLOTS: Final[int] = 2
MUX_COLD_ATTACH_TIMEOUT_MS: Final[int] = 30_000

# --- Adaptive mux load defaults (env may override in mux_load) ---

BASE_PAGE_TIMEOUT_MS: Final[int] = 30_000
PAGE_TIMEOUT_SLOT_MS: Final[int] = 15_000
MAX_PAGE_TIMEOUT_MS: Final[int] = 120_000
BASE_TOOL_TIMEOUT_SEC: Final[float] = 180.0

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


@dataclass(frozen=True, slots=True)
class DevGateSignoffPhase:
    name: str
    command: tuple[str, ...]


SIGNOFF_STATIC_PHASE = DevGateSignoffPhase(
    name="static_dev_tests",
    command=("./myrm", "test", "scripts/dev/tests/"),
)

SIGNOFF_NODE_MUX_PHASE = DevGateSignoffPhase(
    name="node_mux_tests",
    command=("npm", "test"),
)

SIGNOFF_CHROME_MATRIX_PHASE = DevGateSignoffPhase(
    name="chrome_e2e_matrix",
    command=(
        "./myrm",
        "test",
        "-m",
        "chrome_e2e",
        "myrm-agent/myrm-agent-server/tests/e2e/",
        "-n",
        str(DEFAULT_XDIST_WORKERS),
    ),
)

SIGNOFF_CHROME_STRESS_PHASE = DevGateSignoffPhase(
    name="chrome_e2e_stress_xdist4",
    command=(
        "./myrm",
        "test",
        "-m",
        "chrome_e2e",
        "myrm-agent/myrm-agent-server/tests/e2e/test_goal_focus_chrome_e2e.py",
        "myrm-agent/myrm-agent-server/tests/e2e/test_execution_cache_chrome_e2e.py",
        "myrm-agent/myrm-agent-server/tests/e2e/test_instinct_inbox_chrome_e2e.py",
        "myrm-agent/myrm-agent-server/tests/e2e/test_research_studio_chrome_e2e.py",
        "-n",
        str(STRESS_XDIST_WORKERS),
    ),
)


def is_allowlisted_e2e_skip(*, test_path: str, reason: str) -> bool:
    normalized = test_path.replace("\\", "/")
    for suffix, expected_reason in ALLOWLISTED_E2E_SKIPS:
        if normalized.endswith(suffix) and expected_reason in reason:
            return True
    return False
