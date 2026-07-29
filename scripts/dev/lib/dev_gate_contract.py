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

# --- Parallel caps ---

DEFAULT_XDIST_WORKERS: Final[int] = 2
STRESS_XDIST_WORKERS: Final[int] = 4
DEFAULT_BOOTSTRAP_SLOTS: Final[int] = 2
MUX_COLD_ATTACH_SLOTS: Final[int] = 3
MUX_COLD_ATTACH_TIMEOUT_MS: Final[int] = 30_000
CDMCP_MUX_REQUEST_TIMEOUT_MS_DEFAULT: Final[int] = 180_000
LEGACY_MUX_REQUEST_TIMEOUT_MS: Final[tuple[int, ...]] = (55_000, 65_000, 120_000)
# R107: align mux session admission with upstream cold-attach cap (SSOT).
MUX_MAX_CONCURRENT_SESSIONS: Final[int] = MUX_COLD_ATTACH_SLOTS
E2E_MUX_ADMISSION_WAIT_SEC: Final[int] = 300
E2E_MUX_ADMISSION_POLL_SEC: Final[int] = 15
# R123/BUG-DG-022: mux ADMIT wait scales with active wave leases (align attach scaling).
MUX_ADMISSION_WAIT_LEASE_SEC: Final[int] = 45
MUX_UPSTREAM_WAIT_SEC: Final[int] = 300
MUX_UPSTREAM_POLL_SEC: Final[int] = 15
# Single LIVE chrome_e2e test wall-clock stall budget (fail-fast, not pytest floor).
LIVE_SINGLE_TEST_WALL_CLOCK_SEC: Final[int] = 600
# LIVE_AGENT body phase aligns with @pytest.mark.timeout(600) on chrome_e2e LIVE tests.
LIVE_AGENT_BODY_WALL_CLOCK_SEC: Final[int] = LIVE_SINGLE_TEST_WALL_CLOCK_SEC
# R62: signoff four-phase budgets (ADMIT/BOOTSTRAP independent from BODY 600s).
E2E_SIGNOFF_ADMIT_WALL_CLOCK_SEC: Final[int] = 300
E2E_BOOTSTRAP_WALL_CLOCK_SEC_DEV: Final[int] = 180
E2E_BOOTSTRAP_WALL_CLOCK_SEC_SIGNOFF: Final[int] = 240
# R73-B: minimum bridge-hydrate + shared UI session reserve inside bootstrap wall.
E2E_BOOTSTRAP_BRIDGE_HYDRATE_RESERVE_SEC: Final[float] = 90.0
E2E_BOOTSTRAP_SHELL_MIN_SEC: Final[float] = 60.0
E2E_TEARDOWN_WALL_CLOCK_SEC: Final[int] = 30
# Legacy alias: BODY budget for signoff quality gate (not queue+bootstrap merged).
SIGNOFF_LEG_MTB_SEC: Final[int] = LIVE_SINGLE_TEST_WALL_CLOCK_SEC
# R81: pytest-timeout spans ADMIT+BOOTSTRAP fixtures + BODY (func_only=False); must not
# kill during SHPOIB capacity wait under parallel chrome_e2e. Quality gate still uses
# ceil(startup+junit_time) ≤600s for BODY-only elapsed.
SIGNOFF_PYTEST_TIMEOUT_CEILING_SEC: Final[int] = (
    E2E_SIGNOFF_ADMIT_WALL_CLOCK_SEC
    + E2E_BOOTSTRAP_WALL_CLOCK_SEC_SIGNOFF
    + LIVE_SINGLE_TEST_WALL_CLOCK_SEC
)
SIGNOFF_DEDUPE_WAIT_SEC: Final[int] = 60
SIGNOFF_HUNG_BLOCKER_ELAPSED_SEC: Final[int] = SIGNOFF_LEG_MTB_SEC
_SIGNOFF_TRUTHY: Final[frozenset[str]] = frozenset({"1", "true", "yes", "on"})
# Holder / progress stale detection while queueing on shared_hot stream.
STALL_PROGRESS_SEC: Final[int] = 90


def shpoib_parallel_stall_progress_sec() -> float:
    """Scale BODY progress-stale cap under parallel SHPOIB load (R124).

    Matches file_write LIVE scaling: base 90s + 10s per active wave lease (max 150s).
    """
    base = float(STALL_PROGRESS_SEC)
    if os.environ.get("MYRM_E2E_SHPOIB", "").strip() != "1":
        return base
    active_leases = 0
    try:
        from pathlib import Path

        from stack_mutation_policy import wave_active_lease_count

        monorepo_root = Path(__file__).resolve().parents[4]
        active_leases = wave_active_lease_count(monorepo_root)
    except (ImportError, OSError, RuntimeError, ValueError):
        active_leases = 0
    if active_leases < 2:
        return base
    return min(150.0, base + active_leases * 10.0)


