"""Dev Gate v2 contract SSOT for Chrome MCP E2E orchestration (product path).

[INPUT]
(无外部模块依赖，仅 os/typing 标准库)

[OUTPUT]
TRANSIENT_MUX_ERROR_TOKENS: transport 层瞬态错误子串元组（含 "Chrome MCP transport closed"）
BENIGN_CLEANUP_TOKENS: 清理阶段可忽略的错误子串元组
PAGE_OWNERSHIP_ERROR_TOKENS: page ownership 错误子串元组
E2E_UNIFIED_WAIT_SEC / MUX_* / LIVE_* 系列常量: 并行 cap、超时、pytest floor 等 SSOT
chrome_e2e_skips_shared_*: 按 lane/shpoib 判断是否跳过共享资源排队
is_e2e_signoff_runtime / resolve_e2e_wall_profile / E2E_SIGNOFF_* phase budgets: R62 four-phase lifecycle SSOT
SIGNOFF_PYTEST_SAFE_BUFFER_SEC / clarify_skip_api_wait_sec: signoff outer kill · pytest body 600s · clarify wait 90s
apply_chrome_e2e_pytest_timeout_args: dev floor 或 signoff ceiling 模式

[POS]
Dev Gate v2 合约常量 SSOT。定义 Chrome MCP E2E 的错误分类、并行 cap、
超时预算、lane pytest timeout 等配置常量，供 chrome_mcp_client / e2e_bootstrap
/ test.sh 等消费。
"""

from __future__ import annotations

import os
import re
from typing import Final, Literal

E2eWallProfile = Literal["dev", "signoff"]

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
    "Chrome MCP transport closed",
    "retry this call",
)

PAGE_OWNERSHIP_ERROR_TOKENS: Final[tuple[str, ...]] = (
    "not owned by this shim session",
    "Chrome MCP context reset",
    "call new_page before",
    "No McpPage found for the given page",
)

# --- Retry policy ---

NEW_PAGE_TOOL_RETRY_ATTEMPTS: Final[int] = 5
TOOL_RETRY_ATTEMPTS: Final[int] = 3
LIVE_AGENT_TOOL_MIN_TIMEOUT_SEC: Final[float] = 15.0

# --- Parallel caps ---

