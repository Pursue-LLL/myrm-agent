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
    "upstream request timed out",
    "tools/call response timed out",
    "Chrome MCP response timed out",
    "Network.enable timed out",
    "Navigation timeout",
    "protocolTimeout",
    "MUX_NOT_READY",
    "main frame too early",
    "Chrome MCP connection reset during",
    "Chrome MCP reconnect queue is full",
    "MUX_COLD_ATTACH_TIMEOUT",
    "MUX_UPSTREAM_WAIT_TIMEOUT",
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
SIGNOFF_LIVE_AGENT_MAX_CONCURRENT: Final[int] = 4
SIGNOFF_E2E_PRIVATE_BOOTSTRAP_SLOTS: Final[int] = 4
SIGNOFF_E2E_ACTIVE_RUNTIME_CAPACITY: Final[int] = 4
SIGNOFF_E2E_CAPACITY_WAIT_SEC: Final[int] = 600
MUX_COLD_ATTACH_SLOTS: Final[int] = 2
MUX_COLD_ATTACH_TIMEOUT_MS: Final[int] = 30_000
CDMCP_MUX_REQUEST_TIMEOUT_MS_DEFAULT: Final[int] = 180_000
MUX_MAX_CONCURRENT_SESSIONS: Final[int] = 6
MUX_SIGNOFF_RESERVED_SLOTS: Final[int] = 2
E2E_MUX_ADMISSION_WAIT_SEC: Final[int] = 900
E2E_MUX_ADMISSION_POLL_SEC: Final[int] = 15
MUX_UPSTREAM_WAIT_SEC: Final[int] = 900
MUX_UPSTREAM_POLL_SEC: Final[int] = 15
CHROME_E2E_MATRIX_TIMEOUT_SECONDS: Final[int] = 7200
CHROME_E2E_DESKTOP_TIMEOUT_SECONDS: Final[int] = 7200
CHROME_E2E_STRESS_TIMEOUT_SECONDS: Final[int] = 7200
CHROME_E2E_DESKTOP_MARKER: Final[str] = "chrome_e2e_desktop"
CHROME_E2E_BROWSER_TAKEOVER_LIVE_MARKER: Final[str] = "chrome_e2e_browser_takeover_live"
CHROME_E2E_MATRIX_MARKER_EXPR: Final[str] = (
    "chrome_e2e and not chrome_e2e_desktop and not chrome_e2e_browser_takeover_live"
)
SIGNOFF_WAVE_QUIESCE_WAIT_SEC: Final[int] = 3600
SIGNOFF_WAVE_QUIESCE_POLL_SEC: Final[int] = 5
SIGNOFF_MATRIX_SHARED_UI_WAIT_SEC: Final[int] = 600
SIGNOFF_MATRIX_KEEPALIVE_SEC: Final[int] = 30
SIGNOFF_MATRIX_ATTACH_HEAL_FAILURES: Final[int] = 3
SIGNOFF_MATRIX_ATTACH_HEAL_COOLDOWN_SEC: Final[int] = 60
SIGNOFF_MATRIX_AGENT_PREFIX: Final[str] = "signoff-matrix-"
E2E_RUNTIME_HEAL_AGENT_PREFIXES: Final[tuple[str, ...]] = (
    "e2e-parent-",
    "myrm-test-e2e:",
    "signoff-matrix-parent-",
)
SIGNOFF_CHROME_MATRIX_SELECTED_COUNT: Final[int] = 37


def formal_chrome_e2e_runtime_heal_agent(agent_id: str) -> bool:
    """True when agentId belongs to a formal chrome E2E parent session."""
    normalized = agent_id.strip()
    return any(normalized.startswith(prefix) for prefix in E2E_RUNTIME_HEAL_AGENT_PREFIXES)

# --- Adaptive mux load defaults (env may override in mux_load) ---

BASE_PAGE_TIMEOUT_MS: Final[int] = 30_000
PAGE_TIMEOUT_SLOT_MS: Final[int] = 15_000
MAX_PAGE_TIMEOUT_MS: Final[int] = 120_000
BASE_TOOL_TIMEOUT_SEC: Final[float] = 180.0

# --- Chrome E2E pytest-timeout SSOT (lane-aware; ≥ mux new_page retry window) ---

READ_CHROME_E2E_PYTEST_TIMEOUT_SEC: Final[int] = (
    MUX_UPSTREAM_WAIT_SEC + MAX_PAGE_TIMEOUT_MS // 1000 + 90
)
LIVE_CHROME_E2E_PYTEST_TIMEOUT_SEC: Final[int] = 600


def chrome_e2e_pytest_timeout_for_lane(lane: str) -> int:
    """Return pytest-timeout floor for a formal chrome_e2e session lane."""
    if lane.strip().upper() == "READ":
        return READ_CHROME_E2E_PYTEST_TIMEOUT_SEC
    return LIVE_CHROME_E2E_PYTEST_TIMEOUT_SEC