def mux_reset_after_orphan_timeout_sec() -> float:
    """Scale asyncio wait_for around reset_after_orphan under parallel mux load (R142).

    v9 died at hardcoded 90s while peers≥6; align with shpoib_parallel_stall scaling.
    """
    base = 90.0
    active_leases = 0
    try:
        from pathlib import Path

        from stack_mutation_policy import wave_active_lease_count

        monorepo_root = Path(__file__).resolve().parents[4]
        active_leases = wave_active_lease_count(monorepo_root)
    except (ImportError, OSError, RuntimeError, ValueError):
        active_leases = 0
    if active_leases < 2:
        return base
    return min(180.0, base + active_leases * 10.0)


CHROME_E2E_MATRIX_TIMEOUT_SECONDS: Final[int] = 7200
# Single desktop approval chrome_e2e uses the global wall budget (not matrix duration).
CHROME_E2E_DESKTOP_TIMEOUT_SECONDS: Final[int] = LIVE_SINGLE_TEST_WALL_CLOCK_SEC
CHROME_E2E_STRESS_TIMEOUT_SECONDS: Final[int] = 7200
CHROME_E2E_DESKTOP_MARKER: Final[str] = "chrome_e2e_desktop"
CHROME_E2E_BROWSER_TAKEOVER_LIVE_MARKER: Final[str] = "chrome_e2e_browser_takeover_live"
CHROME_E2E_SIGNOFF_BATCH_MARKER: Final[str] = "chrome_e2e_signoff_batch"
CHROME_E2E_MATRIX_MARKER_EXPR: Final[str] = (
    "chrome_e2e and not chrome_e2e_desktop and not chrome_e2e_browser_takeover_live"
)
# Unified E2E admission (UEA v3).
E2E_UNIFIED_WAIT_SEC: Final[int] = 300
# R58: lease/mux/SHPOIB bootstrap queue budget (separate from 600s body wall clock).
E2E_ADMISSION_WALL_CLOCK_SEC: Final[int] = 900
# R122: attach crash-heal try-lock; defer instead of 180s×N dogpile under parallel attach.
E2E_ATTACH_CRASH_HEAL_FLOCK_WAIT_SEC: Final[float] = 5.0
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


def signoff_clarify_backend_ensure_subprocess_timeout_sec() -> int:
    """Subprocess cap for dev-stack backend-only ensure (must exceed health poll)."""
    return max(
        _SIGNOFF_CLARIFY_SEED_START_TIMEOUT_SEC,
        E2E_BOOTSTRAP_WALL_CLOCK_SEC_SIGNOFF,
        SIGNOFF_CLARIFY_BACKEND_HEALTH_WAIT_SEC + 120,
        SIGNOFF_CLARIFY_BACKEND_READY_WAIT_SEC + 360,
    )


def _wave_active_lease_count_for_mux() -> int:
    try:
        from pathlib import Path

        from stack_mutation_policy import wave_active_lease_count

        monorepo_root = Path(__file__).resolve().parents[4]
        return max(0, wave_active_lease_count(monorepo_root))
    except (ImportError, OSError, RuntimeError, ValueError):
        return 0


def _parallel_chrome_e2e_pressure() -> int:
    """Wave leases plus live ADMIT/BODY sessions — drives attach UI probe scaling (R148)."""
    pressure = _wave_active_lease_count_for_mux()
    try:
        from e2e_session_registry import list_live_e2e_sessions

        pressure = max(pressure, len(list_live_e2e_sessions()))
    except (ImportError, OSError, RuntimeError, ValueError):
        pass
    return max(0, pressure)


def attach_ui_probe_timeout_sec() -> float:
    """Shared :3000 HTTP probe timeout; scales under parallel chrome_e2e (R148).

    Solo 8s; under load min(25, 8+pressure×2)s. Isolated runtime keeps 30s.
    """
    if os.environ.get("MYRM_E2E_ISOLATED", "").strip() == "1":
        return 30.0
    override = os.environ.get("MYRM_E2E_ATTACH_UI_PROBE_TIMEOUT_SEC", "").strip()
    if override:
        try:
            value = float(override)
            if value > 0:
                return value
        except ValueError:
            pass
    if os.environ.get("MYRM_E2E_SHPOIB", "").strip() != "1":
        return 8.0
    pressure = _parallel_chrome_e2e_pressure()
    if pressure <= 0:
        return 8.0
    return min(25.0, 8.0 + pressure * 2.0)