DEFAULT_XDIST_WORKERS: Final[int] = 2
STRESS_XDIST_WORKERS: Final[int] = 4
DEFAULT_BOOTSTRAP_SLOTS: Final[int] = 2
MUX_COLD_ATTACH_SLOTS: Final[int] = 3
MUX_COLD_ATTACH_TIMEOUT_MS: Final[int] = 30_000
CDMCP_MUX_REQUEST_TIMEOUT_MS_DEFAULT: Final[int] = 180_000
LEGACY_MUX_REQUEST_TIMEOUT_MS: Final[tuple[int, ...]] = (55_000, 65_000, 120_000)
MUX_MAX_CONCURRENT_SESSIONS: Final[int] = 6
E2E_MUX_ADMISSION_WAIT_SEC: Final[int] = 300
E2E_MUX_ADMISSION_POLL_SEC: Final[int] = 15
MUX_UPSTREAM_WAIT_SEC: Final[int] = 300
MUX_UPSTREAM_POLL_SEC: Final[int] = 15
# Single LIVE chrome_e2e test wall-clock stall budget (fail-fast, not pytest floor).
LIVE_SINGLE_TEST_WALL_CLOCK_SEC: Final[int] = 600
# LIVE_AGENT body phase aligns with @pytest.mark.timeout(600) on chrome_e2e LIVE tests.
LIVE_AGENT_BODY_WALL_CLOCK_SEC: Final[int] = LIVE_SINGLE_TEST_WALL_CLOCK_SEC
# R62: signoff four-phase budgets (ADMIT/BOOTSTRAP independent from BODY 600s).
E2E_SIGNOFF_ADMIT_WALL_CLOCK_SEC: Final[int] = 300
E2E_BOOTSTRAP_WALL_CLOCK_SEC_DEV: Final[int] = 180
E2E_BOOTSTRAP_WALL_CLOCK_SEC_SIGNOFF: Final[int] = 120
# R73-B: minimum bridge-hydrate + shared UI session reserve inside bootstrap wall.
E2E_BOOTSTRAP_BRIDGE_HYDRATE_RESERVE_SEC: Final[float] = 90.0
E2E_BOOTSTRAP_SHELL_MIN_SEC: Final[float] = 60.0
E2E_TEARDOWN_WALL_CLOCK_SEC: Final[int] = 30
# Legacy alias: BODY budget for signoff quality gate (not queue+bootstrap merged).
SIGNOFF_LEG_MTB_SEC: Final[int] = LIVE_SINGLE_TEST_WALL_CLOCK_SEC
# R62: pytest body ceiling equals full BODY phase (bootstrap is separate).
SIGNOFF_PYTEST_TIMEOUT_CEILING_SEC: Final[int] = LIVE_SINGLE_TEST_WALL_CLOCK_SEC
SIGNOFF_DEDUPE_WAIT_SEC: Final[int] = 60
SIGNOFF_HUNG_BLOCKER_ELAPSED_SEC: Final[int] = SIGNOFF_LEG_MTB_SEC
_SIGNOFF_TRUTHY: Final[frozenset[str]] = frozenset({"1", "true", "yes", "on"})
# Holder / progress stale detection while queueing on shared_hot stream.
STALL_PROGRESS_SEC: Final[int] = 90
CHROME_E2E_MATRIX_TIMEOUT_SECONDS: Final[int] = 7200
# Single desktop approval chrome_e2e uses the global wall budget (not matrix duration).
CHROME_E2E_DESKTOP_TIMEOUT_SECONDS: Final[int] = LIVE_SINGLE_TEST_WALL_CLOCK_SEC
CHROME_E2E_STRESS_TIMEOUT_SECONDS: Final[int] = 7200
CHROME_E2E_DESKTOP_MARKER: Final[str] = "chrome_e2e_desktop"
CHROME_E2E_BROWSER_TAKEOVER_LIVE_MARKER: Final[str] = "chrome_e2e_browser_takeover_live"
CHROME_E2E_MATRIX_MARKER_EXPR: Final[str] = (
    "chrome_e2e and not chrome_e2e_desktop and not chrome_e2e_browser_takeover_live"
)
# Unified E2E admission (UEA v3).
E2E_UNIFIED_WAIT_SEC: Final[int] = 300
# R58: lease/mux/SHPOIB bootstrap queue budget (separate from 600s body wall clock).
E2E_ADMISSION_WALL_CLOCK_SEC: Final[int] = 900
LIVE_SHPOIB_MAX_CONCURRENT: Final[int] = 4
LIVE_SHARED_HOT_MAX_CONCURRENT: Final[int] = 1
E2E_RUNTIME_HEAL_AGENT_PREFIXES: Final[tuple[str, ...]] = (
    "e2e-parent-",
    "myrm-test-e2e:",
    "goal-focus-",
    "execution-cache-",
)


def is_e2e_signoff_runtime() -> bool:
    """True when M3 signoff thin shell exported E2E_SIGNOFF=1."""
    return os.environ.get("E2E_SIGNOFF", "").strip().lower() in _SIGNOFF_TRUTHY


def is_e2e_signoff_clarify_api_runtime() -> bool:
    """True when signoff clarify leg runs API-only contract (R66, no chrome bootstrap)."""
    return (
        is_e2e_signoff_runtime()
        and os.environ.get("MYRM_E2E_SIGNOFF_CLARIFY_API", "").strip().lower()
        in _SIGNOFF_TRUTHY
    )


def signoff_clarify_backend_ready_wait_sec() -> int:
    """SHPOIB provider_ready poll cap for signoff clarify API leg."""
    if is_e2e_signoff_clarify_api_runtime():
        return SIGNOFF_CLARIFY_BACKEND_READY_WAIT_SEC
    override = os.environ.get("MYRM_E2E_BACKEND_READY_WAIT_SEC", "").strip()
    if override.isdigit() and int(override) > 0:
        return int(override)
    return 180


def chrome_e2e_skips_signoff_private_preflight() -> bool:
    """Signoff clarify API-only still runs api-only preflight seed (no Chrome/mux)."""
    return False


def resolve_e2e_wall_profile() -> E2eWallProfile:
    """Return dev or signoff lifecycle profile (both use four-phase budgets)."""
    return "signoff" if is_e2e_signoff_runtime() else "dev"


def clarify_skip_api_wait_sec() -> int:
    """Clarify form/API pending wait budget; signoff uses shorter fail-fast window."""
    if is_e2e_signoff_runtime():
        return SIGNOFF_CLARIFY_SKIP_API_WAIT_SEC
    return CLARIFY_SKIP_API_WAIT_SEC


def formal_chrome_e2e_runtime_heal_agent(agent_id: str) -> bool:
    """True when agentId belongs to a formal chrome E2E parent session."""
    normalized = agent_id.strip()
    return any(
        normalized.startswith(prefix) for prefix in E2E_RUNTIME_HEAL_AGENT_PREFIXES
    )