def chrome_e2e_pytest_timeout_floor(lane: str, joined_argv: str) -> int:
    """Lane floor with marker-aware overrides for long-running phases."""
    if CHROME_E2E_DESKTOP_MARKER in joined_argv:
        return CHROME_E2E_DESKTOP_TIMEOUT_SECONDS
    if CHROME_E2E_BROWSER_TAKEOVER_LIVE_MARKER in joined_argv:
        return CHROME_E2E_MATRIX_TIMEOUT_SECONDS
    return chrome_e2e_pytest_timeout_for_lane(lane)


def apply_chrome_e2e_pytest_timeout_args(
    floor: int,
    args: tuple[str, ...],
) -> tuple[str, ...]:
    """Ensure pytest CLI args include --timeout at least ``floor`` seconds."""
    out: list[str] = []
    found = False
    next_is_timeout = False
    for arg in args:
        if next_is_timeout:
            next_is_timeout = False
            if arg.isdigit() and int(arg) < floor:
                out.append(str(floor))
            else:
                out.append(arg)
            found = True
            continue
        if arg.startswith("--timeout="):
            value = arg.split("=", 1)[1]
            if value.isdigit() and int(value) < floor:
                out.append(f"--timeout={floor}")
            else:
                out.append(arg)
            found = True
        elif arg == "--timeout":
            next_is_timeout = True
            out.append(arg)
        else:
            out.append(arg)
    if not found:
        out.append(f"--timeout={floor}")
    return tuple(out)

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
        CHROME_E2E_MATRIX_MARKER_EXPR,
        "myrm-agent/myrm-agent-server/tests/e2e/",
        "-n0",
        "-s",
        "--timeout=900",
    ),
)

SIGNOFF_CHROME_DESKTOP_PHASE = DevGateSignoffPhase(
    name="chrome_e2e_desktop_macos",
    command=(
        "./myrm",
        "test",
        "-m",
        CHROME_E2E_DESKTOP_MARKER,
        "myrm-agent/myrm-agent-server/tests/e2e/test_desktop_control_approval_chrome_e2e.py",
        "-n0",
        "-s",
        "--timeout=900",
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


def signoff_live_env_shell(*, stress: bool = False) -> str:
    """Emit bash export lines for signoff live Chrome E2E phases."""
    lines = [
        "export MYRM_SIGNOFF_MATRIX=1",
        f"export MYRM_SIGNOFF_MATRIX_KEEPALIVE_SEC={SIGNOFF_MATRIX_KEEPALIVE_SEC}",
        f"export MYRM_SIGNOFF_MATRIX_ATTACH_HEAL_FAILURES={SIGNOFF_MATRIX_ATTACH_HEAL_FAILURES}",
        f"export MYRM_SIGNOFF_MATRIX_ATTACH_HEAL_COOLDOWN_SEC={SIGNOFF_MATRIX_ATTACH_HEAL_COOLDOWN_SEC}",
        f"export MYRM_LIVE_AGENT_MAX_CONCURRENT={SIGNOFF_LIVE_AGENT_MAX_CONCURRENT}",
        "export MYRM_MUX_ALLOW_TIMEOUT_RESTART=1",
        f"export MYRM_MUX_MAX_CONCURRENT_SESSIONS={MUX_MAX_CONCURRENT_SESSIONS}",
        f"export MYRM_MUX_SIGNOFF_RESERVED_SLOTS={MUX_SIGNOFF_RESERVED_SLOTS}",
        f"export MYRM_E2E_MUX_ADMISSION_WAIT_SEC={E2E_MUX_ADMISSION_WAIT_SEC}",
        f"export MYRM_MUX_UPSTREAM_WAIT_SEC={MUX_UPSTREAM_WAIT_SEC}",
        f"export MYRM_MUX_UPSTREAM_POLL_SEC={MUX_UPSTREAM_POLL_SEC}",
        f"export MYRM_CHROME_E2E_SHARED_UI_WAIT_SEC={SIGNOFF_MATRIX_SHARED_UI_WAIT_SEC}",
    ]
    if stress:
        lines.extend(
            [
                f"export MYRM_E2E_PRIVATE_BOOTSTRAP_SLOTS={SIGNOFF_E2E_PRIVATE_BOOTSTRAP_SLOTS}",
                f"export MYRM_E2E_ACTIVE_RUNTIME_CAPACITY={SIGNOFF_E2E_ACTIVE_RUNTIME_CAPACITY}",
                f"export MYRM_E2E_CAPACITY_WAIT_SEC={SIGNOFF_E2E_CAPACITY_WAIT_SEC}",
            ]
        )
    return "\n".join(lines)