def admit_wall_clock_sec() -> int:
    """ADMIT-phase hung-reap / queue SSOT (900 dev · 300 signoff)."""
    if is_e2e_signoff_runtime():
        return E2E_SIGNOFF_ADMIT_WALL_CLOCK_SEC
    return E2E_ADMISSION_WALL_CLOCK_SEC


def mux_admission_wait_sec() -> int:
    """Mux session ADMIT queue; dev scales under parallel wave load (R123/BUG-DG-022)."""
    override = os.environ.get("MYRM_E2E_MUX_ADMISSION_WAIT_SEC", "").strip()
    if override.isdigit() and int(override) > 0:
        return int(override)
    if is_e2e_signoff_runtime():
        return E2E_SIGNOFF_ADMIT_WALL_CLOCK_SEC
    active_leases = _wave_active_lease_count_for_mux()
    if active_leases > 0:
        scaled = (
            E2E_MUX_ADMISSION_WAIT_SEC + active_leases * MUX_ADMISSION_WAIT_LEASE_SEC
        )
        return min(E2E_ADMISSION_WALL_CLOCK_SEC, scaled)
    return E2E_ADMISSION_WALL_CLOCK_SEC


def shared_ui_hydrate_wait_sec() -> int:
    """SHPOIB shared :3000 hydrate burst queue; dev ADMIT 900s."""
    override = os.environ.get("MYRM_E2E_SHARED_UI_HYDRATE_WAIT_SEC", "").strip()
    if override.isdigit() and int(override) > 0:
        return int(override)
    if is_e2e_signoff_runtime():
        return E2E_SIGNOFF_ADMIT_WALL_CLOCK_SEC
    return E2E_ADMISSION_WALL_CLOCK_SEC


def chrome_e2e_skips_signoff_private_preflight() -> bool:
    """Signoff clarify API-only still runs api-only preflight seed (no Chrome/mux)."""
    return False


def resolve_e2e_wall_profile() -> E2eWallProfile:
    """Return dev or signoff lifecycle profile (both use four-phase budgets)."""
    return "signoff" if is_e2e_signoff_runtime() else "dev"