# --- Adaptive mux load defaults (env may override in mux_load) ---

BASE_PAGE_TIMEOUT_MS: Final[int] = 30_000
PAGE_TIMEOUT_SLOT_MS: Final[int] = 15_000
MAX_PAGE_TIMEOUT_MS: Final[int] = 120_000
BASE_TOOL_TIMEOUT_SEC: Final[float] = 180.0

# --- Chrome E2E pytest-timeout SSOT (lane-aware; ≥ mux new_page retry window) ---

# Shared-hot LIVE tests queue on :8080 agent-stream (e2e_runtime_guard default).
LIVE_AGENT_STREAM_WAIT_SEC: Final[int] = 300
# Desktop shared_hot queue cap aligns with monotonic wall budget (R39).
LIVE_AGENT_STREAM_WAIT_DESKTOP_SEC: Final[int] = LIVE_SINGLE_TEST_WALL_CLOCK_SEC
# pytest-timeout cap for a single LIVE pytest item (bootstrap + body + teardown; ADMIT is pre-pytest).
LIVE_AGENT_PYTEST_WALL_CAP_SEC: Final[int] = (
    E2E_BOOTSTRAP_WALL_CLOCK_SEC_DEV
    + LIVE_SINGLE_TEST_WALL_CLOCK_SEC
    + E2E_TEARDOWN_WALL_CLOCK_SEC
)
# pytest-timeout floor body segment — SSOT with LIVE_AGENT_BODY_WALL_CLOCK_SEC (R73-D / R96-R62).
LIVE_AGENT_BODY_BUFFER_SEC: Final[int] = LIVE_AGENT_BODY_WALL_CLOCK_SEC
# SHPOIB clarify skip API poll under parallel load (API-first path).
CLARIFY_SKIP_API_WAIT_SEC: Final[int] = 180
# M3 signoff: fail-fast clarify wait (LLM flake should not burn full BODY 600s).
SIGNOFF_CLARIFY_SKIP_API_WAIT_SEC: Final[int] = 90
# R66/R67: signoff clarify SHPOIB bootstrap wait (BOOTSTRAP phase; warm pool uses 120s).
SIGNOFF_CLARIFY_BACKEND_READY_WAIT_SEC: Final[int] = (
    E2E_BOOTSTRAP_WALL_CLOCK_SEC_SIGNOFF
)
# R66: signoff clarify SHPOIB cold bootstrap quality gate (BODY startup+junit excluded).
SIGNOFF_CLARIFY_STARTUP_QUALITY_MAX_SEC: Final[int] = 90
SIGNOFF_CLARIFY_API_SEAL_CLARIFY: Final[str] = (
    "E2E_SIGNOFF_CLARIFY_API_SEAL: clarify_confirmed"
)
SIGNOFF_CLARIFY_API_SEAL_SKIP: Final[str] = (
    "E2E_SIGNOFF_CLARIFY_API_SEAL: skip_resume_ok"
)
# R47: hard wall for mux page reopen/reclaim (nested call_tool must not burn 600s).
MUX_PAGE_RECLAIM_HARD_TIMEOUT_SEC: Final[int] = 120
SHELL_PROBE_STALL_FAIL_FAST_SEC: Final[int] = 120
# R96-MUX: browser takeover gate — consecutive MUX stall without API gate progress.
GATE_MUX_STALL_FAIL_FAST_SEC: Final[int] = 120
E2E_SHELL_SKELETON_STALL_TOKEN: Final[str] = "E2E_SHELL_SKELETON_STALL"
MUX_RECLAIM_STALL_TOKEN: Final[str] = "MUX_RECLAIM_STALL"
# R69: refuse global mux shim teardown when other wave leases/contexts are active.
MUX_CROSS_SESSION_RECOVER_DENIED_TOKEN: Final[str] = "E2E_MUX_CROSS_SESSION_RECOVER_DENIED"
# R72 SendTurnContract: single evaluate budget (kickoff observe + API poll + margin).
SEND_TURN_EVAL_RECV_SEC: Final[float] = 120.0
SEND_TURN_PYTHON_WALL_SEC: Final[float] = 130.0
SEND_TURN_OBSERVE_SEC: Final[int] = 45
SEND_TURN_API_POLL_SEC: Final[int] = 60
SEND_TURN_LOG_TOKEN: Final[str] = "E2E_SEND_TURN"
SEND_TURN_GENERATION_WINDOW_KEY: Final[str] = "__MYRM_E2E_SEND_GENERATION__"
# run_pytest_safe outer budget padding beyond pytest floor (bootstrap/MCP setup).
PYTEST_SAFE_BOOTSTRAP_BUFFER_SEC: Final[int] = 120
# M3 signoff: outer kill aligned with R62 four-phase signoff budgets.
SIGNOFF_PYTEST_SAFE_BUFFER_SEC: Final[int] = 60
SIGNOFF_OUTER_KILL_SEC: Final[int] = (
    E2E_SIGNOFF_ADMIT_WALL_CLOCK_SEC
    + E2E_BOOTSTRAP_WALL_CLOCK_SEC_SIGNOFF
    + LIVE_SINGLE_TEST_WALL_CLOCK_SEC
    + SIGNOFF_PYTEST_SAFE_BUFFER_SEC
)
# Stream lock holder heartbeat file (waiters read holder identity while queueing).
LIVE_AGENT_STREAM_HOLDER_INFO_BASENAME: Final[str] = (
    "myrm-live-agent-stream.holder.json"
)