def mux_page_reclaim_hard_timeout_sec() -> int:
    """Mux page reopen/reclaim hard wall; signoff allows parallel mux bind_lease wait."""
    if is_e2e_signoff_runtime():
        return MUX_PAGE_RECLAIM_HARD_TIMEOUT_SIGNOFF_SEC
    return MUX_PAGE_RECLAIM_HARD_TIMEOUT_SEC


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
# M3 signoff: clarify API wait — must cover SHPOIB agent cold-start under parallel load.
SIGNOFF_CLARIFY_SKIP_API_WAIT_SEC: Final[int] = 300
# R100/R105: one-shot agent-stream warm during SHPOIB pool acquire (parallel cold start).
SIGNOFF_CLARIFY_AGENT_WARM_TIMEOUT_SEC: Final[int] = 600
# R66/R67: signoff clarify SHPOIB bootstrap wait (BOOTSTRAP phase; warm pool uses 120s).
SIGNOFF_CLARIFY_BACKEND_READY_WAIT_SEC: Final[int] = (
    E2E_BOOTSTRAP_WALL_CLOCK_SEC_SIGNOFF
)
# R115: dev-stack /health poll during backend-only ensure under parallel signoff load.
SIGNOFF_CLARIFY_BACKEND_HEALTH_WAIT_SEC: Final[int] = (
    E2E_BOOTSTRAP_WALL_CLOCK_SEC_SIGNOFF * 2
)
# Align verify_backend_seed.SEED_START_TIMEOUT_SEC (avoid cross-module import).
_SIGNOFF_CLARIFY_SEED_START_TIMEOUT_SEC: Final[int] = 180
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
# R83: signoff desktop under parallel chrome_e2e may block on bind_lease >120s.
MUX_PAGE_RECLAIM_HARD_TIMEOUT_SIGNOFF_SEC: Final[int] = E2E_SIGNOFF_ADMIT_WALL_CLOCK_SEC
# R85/R88: mux cold-attach queue + bind_lease under parallel (≤ ADMIT + reclaim).
# R85/R88/R89: mux cold-attach + bind_lease under parallel (≤ 3× ADMIT queue budget).
SIGNOFF_DESKTOP_OPEN_NAV_WALL_TIMEOUT_SEC: Final[int] = E2E_MUX_ADMISSION_WAIT_SEC * 3
# R91/R92: signoff open uses direct + direct_recover retries (see infra_retry strategies).
SIGNOFF_DESKTOP_OPEN_NAV_STRATEGY_COUNT: Final[int] = 3
# R88/R92: desktop pytest spans bootstrap + N× open/nav reserve + fresh BODY after open.
SIGNOFF_DESKTOP_PYTEST_TIMEOUT_CEILING_SEC: Final[int] = (
    E2E_BOOTSTRAP_WALL_CLOCK_SEC_SIGNOFF
    + SIGNOFF_DESKTOP_OPEN_NAV_WALL_TIMEOUT_SEC
    * SIGNOFF_DESKTOP_OPEN_NAV_STRATEGY_COUNT
    + LIVE_SINGLE_TEST_WALL_CLOCK_SEC
    + E2E_TEARDOWN_WALL_CLOCK_SEC
)
SHELL_PROBE_STALL_FAIL_FAST_SEC: Final[int] = 120
# R96-MUX: browser takeover gate — consecutive MUX stall without API gate progress.
GATE_MUX_STALL_FAIL_FAST_SEC: Final[int] = 120
# R96-B6: transport infra nodes stuck without semantic progress (parallel mux hog).
NODE_STUCK_FAIL_FAST_SEC: Final[int] = GATE_MUX_STALL_FAIL_FAST_SEC
E2E_NODE_STUCK_TOKEN: Final[str] = "E2E_NODE_STUCK"
E2E_BODY_WALL_EXCEEDED_TOKEN: Final[str] = "E2E_BODY_WALL_EXCEEDED"
E2E_TRANSPORT_PROGRESS_TOKEN: Final[str] = "E2E_TRANSPORT_PROGRESS"
TRANSPORT_STALL_NODE_PREFIXES: Final[tuple[str, ...]] = (
    "open_mcp_page_",
    "mux_",
    "bootstrap_",
    "bridge_",
    "E2E_BOOTSTRAP",
)
E2E_SHELL_SKELETON_STALL_TOKEN: Final[str] = "E2E_SHELL_SKELETON_STALL"
MUX_RECLAIM_STALL_TOKEN: Final[str] = "MUX_RECLAIM_STALL"
# R69: refuse global mux shim teardown when other wave leases/contexts are active.
MUX_CROSS_SESSION_RECOVER_DENIED_TOKEN: Final[str] = (
    "E2E_MUX_CROSS_SESSION_RECOVER_DENIED"
)
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
# R93: READ SHPOIB signoff panel legs reserve UEA capacity wait inside pytest (func_only=False).
SIGNOFF_READ_SHPOIB_PYTEST_TIMEOUT_CEILING_SEC: Final[int] = (
    E2E_SIGNOFF_ADMIT_WALL_CLOCK_SEC
    + E2E_ADMISSION_WALL_CLOCK_SEC
    + E2E_BOOTSTRAP_WALL_CLOCK_SEC_SIGNOFF
    + LIVE_SINGLE_TEST_WALL_CLOCK_SEC
)
SIGNOFF_READ_SHPOIB_OUTER_KILL_SEC: Final[int] = (
    SIGNOFF_READ_SHPOIB_PYTEST_TIMEOUT_CEILING_SEC + SIGNOFF_PYTEST_SAFE_BUFFER_SEC
)
# R97: signoff READ SHPOIB open/rebind waits under parallel turbopack + mux contention.
SIGNOFF_OPEN_PAGE_LAYOUT_WAIT_SEC: Final[int] = 180
SIGNOFF_OPEN_PAGE_WALL_BUDGET_SEC: Final[int] = 240
SIGNOFF_OPEN_PAGE_TOTAL_BUDGET_SEC: Final[int] = 420
SIGNOFF_OPEN_PAGE_PARALLEL_WALL_CAP_SEC: Final[int] = 420
SIGNOFF_OPEN_PAGE_PARALLEL_TOTAL_CAP_SEC: Final[int] = 600
SIGNOFF_SHPOIB_REBIND_WALL_SEC: Final[int] = 300
SIGNOFF_SHPOIB_REBIND_LOCATION_WAIT_SEC: Final[int] = 120
# R90: desktop signoff spans open/nav reserve inside pytest (not quality-gate BODY).
SIGNOFF_DESKTOP_OUTER_KILL_SEC: Final[int] = (
    SIGNOFF_DESKTOP_PYTEST_TIMEOUT_CEILING_SEC + SIGNOFF_PYTEST_SAFE_BUFFER_SEC
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


def _signoff_read_shpoib_leg(joined_argv: str) -> bool:
    """True when signoff READ lane runs SHPOIB chrome_e2e (panel_stdin legs)."""
    if CHROME_E2E_DESKTOP_MARKER in joined_argv:
        return False
    shpoib = os.environ.get("E2E_PROFILE_SHPOIB", "").strip() == "1"
    lane = os.environ.get("MYRM_E2E_LANE", "").strip().upper()
    return shpoib and lane == "READ"


def _parse_signoff_batch_body_sec(joined_argv: str) -> int | None:
    """Extract body_sec from chrome_e2e_signoff_batch marker in joined argv."""
    if CHROME_E2E_SIGNOFF_BATCH_MARKER not in joined_argv:
        return None
    for token in joined_argv.split():
        if token.startswith("body_sec="):
            raw = token.split("=", 1)[1]
            if raw.isdigit():
                return int(raw)
    return None


def signoff_batch_pytest_timeout_ceiling_sec(body_sec: int) -> int:
    """pytest-timeout for multi-scenario signoff batch legs (R81 + extended BODY)."""
    return (
        E2E_SIGNOFF_ADMIT_WALL_CLOCK_SEC
        + E2E_BOOTSTRAP_WALL_CLOCK_SEC_SIGNOFF
        + body_sec
        + E2E_TEARDOWN_WALL_CLOCK_SEC
    )


def signoff_pytest_timeout_ceiling_sec(joined_argv: str) -> int:
    """Signoff pytest-timeout ceiling; desktop leg reserves open/nav inside pytest."""
    batch_body = _parse_signoff_batch_body_sec(joined_argv)
    if batch_body is not None:
        return signoff_batch_pytest_timeout_ceiling_sec(batch_body)
    if CHROME_E2E_DESKTOP_MARKER in joined_argv:
        return SIGNOFF_DESKTOP_PYTEST_TIMEOUT_CEILING_SEC
    if _signoff_read_shpoib_leg(joined_argv):
        return SIGNOFF_READ_SHPOIB_PYTEST_TIMEOUT_CEILING_SEC
    return SIGNOFF_PYTEST_TIMEOUT_CEILING_SEC


def signoff_outer_kill_sec(joined_argv: str) -> int:
    """run_pytest_safe outer budget for signoff chrome_e2e legs."""
    batch_body = _parse_signoff_batch_body_sec(joined_argv)
    if batch_body is not None:
        return (
            signoff_batch_pytest_timeout_ceiling_sec(batch_body)
            + SIGNOFF_PYTEST_SAFE_BUFFER_SEC
        )
    if CHROME_E2E_DESKTOP_MARKER in joined_argv:
        return SIGNOFF_DESKTOP_OUTER_KILL_SEC
    if _signoff_read_shpoib_leg(joined_argv):
        return SIGNOFF_READ_SHPOIB_OUTER_KILL_SEC
    return SIGNOFF_OUTER_KILL_SEC


def chrome_e2e_pytest_safe_timeout_sec(
    lane: str,
    item_count: int,
    joined_argv: str = "",
) -> int:
    """Hard timeout for run_pytest_safe wrapper across a chrome_e2e session."""
    if resolve_e2e_wall_profile() == "signoff":
        return signoff_outer_kill_sec(joined_argv)
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
        return signoff_pytest_timeout_ceiling_sec(joined_argv)
    if CHROME_E2E_DESKTOP_MARKER in joined_argv:
        return CHROME_E2E_DESKTOP_TIMEOUT_SECONDS
    floor = chrome_e2e_pytest_timeout_for_lane(lane)
    shpoib = os.environ.get("E2E_PROFILE_SHPOIB", "").strip() == "1"
    normalized_lane = lane.strip().upper()
    if shpoib and normalized_lane in {"LIVE_AGENT", "READ"}:
        try:
            from transport_supervisor import live_agent_pytest_wall_cap_sec

            return max(floor, live_agent_pytest_wall_cap_sec(pessimistic_peers=True))
        except ImportError:
            return max(floor, LIVE_AGENT_PYTEST_WALL_CAP_SEC)
    return floor


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