READ_CHROME_E2E_PYTEST_TIMEOUT_SEC: Final[int] = (
    MUX_UPSTREAM_WAIT_SEC + MAX_PAGE_TIMEOUT_MS // 1000 + 90
)
LIVE_CHROME_E2E_PYTEST_TIMEOUT_SEC: Final[int] = (
    LIVE_AGENT_STREAM_WAIT_SEC
    + LIVE_AGENT_BODY_BUFFER_SEC
    + MAX_PAGE_TIMEOUT_MS // 1000
    + 90
)
CHROME_E2E_BROWSER_TAKEOVER_PYTEST_TIMEOUT_SEC: Final[int] = (
    LIVE_CHROME_E2E_PYTEST_TIMEOUT_SEC
)


def chrome_e2e_pytest_timeout_for_lane(lane: str) -> int:
    """Return pytest-timeout floor for a formal chrome_e2e session lane."""
    if lane.strip().upper() == "READ":
        return READ_CHROME_E2E_PYTEST_TIMEOUT_SEC
    return LIVE_CHROME_E2E_PYTEST_TIMEOUT_SEC


def chrome_e2e_pytest_safe_queue_buffer_sec(
    lane: str,
    joined_argv: str,
    *,
    shpoib: bool | None = None,
) -> int:
    """Queue/admission wait excluded from R58 body wall clock but counted by run_pytest_safe."""
    if resolve_e2e_wall_profile() == "signoff":
        return E2E_SIGNOFF_ADMIT_WALL_CLOCK_SEC
    resolved_shpoib = (
        shpoib
        if shpoib is not None
        else os.environ.get("E2E_PROFILE_SHPOIB", "").strip() == "1"
    )
    if resolved_shpoib:
        return E2E_ADMISSION_WALL_CLOCK_SEC
    if lane.strip().upper() != "LIVE_AGENT":
        return 0
    buffer = E2E_UNIFIED_WAIT_SEC
    if not chrome_e2e_skips_shared_stream_lock(lane=lane, shpoib=resolved_shpoib):
        buffer += live_agent_stream_wait_sec(joined_argv)
    return buffer


def chrome_e2e_pytest_safe_timeout_sec(
    lane: str,
    item_count: int,
    joined_argv: str = "",
) -> int:
    """Hard timeout for run_pytest_safe wrapper across a chrome_e2e session."""
    if resolve_e2e_wall_profile() == "signoff":
        return SIGNOFF_OUTER_KILL_SEC
    per_item = chrome_e2e_pytest_timeout_floor(lane, joined_argv)
    normalized_count = max(1, int(item_count))
    raw = per_item * normalized_count
    # CHROME_E2E_MATRIX is per long single-test (desktop/matrix); multi-item sessions scale by mux waves.
    wave_cap = CHROME_E2E_MATRIX_TIMEOUT_SECONDS * max(
        1,
        (normalized_count + MUX_MAX_CONCURRENT_SESSIONS - 1)
        // MUX_MAX_CONCURRENT_SESSIONS,
    )
    queue_buffer = chrome_e2e_pytest_safe_queue_buffer_sec(lane, joined_argv)
    return min(raw, wave_cap) + PYTEST_SAFE_BOOTSTRAP_BUFFER_SEC + queue_buffer


def chrome_e2e_pytest_timeout_floor(lane: str, joined_argv: str) -> int:
    """Lane floor with marker-aware overrides; SHPOIB admission runs inside pytest fixture."""
    if resolve_e2e_wall_profile() == "signoff":
        return SIGNOFF_PYTEST_TIMEOUT_CEILING_SEC
    if CHROME_E2E_DESKTOP_MARKER in joined_argv:
        return CHROME_E2E_DESKTOP_TIMEOUT_SECONDS
    floor = chrome_e2e_pytest_timeout_for_lane(lane)
    body_cap = LIVE_SINGLE_TEST_WALL_CLOCK_SEC
    shpoib = os.environ.get("E2E_PROFILE_SHPOIB", "").strip() == "1"
    if shpoib and lane.strip().upper() == "LIVE_AGENT":
        body_cap = LIVE_AGENT_PYTEST_WALL_CAP_SEC
    return min(floor, body_cap)


def chrome_e2e_skips_shared_approval_preflight(*, lane: str, shpoib: bool) -> bool:
    """True when LIVE E2E uses SHPOIB private backend — skip shared :8080 approval preflight."""
    return lane == "LIVE_AGENT" and shpoib


def chrome_e2e_skips_shared_stream_lock(*, lane: str, shpoib: bool) -> bool:
    """True when SHPOIB LIVE must not FIFO-queue on shared :8080 agent-stream lock."""
    return lane == "LIVE_AGENT" and shpoib


def chrome_e2e_skips_attach_health_reprobe(
    *,
    chrome_attach: bool,
    shared_hot: bool = False,
    stream_lock_held: bool = False,
    api_only: bool = False,
) -> bool:
    """True when test.sh bootstrap already verified Chrome attach — skip pytest fixture reprobe."""
    return chrome_attach or shared_hot or stream_lock_held or api_only


def live_agent_stream_wait_sec(joined_argv: str) -> int:
    """Seconds to FIFO-wait on shared :8080 agent-stream lock before fail-closed."""
    if CHROME_E2E_DESKTOP_MARKER in joined_argv:
        return LIVE_AGENT_STREAM_WAIT_DESKTOP_SEC
    return LIVE_AGENT_STREAM_WAIT_SEC


def _normalize_pytest_timeout_value(raw: str, *, floor: int, ceiling: bool) -> str:
    if not raw.isdigit():
        return raw
    value = int(raw)
    if ceiling:
        return str(min(value, floor))
    if value < floor:
        return str(floor)
    return raw


_CHROME_E2E_PYTEST_FILE = re.compile(r"(^|[/\\])test_[^/\\]*_chrome_e2e\.py(::|$)")


def pytest_argv_needs_live_chrome_e2e(
    argv: tuple[str, ...],
    *,
    run_e2e_tests: bool = False,
) -> bool:
    """True when ./myrm test argv selects formal chrome_e2e (marker or *_chrome_e2e.py).

    Must not match unit-test node ids or -k filters that merely contain the substring
    ``chrome_e2e`` (R99 gate tests live under scripts/dev/tests/).
    """
    next_is_marker = False
    for arg in argv:
        if next_is_marker:
            next_is_marker = False
            if "chrome_e2e" in arg:
                return True
            continue
        if arg in {"-m", "--markers"}:
            next_is_marker = True
            continue
        if _CHROME_E2E_PYTEST_FILE.search(arg):
            return True
    if run_e2e_tests:
        return any(_CHROME_E2E_PYTEST_FILE.search(arg) for arg in argv)
    return False


def apply_chrome_e2e_pytest_timeout_args(
    floor: int,
    args: tuple[str, ...],
) -> tuple[str, ...]:
    """Ensure pytest CLI --timeout respects dev floor or signoff ceiling."""
    ceiling_mode = resolve_e2e_wall_profile() == "signoff"
    out: list[str] = []
    found = False
    next_is_timeout = False
    for arg in args:
        if next_is_timeout:
            next_is_timeout = False
            out.append(
                _normalize_pytest_timeout_value(arg, floor=floor, ceiling=ceiling_mode)
            )
            found = True
            continue
        if arg.startswith("--timeout="):
            value = arg.split("=", 1)[1]
            normalized = _normalize_pytest_timeout_value(
                value, floor=floor, ceiling=ceiling_mode
            )
            out.append(f"--timeout={normalized}")
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


def is_allowlisted_e2e_skip(*, test_path: str, reason: str) -> bool:
    normalized = test_path.replace("\\", "/")
    for suffix, expected_reason in ALLOWLISTED_E2E_SKIPS:
        if normalized.endswith(suffix) and expected_reason in reason:
            return True
    return False
