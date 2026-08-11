"""Dev Gate v2 contract SSOT for Chrome MCP E2E orchestration (product path).

[INPUT]
(无外部模块依赖，仅 os/typing 标准库)

[OUTPUT]
TRANSIENT_MUX_ERROR_TOKENS: transport 层瞬态错误子串元组（含 "Chrome MCP transport closed"）
BENIGN_CLEANUP_TOKENS: 清理阶段可忽略的错误子串元组
PAGE_OWNERSHIP_ERROR_TOKENS: page ownership 错误子串元组
MUX_* / LIVE_* 系列常量: 物理工作池、超时、pytest floor 等 SSOT
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

import ast
import os
import re
import time
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
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

# --- EvaluateIntent SSOT (§24 W3) ---


class EvaluateIntent(StrEnum):
    """CDP evaluate semantic intent — drives awaitPromise, timeout, MUX retry."""

    SYNC_PROBE = "sync_probe"
    BRIDGE_POLL = "bridge_poll"
    ROUTE_ATTACH = "route_attach"
    AGENT_SUBMIT = "agent_submit"
    NAV_HEAVY = "nav_heavy"


@dataclass(frozen=True)
class EvaluateBudget:
    await_promise: bool
    cdp_timeout_sec: float
    mux_max_attempts: int
    mux_recv_grace_sec: float


E2E_ATTACH_FRONTEND_MS: Final[int] = 90_000
E2E_ATTACH_CDP_GRACE_SEC: Final[float] = 30.0


def resolve_evaluate_budget(
    intent: EvaluateIntent,
    *,
    live: bool = True,
) -> EvaluateBudget:
    """Single SSOT for evaluate budgets — no scattered magic timeouts."""
    if intent is EvaluateIntent.SYNC_PROBE:
        return EvaluateBudget(
            await_promise=False,
            cdp_timeout_sec=12.0,
            mux_max_attempts=0,
            mux_recv_grace_sec=5.0,
        )
    if intent is EvaluateIntent.BRIDGE_POLL:
        return EvaluateBudget(
            await_promise=False,
            cdp_timeout_sec=45.0 if live else 15.0,
            mux_max_attempts=1,
            mux_recv_grace_sec=10.0,
        )
    if intent is EvaluateIntent.ROUTE_ATTACH:
        attach_sec = E2E_ATTACH_FRONTEND_MS / 1000.0 + E2E_ATTACH_CDP_GRACE_SEC
        return EvaluateBudget(
            await_promise=True,
            cdp_timeout_sec=attach_sec,
            mux_max_attempts=2,
            mux_recv_grace_sec=15.0,
        )
    if intent is EvaluateIntent.AGENT_SUBMIT:
        return EvaluateBudget(
            await_promise=True,
            cdp_timeout_sec=180.0,
            mux_max_attempts=2,
            mux_recv_grace_sec=15.0,
        )
    # NAV_HEAVY — aligned with W4 silk path operation budgets
    return EvaluateBudget(
        await_promise=False,
        cdp_timeout_sec=120.0,
        mux_max_attempts=1,
        mux_recv_grace_sec=20.0,
    )


# --- Parallel caps ---

# S2: single cap root — private credits, mux workers, and bootstrap slots derive here.
LIVE_SHPOIB_MAX_CONCURRENT: Final[int] = 4

DEFAULT_XDIST_WORKERS: Final[int] = 2
STRESS_XDIST_WORKERS: Final[int] = 4
DEFAULT_BOOTSTRAP_SLOTS: Final[int] = LIVE_SHPOIB_MAX_CONCURRENT
SHARED_BROWSER_WORKERS: Final[int] = LIVE_SHPOIB_MAX_CONCURRENT
MUX_COLD_ATTACH_SLOTS: Final[int] = SHARED_BROWSER_WORKERS
WAVE_EXPENSIVE_SESSION_SLOTS: Final[int] = MUX_COLD_ATTACH_SLOTS
MUX_COLD_ATTACH_TIMEOUT_MS: Final[int] = 30_000
CDMCP_MUX_REQUEST_TIMEOUT_MS_DEFAULT: Final[int] = 180_000
LEGACY_MUX_REQUEST_TIMEOUT_MS: Final[tuple[int, ...]] = (55_000, 65_000, 120_000)
# mux tools/list probe budget during attach/bootstrap (align chrome-e2e-preflight.sh).
MUX_RESPONSIVE_PROBE_BASE_SEC: Final[float] = 8.0
MUX_RESPONSIVE_PROBE_LEASE_SCALE_SEC: Final[float] = 3.0
MUX_RESPONSIVE_PROBE_MAX_SEC: Final[float] = 45.0
MUX_RESPONSIVE_PROBE_RETRY_ATTEMPTS: Final[int] = 3
# R275: launch-check / test.sh readiness subprocess wall — scales under parallel attach.
E2E_LAUNCH_CHECK_WALL_SOLO_SEC: Final[float] = 45.0
E2E_LAUNCH_CHECK_WALL_LEASE_SCALE_SEC: Final[float] = 15.0
E2E_LAUNCH_CHECK_WALL_MAX_SEC: Final[float] = 180.0
# R170: bootstrap provider readiness gate scales under parallel (align desktop runner 180s).
PROVIDER_READINESS_GATE_BASE_SEC: Final[float] = 60.0
PROVIDER_READINESS_GATE_LEASE_SCALE_SEC: Final[float] = 15.0
PROVIDER_READINESS_GATE_MAX_SEC: Final[float] = 180.0
# R214: desktop leg soak — shared :8080 config_load_timeout under parallel chrome_e2e.
PROVIDER_READINESS_GATE_DESKTOP_SOAK_LEASE_SCALE_SEC: Final[float] = 40.0
PROVIDER_READINESS_GATE_DESKTOP_SOAK_MAX_SEC: Final[float] = 480.0
# Physical work is bounded; logical shared sessions are deliberately unlimited.
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
# R285: parallel burst SQLite lock + observed seal can exceed 60s; client must wait.
E2E_TEARDOWN_FINISH_CLIENT_TIMEOUT_SEC: Final[int] = 120
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
# LIVE WebUI turns (TURN_WAIT_SEC=300) may legitimately stall snapshot progress >90s.
LIVE_AGENT_STALL_PROGRESS_FLOOR_SEC: Final[int] = 240
# R281: M3 signoff desktop wait_shell_layout may block on mux evaluate >90s even solo.
SIGNOFF_STALL_PROGRESS_FLOOR_SEC: Final[int] = 150
# Watchdog: expire heartbeat-stale leases (display stale remains STALL_PROGRESS_SEC).
E2E_STALE_HEARTBEAT_REAP_SEC: Final[int] = 45


def private_shpoib_runtime_active() -> bool:
    """True when pytest runs PRIVATE backend via SHPOIB (MYRM_E2E_SHPOIB or legacy alias)."""
    if os.environ.get("MYRM_E2E_EXECUTION_MODE", "").strip().upper() != "PRIVATE":
        return False
    return (
        os.environ.get("MYRM_E2E_SHPOIB", "").strip() == "1"
        or os.environ.get("E2E_PROFILE_SHPOIB", "").strip() == "1"
    )


def shpoib_parallel_stall_progress_sec(
    *,
    lane: str | None = None,
    workload: str | None = None,
) -> float:
    """Scale BODY progress-stale cap under parallel SHPOIB load (R124).

    Matches file_write LIVE scaling: base 90s + 10s per active wave lease (max 150s).
    LIVE_AGENT/RESOURCE_WRITE: floor 240s (LLM turn wait) + 30s/lease (max 360s).
    R219/R281: signoff (incl. desktop soak) extends cap for wait_shell_layout mux evaluate.

    Coordinator hung-reap must pass lane/workload from session snapshot — not its own env.
    """
    base = float(STALL_PROGRESS_SEC)
    lane_val = (lane or os.environ.get("MYRM_E2E_LANE", "")).strip().upper()
    workload_val = (workload or os.environ.get("MYRM_E2E_WORKLOAD", "")).strip().upper()
    is_live_lane = (
        lane_val in {"LIVE_AGENT", "RESOURCE_WRITE"} or workload_val == "LIVE"
    )
    if is_live_lane:
        base = max(base, float(LIVE_AGENT_STALL_PROGRESS_FLOOR_SEC))
    active_leases = 0
    try:
        from pathlib import Path

        from stack_mutation_policy import wave_active_lease_count

        monorepo_root = Path(__file__).resolve().parents[4]
        active_leases = wave_active_lease_count(monorepo_root)
    except (ImportError, OSError, RuntimeError, ValueError):
        active_leases = 0
    if is_e2e_signoff_runtime():
        load = max(active_leases, _parallel_signoff_pressure_peers())
        scaled = base + load * 15.0
        return min(240.0, max(float(SIGNOFF_STALL_PROGRESS_FLOOR_SEC), scaled))
    if os.environ.get("MYRM_E2E_SHPOIB", "").strip() != "1":
        return base
    if active_leases < 2:
        return base
    if is_live_lane:
        return min(360.0, base + active_leases * 30.0)
    return min(150.0, base + active_leases * 10.0)


def shell_probe_stall_fail_fast_effective_sec() -> float:
    """Scale skeleton/blank shell fail-fast under parallel signoff desktop soak (R223)."""
    base = float(SHELL_PROBE_STALL_FAIL_FAST_SEC)
    if not (
        is_desktop_soak_signoff_runtime()
        or os.environ.get("E2E_SIGNOFF", "").strip() == "1"
    ):
        return base
    try:
        from cdp_chat_support import signoff_parallel_force_chat_timeout_sec

        return signoff_parallel_force_chat_timeout_sec(base)
    except ImportError:
        return base


def mux_reset_after_orphan_timeout_sec() -> float:
    """Scale asyncio wait_for around reset_after_orphan under parallel mux load (R142).

    v9 died at hardcoded 90s while peers≥6; align with shpoib_parallel_stall scaling.
    R215: desktop leg soak extends cap to 300s under parallel chrome_e2e.
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
        scaled = base
    else:
        scaled = min(180.0, base + active_leases * 10.0)
    if (
        os.environ.get("MYRM_E2E_DESKTOP_SOAK", "").strip() in _SIGNOFF_TRUTHY
        and is_e2e_signoff_runtime()
    ):
        load = max(active_leases, _parallel_signoff_pressure_peers())
        desktop_scaled = base + load * 20.0
        return min(300.0, max(scaled, desktop_scaled))
    if is_e2e_signoff_runtime():
        # R224/R228: parallel signoff post-SEND_TURN attach needs mux reclaim headroom (v146 @45s, v153 @180s).
        peers = max(active_leases, _parallel_signoff_pressure_peers())
        if peers >= 2:
            return min(300.0, max(scaled, 60.0 + peers * 15.0))
        return min(scaled, 60.0)
    return scaled


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
# R58: lease/mux/SHPOIB bootstrap queue budget (separate from 600s body wall clock).
E2E_ADMISSION_WALL_CLOCK_SEC: Final[int] = 900
# R122: attach crash-heal try-lock; defer instead of 180s×N dogpile under parallel attach.
E2E_ATTACH_CRASH_HEAL_FLOCK_WAIT_SEC: Final[float] = 5.0
SHARED_ATTACH_RECOVERY_WAIT_SEC: Final[int] = 360
# R161 contract: attach recovery must cover a full frontend heal cycle
# (STACK_FRONTEND_ATTACH_HEAL_ENSURE_WAIT_SEC=360). The previous 20s cap made
# parallel attach fail before ui-heal could restore a cold-compiling frontend
# (regression vs R161 "≥ heal+120"; R122 dogpile is solved by flock, not by cap).
# R132: attach UI heal must cover frontend cold compile + post-ensure warm streak (not 72s).
E2E_ATTACH_UI_HEAL_POST_ENSURE_FLOOR_SEC: Final[int] = 120
E2E_ATTACH_UI_HEAL_TIMEOUT_FLOOR_SEC: Final[int] = 300
E2E_ATTACH_UI_HEAL_TIMEOUT_CAP_SEC: Final[int] = 600
STACK_FRONTEND_ENSURE_WAIT_SEC: Final[int] = 180
STACK_FRONTEND_ATTACH_HEAL_ENSURE_WAIT_SEC: Final[int] = 360


def attach_ui_heal_post_ensure_max_sec(active_leases: int = 0) -> int:
    """Post-ensure warm streak cap after attach frontend heal leader returns."""
    scaled = 60 + max(active_leases, 0) * 12
    return max(E2E_ATTACH_UI_HEAL_POST_ENSURE_FLOOR_SEC, scaled)


def attach_ui_heal_timeout_sec(active_leases: int = 0) -> int:
    """Outer timeout for frontend-warmup-heal-entry.sh during parallel ADMIT attach."""
    post = attach_ui_heal_post_ensure_max_sec(active_leases)
    total = STACK_FRONTEND_ATTACH_HEAL_ENSURE_WAIT_SEC + post + 60
    return min(
        E2E_ATTACH_UI_HEAL_TIMEOUT_CAP_SEC,
        max(E2E_ATTACH_UI_HEAL_TIMEOUT_FLOOR_SEC, total),
    )


def attach_parallel_wait_sec(
    active_leases: int = 0, *, base: int = SHARED_ATTACH_RECOVERY_WAIT_SEC
) -> int:
    """Bound attach recovery independently from logical SHARED session count.

    PRIVATE capacity waiting happens before bootstrap. Once admitted, both modes use
    the same shared frontend/Chrome recovery SLO; peer count must never enlarge it.
    """
    del active_leases
    cap = SHARED_ATTACH_RECOVERY_WAIT_SEC
    cap_raw = os.environ.get("MYRM_CHROME_E2E_ATTACH_WAIT_CAP_SEC", "").strip()
    if cap_raw.isdigit() and int(cap_raw) > 0:
        cap = min(cap, int(cap_raw))
    return max(1, min(max(1, base), cap))


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


# Beats PRIVATE_AGING (+1 per 60s) so signoff clarifies ahead of parallel chrome_e2e.
E2E_SIGNOFF_PRIVATE_QUEUE_PRIORITY: Final[int] = 1000


def resolve_dev_gate_submit_priority() -> int:
    """Dev Gate submit priority for private_admission ordering."""
    if is_e2e_signoff_runtime():
        return E2E_SIGNOFF_PRIVATE_QUEUE_PRIORITY
    return 0


def is_e2e_signoff_clarify_api_runtime() -> bool:
    """True when signoff clarify leg runs API-only contract (R66, no chrome bootstrap)."""
    return (
        is_e2e_signoff_runtime()
        and os.environ.get("MYRM_E2E_SIGNOFF_CLARIFY_API", "").strip().lower()
        in _SIGNOFF_TRUTHY
    )


def is_desktop_soak_signoff_runtime() -> bool:
    """True when M3 desktop leg soak runs under signoff (parallel chrome_e2e)."""
    return (
        is_e2e_signoff_runtime()
        and os.environ.get("MYRM_E2E_DESKTOP_SOAK", "").strip() in _SIGNOFF_TRUTHY
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
        from e2e_session_runtime.registry import list_live_e2e_sessions

        pressure = max(pressure, len(list_live_e2e_sessions()))
    except (ImportError, OSError, RuntimeError, ValueError):
        pass
    return max(0, pressure)


def e2e_launch_check_wall_sec(*, active_leases: int | None = None) -> float:
    """Readiness emit subprocess budget for launch-check and test.sh gate (R275).

    Solo 45s; under parallel chrome_e2e pressure min(180, 45+peers×15)s so
    ``e2e_readiness emit`` is not falsely denied while peers hold the stack.
    """
    raw = os.environ.get("E2E_LAUNCH_CHECK_WALL_SEC", "").strip()
    if raw:
        try:
            parsed = float(raw)
        except ValueError:
            parsed = 0.0
        if parsed > 0:
            return parsed
    pressure = (
        active_leases if active_leases is not None else _parallel_chrome_e2e_pressure()
    )
    if pressure <= 0:
        return E2E_LAUNCH_CHECK_WALL_SOLO_SEC
    scaled = (
        E2E_LAUNCH_CHECK_WALL_SOLO_SEC
        + pressure * E2E_LAUNCH_CHECK_WALL_LEASE_SCALE_SEC
    )
    return min(E2E_LAUNCH_CHECK_WALL_MAX_SEC, scaled)


def mux_responsive_probe_timeout_sec(*, active_leases: int | None = None) -> float:
    """tools/list probe budget for mux stamp validation (preflight + test.sh SSOT).

    Solo 8s; under parallel wave load min(45, 8+leases×3)s — matches
    chrome-e2e-preflight.sh ``_mux_probe_timeout_sec``.
    """
    leases = (
        active_leases
        if active_leases is not None
        else _wave_active_lease_count_for_mux()
    )
    if leases <= 0:
        return MUX_RESPONSIVE_PROBE_BASE_SEC
    scaled = (
        MUX_RESPONSIVE_PROBE_BASE_SEC + leases * MUX_RESPONSIVE_PROBE_LEASE_SCALE_SEC
    )
    return min(MUX_RESPONSIVE_PROBE_MAX_SEC, scaled)


def signoff_wave_open_wait_sec() -> int:
    """R204: bounded wait when parallel pytest holds wave with foreign runtimeId."""
    if not is_e2e_signoff_runtime():
        return 0
    return E2E_ADMISSION_WALL_CLOCK_SEC


def signoff_stack_recovery_admit_budget_sec(
    *,
    active_leases: int | None = None,
) -> int:
    """R211: ADMIT fail-fast cap must cover E2E_SHARED_STACK_RECOVERY_WAIT (R207/R164).

    Stack recovery uses attach_parallel_wait_sec; solo admit cap (300–480s) must not
    trip E2E_WALL_BUDGET_FAIL_FAST while recovery still has budget (e.g. 240/660s).
    """
    if os.environ.get("E2E_SIGNOFF", "").strip() != "1":
        return E2E_SIGNOFF_ADMIT_WALL_CLOCK_SEC
    leases = (
        active_leases
        if active_leases is not None
        else _parallel_signoff_pressure_peers()
    )
    return attach_parallel_wait_sec(
        leases, base=SHARED_ATTACH_RECOVERY_WAIT_SEC
    )


def provider_readiness_gate_wait_sec(*, active_leases: int | None = None) -> float:
    """Bootstrap provider readiness poll budget (cdp bootstrap gate SSOT).

    Solo 60s; under parallel wave load min(180, 60+leases×15)s — aligns
    ``run_desktop_approval_chrome_e2e`` entry probe and avoids
    ``config_load_timeout`` flakes when shared :8080 is busy.
    """
    leases = (
        active_leases if active_leases is not None else _parallel_chrome_e2e_pressure()
    )
    if leases <= 0:
        return PROVIDER_READINESS_GATE_BASE_SEC
    scaled = (
        PROVIDER_READINESS_GATE_BASE_SEC
        + leases * PROVIDER_READINESS_GATE_LEASE_SCALE_SEC
    )
    base_result = min(PROVIDER_READINESS_GATE_MAX_SEC, scaled)
    if (
        os.environ.get("MYRM_E2E_DESKTOP_SOAK", "").strip() in _SIGNOFF_TRUTHY
        and is_e2e_signoff_runtime()
    ):
        load = max(leases, _parallel_signoff_pressure_peers())
        desktop_scaled = (
            PROVIDER_READINESS_GATE_BASE_SEC
            + load * PROVIDER_READINESS_GATE_DESKTOP_SOAK_LEASE_SCALE_SEC
        )
        return min(
            PROVIDER_READINESS_GATE_DESKTOP_SOAK_MAX_SEC,
            max(base_result, desktop_scaled),
        )
    return base_result


def provider_readiness_gate_effective_budget_sec(
    *,
    phase: str,
    remaining_wall_sec: float,
    bootstrap_cap: float,
) -> float:
    """Resolve provider gate wait budget (R217 desktop soak wall-starve fix).

    Under parallel chrome_e2e, open_mcp_page consumes bootstrap/body wall before
    cdp_bootstrap provider polling. Desktop soak must not clamp gate wait below
    ``provider_readiness_gate_wait_sec`` SSOT.
    """
    scaled = provider_readiness_gate_wait_sec()
    wall_cap = remaining_wall_sec if phase == "body" else bootstrap_cap
    if is_desktop_soak_signoff_runtime():
        wall_cap = max(wall_cap, scaled)
    return max(5.0, min(scaled, wall_cap))


def signoff_hitl_pin_max_attempts(*, active_leases: int | None = None) -> int:
    """HITL securityConfig pin retries under signoff parallel load (R195)."""
    base = 3
    if os.environ.get("E2E_SIGNOFF", "").strip() != "1":
        return base
    budget = provider_readiness_gate_wait_sec(active_leases=active_leases)
    return max(base, min(9, int(budget // 25) + base))


def signoff_hitl_pin_request_timeout_sec(*, active_leases: int | None = None) -> float:
    """Per-request timeout for HITL pin loopback calls under signoff (R195)."""
    if os.environ.get("E2E_SIGNOFF", "").strip() != "1":
        return 15.0
    budget = provider_readiness_gate_wait_sec(active_leases=active_leases)
    return min(45.0, max(15.0, budget / 5))


def attach_ui_liveness_probe_timeout_sec() -> float:
    """Short :3000 probe for LISTEN-but-hung / post-heal streak (R150).

    Never uses the 210s cold-compile budget — hung TCP must fail fast so parallel
    chrome_e2e does not block for hours on HTTP 000.
    """
    if os.environ.get("MYRM_E2E_ISOLATED", "").strip() == "1":
        return 10.0
    override = os.environ.get(
        "MYRM_E2E_ATTACH_UI_LIVENESS_PROBE_TIMEOUT_SEC", ""
    ).strip()
    if override:
        try:
            value = float(override)
            if value > 0:
                return value
        except ValueError:
            pass
    pressure = _parallel_chrome_e2e_pressure()
    if pressure <= 0:
        return 8.0
    return min(15.0, 8.0 + pressure * 2.0)


def attach_ui_probe_timeout_sec() -> float:
    """Shared :3000 HTTP probe timeout; scales under parallel chrome_e2e (R148).

    Solo 8s; under load min(25, 8+pressure×2)s for SHPOIB.
    READ shared-hot parallel + attach frontend heal allow cold compile (≤210s).
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
    if (
        os.environ.get("MYRM_E2E_ATTACH_FRONTEND_HEAL", "").strip() == "1"
        or os.environ.get("MYRM_CHROME_E2E_FRONTEND_HEAL", "").strip() == "1"
    ):
        return 210.0
    pressure = _parallel_chrome_e2e_pressure()
    if os.environ.get("MYRM_E2E_SHPOIB", "").strip() != "1":
        if pressure <= 0:
            return 8.0
        return min(210.0, 30.0 + pressure * 15.0)
    if pressure <= 0:
        return 8.0
    return min(25.0, 8.0 + pressure * 2.0)


_PARALLEL_SIGNOFF_PRESSURE_CACHE: tuple[float, int] | None = None


def _parallel_signoff_pressure_peers() -> int:
    """Cheap session-plane pressure for wall scaling; never live-probe mux here."""
    global _PARALLEL_SIGNOFF_PRESSURE_CACHE

    raw = os.environ.get("MYRM_E2E_PARALLEL_ACTIVE_COUNT", "").strip()
    if raw.isdigit():
        return max(0, int(raw))
    now = time.monotonic()
    if (
        _PARALLEL_SIGNOFF_PRESSURE_CACHE is not None
        and now - _PARALLEL_SIGNOFF_PRESSURE_CACHE[0] <= 2.0
    ):
        return _PARALLEL_SIGNOFF_PRESSURE_CACHE[1]
    # Wall-budget calculation is on the launch hot path. Wave leases are the
    # session SSOT; forcing mux/CDP status here made every helper subprocess
    # block for 10–20 seconds under load and multiplied admit latency.
    pressure = _wave_active_lease_count_for_mux()
    _PARALLEL_SIGNOFF_PRESSURE_CACHE = (now, max(0, pressure))
    return max(0, pressure)


def _scaled_parallel_admit_wait_sec(*, solo_base: int) -> int:
    """Parallel ADMIT/mux wait: min(900, solo_base + peers×45)."""
    pressure = _parallel_signoff_pressure_peers()
    if pressure <= 0:
        return solo_base
    scaled = solo_base + pressure * MUX_ADMISSION_WAIT_LEASE_SEC
    return min(E2E_ADMISSION_WALL_CLOCK_SEC, scaled)


def admit_wall_clock_sec() -> int:
    """Fixed ADMIT hard cap: PRIVATE ≤900s; formal signoff ≤300s.

    Parallel pressure is handled by explicit credits and queues. Extending this
    deadline with peer count hides stalls and violates the product contract.
    """
    if is_e2e_signoff_runtime():
        return E2E_SIGNOFF_ADMIT_WALL_CLOCK_SEC
    return E2E_ADMISSION_WALL_CLOCK_SEC


def signoff_read_shpoib_body_wall_sec() -> int:
    """Signoff BODY uses the same non-scalable 600s hard cap."""
    return LIVE_SINGLE_TEST_WALL_CLOCK_SEC


def signoff_effective_body_wall_sec() -> int:
    """Runtime signoff BODY hard cap; never scales with peers or workload."""
    return LIVE_SINGLE_TEST_WALL_CLOCK_SEC


DEV_GATE_SUBMIT_HARD_TIMEOUT_GRACE_SEC: Final[int] = 60


def dev_gate_post_admit_hard_timeout_sec() -> int:
    """PREPARING+ coordinator budget after PRIVATE admit grant (bootstrap + BODY + teardown).

    tools_panel log-8: grant used now+600 while bootstrap cap=990 + BODY=660 remained;
    HARD_DEADLINE @ ~709s from submit → PARENT_LEASE_NOT_ACTIVE during mux recovery.

    Submit/ADMIT paths must not call live mux snapshot (snapshot_mux_load force=True)
    — parallel chrome_e2e blocks on mux RPC and stalls dev_gate submit wrapper (R250).
    """
    bootstrap_sec = int(E2E_BOOTSTRAP_WALL_CLOCK_SEC_DEV)
    try:
        from transport_supervisor import (
            MUX_BOOTSTRAP_WALL_MAX_SEC,
            MUX_UPSTREAM_WAIT_MAX_SEC,
        )

        bootstrap_sec = int(MUX_BOOTSTRAP_WALL_MAX_SEC + MUX_UPSTREAM_WAIT_MAX_SEC)
    except ImportError:
        bootstrap_sec = int(E2E_BOOTSTRAP_WALL_CLOCK_SEC_DEV + MUX_UPSTREAM_WAIT_SEC)
    return (
        bootstrap_sec
        + LIVE_SINGLE_TEST_WALL_CLOCK_SEC
        + E2E_TEARDOWN_WALL_CLOCK_SEC
        + DEV_GATE_SUBMIT_HARD_TIMEOUT_GRACE_SEC
    )


def dev_gate_submit_hard_timeout_sec() -> int:
    """Coordinator hard_deadline offset from session submit (R249).

    Submit deadline must cover ADMIT queue + bootstrap + effective BODY + teardown.
    """
    if is_desktop_soak_signoff_runtime():
        body = signoff_effective_body_wall_sec()
        return (
            admit_wall_clock_sec()
            + E2E_BOOTSTRAP_WALL_CLOCK_SEC_SIGNOFF
            + body
            + E2E_TEARDOWN_WALL_CLOCK_SEC
            + DEV_GATE_SUBMIT_HARD_TIMEOUT_GRACE_SEC
        )
    if is_e2e_signoff_runtime():
        return (
            admit_wall_clock_sec()
            + SIGNOFF_PYTEST_TIMEOUT_CEILING_SEC
            + DEV_GATE_SUBMIT_HARD_TIMEOUT_GRACE_SEC
        )
    return admit_wall_clock_sec() + dev_gate_post_admit_hard_timeout_sec()


def dev_gate_teardown_finish_client_timeout_sec() -> int:
    """Socket + subprocess budget for teardown-finish under parallel SQLite contention."""
    return E2E_TEARDOWN_FINISH_CLIENT_TIMEOUT_SEC


def parallel_mux_cold_attach_drain_sec(*, parallel_peers: int | None = None) -> float:
    """Peers-scaled mux cold-attach drain budget (open_mcp_page + infra_retry SSOT).

    Signoff uses the same floor as dev (fixes historical 20s<45s inversion).
    """
    from transport_supervisor import mux_upstream_wait_cap

    peers = parallel_peers
    if peers is None:
        peers = _parallel_signoff_pressure_peers()
    base = 45.0
    scaled = base + max(0, int(peers)) * 12.0
    ceiling = float(mux_upstream_wait_cap())
    return min(max(base, scaled), ceiling)


# R97/R169: signoff READ SHPOIB open/rebind wall budgets (must precede stall-cap helpers).
SIGNOFF_OPEN_PAGE_LAYOUT_WAIT_SEC: Final[int] = 180
SIGNOFF_OPEN_PAGE_WALL_BUDGET_SEC: Final[int] = 240
SIGNOFF_OPEN_PAGE_TOTAL_BUDGET_SEC: Final[int] = 420
SIGNOFF_OPEN_PAGE_PARALLEL_WALL_CAP_SEC: Final[int] = 420
SIGNOFF_OPEN_PAGE_PARALLEL_TOTAL_CAP_SEC: Final[int] = 600


def _signoff_open_page_parallel_wall_cap() -> float:
    cap = float(SIGNOFF_OPEN_PAGE_PARALLEL_WALL_CAP_SEC)
    if os.environ.get("MYRM_E2E_DESKTOP_SOAK", "").strip() in _SIGNOFF_TRUTHY:
        cap = max(cap, 600.0)
    elif is_e2e_signoff_runtime():
        # R284: panel signoff legs hit join=420 HARD_DEADLINE under parallel mux (M3 v6).
        cap = max(cap, 540.0)
    return cap


def _signoff_open_page_parallel_total_cap() -> float:
    cap = float(SIGNOFF_OPEN_PAGE_PARALLEL_TOTAL_CAP_SEC)
    if os.environ.get("MYRM_E2E_DESKTOP_SOAK", "").strip() in _SIGNOFF_TRUTHY:
        cap = max(cap, 900.0)
    elif is_e2e_signoff_runtime():
        cap = max(cap, 780.0)
    return cap


@dataclass(frozen=True)
class SignoffOpenMcpBudgets:
    """SSOT for signoff open_mcp_page wall/total/attempts + hung-reap transport cap."""

    wall_budget_sec: float
    total_budget_sec: float
    attempt_count: int
    transport_stall_cap_sec: float
    layout_wait_sec: float = float(SIGNOFF_OPEN_PAGE_LAYOUT_WAIT_SEC)


def signoff_open_mcp_budgets(
    *, parallel_peers: int | None = None
) -> SignoffOpenMcpBudgets:
    """Single SSOT for signoff open_mcp budgets (chrome_mcp_e2e + stall_guard + hung-reap)."""
    peers = parallel_peers
    if peers is None:
        peers = _parallel_signoff_pressure_peers()
    wall_budget = float(SIGNOFF_OPEN_PAGE_WALL_BUDGET_SEC)
    total_budget = float(SIGNOFF_OPEN_PAGE_TOTAL_BUDGET_SEC)
    wall_cap = _signoff_open_page_parallel_wall_cap()
    total_cap = _signoff_open_page_parallel_total_cap()
    if peers >= 1:
        wall_budget = min(wall_budget + peers * 18.0, wall_cap)
        total_budget = min(total_budget + peers * 30.0, total_cap)
    body_ref = float(LIVE_SINGLE_TEST_WALL_CLOCK_SEC)
    if peers >= 4:
        attempts = 2
        per_attempt_cap = max(180.0, (body_ref * 0.45) / float(attempts))
    else:
        attempts = 3 if peers >= 3 else 2
        per_attempt_cap = max(120.0, (body_ref * 0.52) / float(attempts))
    total_budget = min(total_budget, per_attempt_cap)
    wall_ratio = 0.55
    wall_budget = min(
        wall_budget,
        per_attempt_cap * wall_ratio,
    )
    if peers >= 1:
        parallel_floor = 165.0 if peers < 4 else 240.0
        per_attempt_cap = max(per_attempt_cap, parallel_floor)
        total_budget = min(max(total_budget, parallel_floor), total_cap)
        wall_budget = min(max(wall_budget, parallel_floor * wall_ratio), wall_cap)
    body_frac = max(90.0, body_ref * 0.35)
    if peers >= 1:
        body_frac = min(body_frac + peers * 25.0, body_ref * 0.45)
    if peers < 1:
        stall_cap = per_attempt_cap + 30.0
    else:
        stall_cap = max(
            per_attempt_cap + 120.0,
            min(total_budget + 150.0, body_frac),
        )
    stall_cap = min(
        stall_cap,
        (
            720.0
            if os.environ.get("MYRM_E2E_DESKTOP_SOAK", "").strip() in _SIGNOFF_TRUTHY
            else 540.0
        ),
    )
    return SignoffOpenMcpBudgets(
        wall_budget_sec=wall_budget,
        total_budget_sec=total_budget,
        attempt_count=attempts,
        transport_stall_cap_sec=stall_cap,
    )


def signoff_bootstrap_open_mcp_budgets(
    *, parallel_peers: int | None = None
) -> SignoffOpenMcpBudgets:
    """R219/R222: bootstrap open_mcp budgets — SHPOIB/mux queue headroom, not BODY 35%."""
    peers = parallel_peers
    if peers is None:
        peers = _parallel_signoff_pressure_peers()
    pessimistic = peers >= 2
    from transport_supervisor import bootstrap_wall_cap_sec, mux_upstream_wait_cap

    boot = float(bootstrap_wall_cap_sec(pessimistic=pessimistic))
    mux = float(mux_upstream_wait_cap(pessimistic=pessimistic))
    effective_boot_wall = max(signoff_effective_bootstrap_wall_sec(), boot + mux)
    bootstrap_wall_cap = min(effective_boot_wall * 0.55, 540.0)
    bootstrap_total_cap = min(effective_boot_wall * 0.75, 720.0)
    wall_budget = min(
        bootstrap_wall_cap,
        max(float(SIGNOFF_OPEN_PAGE_WALL_BUDGET_SEC), boot + mux * 0.35),
    )
    total_budget = min(
        bootstrap_total_cap,
        max(float(SIGNOFF_OPEN_PAGE_TOTAL_BUDGET_SEC), boot + mux * 0.55),
    )
    if peers >= 1:
        wall_budget = min(
            max(wall_budget + peers * 18.0, boot + mux * 0.25),
            bootstrap_wall_cap,
        )
        total_budget = min(
            max(total_budget + peers * 30.0, boot + mux * 0.45),
            bootstrap_total_cap,
        )
    attempts = 2 if peers >= 4 else 3 if peers >= 3 else 2
    stall_cap = min(max(total_budget + mux * 0.25, boot + mux), bootstrap_total_cap)
    if os.environ.get("MYRM_E2E_DESKTOP_SOAK", "").strip() in _SIGNOFF_TRUTHY:
        attempts = max(attempts, 3)
        stall_cap = min(stall_cap * 1.25, bootstrap_total_cap * 1.1)
        total_budget = min(total_budget * 1.15, bootstrap_total_cap)
        wall_budget = min(wall_budget * 1.15, bootstrap_wall_cap)
    return SignoffOpenMcpBudgets(
        wall_budget_sec=wall_budget,
        total_budget_sec=total_budget,
        attempt_count=attempts,
        transport_stall_cap_sec=stall_cap,
    )


def signoff_new_page_join_timeout_sec(
    *,
    page_timeout_ms: int,
    parallel_peers: int | None = None,
) -> float:
    """R201/R208: signoff threaded new_page join — mux queue + page timeout headroom under parallel."""
    mux_grace = page_timeout_ms / 1000.0 + 5.0
    peers = parallel_peers
    if peers is None:
        peers = _parallel_signoff_pressure_peers()
    load = peers
    try:
        from transport_supervisor import parallel_mux_peer_count

        load = max(load, parallel_mux_peer_count())
    except ImportError:
        pass
    try:
        from mux_load import snapshot_mux_load

        snap = snapshot_mux_load()
        load = max(load, int(snap.mux_contexts), int(snap.wave_leases))
    except (ImportError, OSError, RuntimeError, TypeError, ValueError):
        pass
    if load < 1:
        solo = signoff_open_mcp_budgets(parallel_peers=0)
        base = max(mux_grace, solo.wall_budget_sec)
        return min(base, float(SIGNOFF_OPEN_PAGE_WALL_BUDGET_SEC))
    parallel_wall = min(
        float(SIGNOFF_OPEN_PAGE_WALL_BUDGET_SEC) + max(0, int(load)) * 18.0,
        _signoff_open_page_parallel_wall_cap(),
    )
    parallel_total = min(
        float(SIGNOFF_OPEN_PAGE_TOTAL_BUDGET_SEC) + max(0, int(load)) * 30.0,
        _signoff_open_page_parallel_total_cap(),
    )
    open_mcp_wall = signoff_open_mcp_budgets(
        parallel_peers=max(0, int(load)),
    ).wall_budget_sec
    # R206: join must survive open_mcp wall + mux grace (Run#6 desktop join=240s after open_mcp=231s).
    open_mcp_aligned = open_mcp_wall + mux_grace + 30.0
    base = max(mux_grace, parallel_wall, open_mcp_aligned)
    scaled = max(base, 120.0 + load * 15.0)
    floor = max(scaled, parallel_wall * 0.95, open_mcp_aligned)
    cap = min(
        max(floor, parallel_total * 0.55, open_mcp_aligned),
        _signoff_open_page_parallel_wall_cap(),
    )
    result = min(floor, cap)
    if is_e2e_signoff_runtime():
        if os.environ.get("MYRM_E2E_DESKTOP_SOAK", "").strip() in _SIGNOFF_TRUTHY:
            desktop_scaled = max(result, 540.0, 120.0 + load * 25.0)
            return min(desktop_scaled, _signoff_open_page_parallel_wall_cap())
        # R284: panel stdin legs under parallel mux (no desktop soak env).
        panel_scaled = max(result, 480.0, 120.0 + load * 22.0)
        return min(panel_scaled, _signoff_open_page_parallel_wall_cap())
    return result


def signoff_new_page_join_stall_abandon_sec(
    *,
    join_timeout_sec: float,
    parallel_peers: int | None = None,
) -> float:
    """R230: abandon hung threaded new_page early under parallel mux queue starvation."""
    peers = parallel_peers
    if peers is None:
        peers = _parallel_signoff_pressure_peers()
    base = 120.0 + max(0, int(peers)) * 20.0
    if os.environ.get("MYRM_E2E_DESKTOP_SOAK", "").strip() in _SIGNOFF_TRUTHY:
        base = max(base, 180.0)
    elif is_e2e_signoff_runtime():
        base = max(base, 240.0)
    stall_cap = 300.0
    if os.environ.get("MYRM_E2E_DESKTOP_SOAK", "").strip() in _SIGNOFF_TRUTHY:
        stall_cap = 420.0
    elif is_e2e_signoff_runtime():
        stall_cap = 360.0
    return min(join_timeout_sec, min(base, stall_cap))


def signoff_bootstrap_transport_stall_cap_sec(
    *,
    parallel_peers: int | None = None,
    page_timeout_ms: int = 90_000,
) -> float:
    """R206: bootstrap open_mcp stall cap — must cover R201 parallel new_page join.

    ``total_budget_sec`` is per-attempt open_mcp wall; transport stall must not be
    clamped below parallel-scaled threaded join (hung-reap + chrome_mcp_e2e SSOT).
    """
    budgets = signoff_bootstrap_open_mcp_budgets(parallel_peers=parallel_peers)
    join_floor = (
        signoff_new_page_join_timeout_sec(
            page_timeout_ms=page_timeout_ms,
            parallel_peers=parallel_peers,
        )
        + 10.0
    )
    return max(budgets.transport_stall_cap_sec, join_floor)


def signoff_open_page_transport_stall_cap_sec() -> float:
    """Signoff transport-node stall cap aligned with chrome_mcp_e2e open_mcp_page (R169)."""
    if not is_e2e_signoff_runtime():
        return float(NODE_STUCK_FAIL_FAST_SEC)
    return signoff_open_mcp_budgets().transport_stall_cap_sec


def live_open_page_transport_stall_cap_sec(*, active_peers: int | None = None) -> float:
    """R170/P0-G: hung-reap NODE_STUCK cap aligned with chrome_mcp open_mcp body fraction.

    log-11 @121s: peers<2 returned 120s while mux queue still draining — SIGKILL mid open_mcp.
    """
    peers = active_peers
    if peers is None:
        peers = 0
        try:
            from mux_load import (
                active_mux_context_count,
                read_mux_status,
                snapshot_mux_load,
            )

            mux_status = read_mux_status()
            load = snapshot_mux_load()
            peers = max(int(load.wave_leases), active_mux_context_count(mux_status))
        except (ImportError, OSError, RuntimeError, TypeError, ValueError):
            peers = 0
    try:
        from transport_supervisor import live_agent_body_wall_cap_sec

        body_cap = float(live_agent_body_wall_cap_sec())
    except ImportError:
        body_cap = float(LIVE_AGENT_BODY_WALL_CLOCK_SEC)
    body_frac = max(
        _OPEN_PAGE_BODY_FRACTION_FLOOR_SEC, body_cap * _OPEN_PAGE_BODY_FRACTION
    )
    drain_floor = float(parallel_mux_cold_attach_drain_sec(parallel_peers=peers))
    solo_floor = max(body_frac, drain_floor, float(NODE_STUCK_FAIL_FAST_SEC))
    if peers < 2:
        return solo_floor
    base = max(_OPEN_PAGE_BODY_FRACTION_FLOOR_SEC, body_cap * _OPEN_PAGE_BODY_FRACTION)
    return min(base + float(peers) * 25.0, body_cap * 0.45)


def is_admit_semantic_stall_node(node: str) -> bool:
    """True for ADMIT phase nodes eligible for node-level stall (below admit process wall)."""
    text = node.strip()
    if not text:
        return False
    return any(text.startswith(prefix) for prefix in ADMIT_SEMANTIC_STALL_NODE_PREFIXES)


def admit_semantic_node_stall_cap_sec(
    *,
    current_node: str,
    batch_mode: bool = False,
    signoff: bool = False,
) -> float:
    """Node-level ADMIT stall cap — releases credit before 900s process wall when stuck.

    E2E_ADMIT_TEST_SH (no sidecar) and batch parent holders must not block parallel
    queue for the full dev ADMIT wall while test.sh never writes a snapshot.
    """
    node = current_node.strip()
    if not is_admit_semantic_stall_node(node):
        return float(E2E_ADMISSION_WALL_CLOCK_SEC)
    uses_tight_cap = node == E2E_ADMIT_TEST_SH_NODE or (
        batch_mode and node.startswith("E2E_ADMIT_")
    )
    if not uses_tight_cap:
        if signoff:
            return float(admit_wall_clock_sec())
        return float(E2E_ADMISSION_WALL_CLOCK_SEC)
    base = float(
        ADMIT_BATCH_PARENT_STALL_CAP_DEV_SEC
        if batch_mode
        else ADMIT_TEST_SH_STALL_CAP_DEV_SEC
    )
    if signoff:
        peers = max(0, _parallel_signoff_pressure_peers())
        if peers >= 2:
            scaled = _scaled_parallel_admit_wait_sec(solo_base=int(base))
            return min(float(SIGNOFF_ATTACH_PARALLEL_CAP_SEC), scaled)
        return min(float(SIGNOFF_ATTACH_PARALLEL_CAP_SEC), base + 60.0)
    pressure = _parallel_chrome_e2e_pressure()
    if pressure >= 2:
        return min(480.0, base + float(pressure) * 45.0)
    return base


def resolve_transport_stall_cap_sec(*, current_node: str = "") -> float:
    """R170 SSOT: hung-reap / open_mcp NODE_STUCK cap (import fresh after reload)."""
    try:
        from e2e_stall_guard import is_transport_stall_node, transport_stall_cap_sec
    except ImportError:
        return float(NODE_STUCK_FAIL_FAST_SEC)
    transport = transport_stall_cap_sec()
    if not is_transport_stall_node(current_node):
        return transport
    open_page_family = current_node.startswith(
        "open_mcp_page"
    ) or current_node.startswith("open_page_")
    if is_e2e_signoff_runtime():
        if open_page_family:
            try:
                from mux_load import parallel_open_page_peer_count

                peers = parallel_open_page_peer_count(signoff=True)
            except ImportError:
                peers = 0
            bootstrap_cap = signoff_bootstrap_transport_stall_cap_sec(
                parallel_peers=peers,
            )
            body_cap = signoff_open_page_transport_stall_cap_sec()
            return max(transport, bootstrap_cap, body_cap)
        return max(transport, signoff_open_page_transport_stall_cap_sec())
    if open_page_family:
        live = live_open_page_transport_stall_cap_sec()
        try:
            from transport_supervisor import live_agent_body_wall_cap_sec

            body_cap = float(live_agent_body_wall_cap_sec())
        except ImportError:
            body_cap = float(LIVE_AGENT_BODY_WALL_CLOCK_SEC)
        body_frac = max(
            _OPEN_PAGE_BODY_FRACTION_FLOOR_SEC,
            body_cap * _OPEN_PAGE_BODY_FRACTION,
        )
        if live <= float(NODE_STUCK_FAIL_FAST_SEC):
            live = body_frac
        elif transport > float(NODE_STUCK_FAIL_FAST_SEC):
            peer_hint = max(
                2,
                int(round((transport - float(NODE_STUCK_FAIL_FAST_SEC)) / 22.0)),
            )
            live = max(
                live, live_open_page_transport_stall_cap_sec(active_peers=peer_hint)
            )
        return max(transport, live, body_frac)
    return transport


def shpoib_rebind_location_wait_cap_sec() -> float:
    """SHPOIB navigate location settle; signoff scales under parallel :3000 compile."""
    if not is_e2e_signoff_runtime():
        return 45.0
    base = float(SIGNOFF_SHPOIB_REBIND_LOCATION_WAIT_SEC)
    active_leases = _wave_active_lease_count_for_mux()
    if active_leases >= 2:
        scaled = base + active_leases * 20.0
        return min(float(SIGNOFF_OPEN_PAGE_PARALLEL_WALL_CAP_SEC), scaled)
    return base


def dev_bootstrap_wall_cap_for_hung_reap(*, lane: str, shpoib: bool) -> float:
    """R221/P0-D: hung-reap bootstrap cap must match resolve_budget_policy().bootstrap_sec."""
    bootstrap_sec = float(E2E_BOOTSTRAP_WALL_CLOCK_SEC_DEV)
    normalized_lane = lane.strip().upper()
    try:
        from transport_supervisor import bootstrap_wall_cap_sec, mux_upstream_wait_cap

        if boot_mux_body_transport_gate_required():
            bootstrap_sec = float(bootstrap_wall_cap_sec(pessimistic=True))
            bootstrap_sec += float(mux_upstream_wait_cap(pessimistic=True))
        elif shpoib or normalized_lane in {"LIVE_AGENT", "RESOURCE_WRITE"}:
            bootstrap_sec = float(bootstrap_wall_cap_sec(pessimistic=True))
            bootstrap_sec += float(mux_upstream_wait_cap(pessimistic=True))
        else:
            bootstrap_sec = float(bootstrap_wall_cap_sec())
    except ImportError:
        pass
    return bootstrap_sec


def signoff_effective_bootstrap_wall_sec() -> float:
    """Signoff bootstrap cap; explicit batch override only, never peer-scaled."""
    bootstrap_sec = float(E2E_BOOTSTRAP_WALL_CLOCK_SEC_SIGNOFF)
    batch_bootstrap_raw = os.environ.get(
        "MYRM_E2E_SIGNOFF_BATCH_BOOTSTRAP_SEC", ""
    ).strip()
    if batch_bootstrap_raw.isdigit():
        bootstrap_sec = max(bootstrap_sec, float(int(batch_bootstrap_raw)))
    return bootstrap_sec


def signoff_mux_transport_wait_budget_sec(
    *, bootstrap_phase: bool | None = None
) -> float:
    """R219/R221: pessimistic mux queue wait under signoff bootstrap parallel."""
    from transport_supervisor import mux_upstream_wait_cap

    pessimistic = False
    if is_e2e_signoff_runtime():
        if bootstrap_phase is None:
            try:
                from e2e_session_runtime.lifecycle import current_phase

                bootstrap_phase = current_phase() == "bootstrap"
            except ImportError:
                bootstrap_phase = False
        if bootstrap_phase and _parallel_signoff_pressure_peers() >= 2:
            pessimistic = True
    mux_cap = float(mux_upstream_wait_cap(pessimistic=pessimistic))
    if is_e2e_signoff_runtime() and bootstrap_phase:
        return max(mux_cap, signoff_effective_bootstrap_wall_sec() * 0.85)
    return mux_cap


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
# R118: harness import smoke under parallel signoff load (cold editable import).
SIGNOFF_CLARIFY_HARNESS_SMOKE_TIMEOUT_SEC: Final[int] = 180
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
SIGNOFF_DESKTOP_OPEN_NAV_WALL_TIMEOUT_SEC: Final[int] = (
    E2E_SIGNOFF_ADMIT_WALL_CLOCK_SEC * 3
)
# R177/R193: parallel signoff desktop — per-strategy wall (must match SIGNOFF_OPEN_PAGE_WALL_BUDGET_SEC).
SIGNOFF_DESKTOP_OPEN_NAV_PARALLEL_ATTEMPT_WALL_SEC: Final[int] = 240
# R91/R92: signoff open uses direct + direct_recover retries (see infra_retry strategies).
SIGNOFF_DESKTOP_OPEN_NAV_STRATEGY_COUNT: Final[int] = 3


def signoff_desktop_open_nav_attempt_wall_sec(*, parallel_peers: int) -> float:
    """Per-strategy asyncio wall for signoff desktop open/nav (R177).

    Solo signoff keeps the full mux-queue budget per attempt. Under parallel mux
    (peers≥2) use a shorter per-attempt wall so scoped attach restart runs between
    tries instead of one 900s new_page hang.
    """
    if parallel_peers >= 2:
        return float(SIGNOFF_DESKTOP_OPEN_NAV_PARALLEL_ATTEMPT_WALL_SEC)
    return float(SIGNOFF_DESKTOP_OPEN_NAV_WALL_TIMEOUT_SEC)


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
# R299: dev openPageTransaction whole-RPC wall — orchestrator daemon + client socket + hung-reap SSOT.
DEV_OPEN_PAGE_TRANSACTION_WALL_SEC: Final[float] = float(NODE_STUCK_FAIL_FAST_SEC)
E2E_NODE_STUCK_TOKEN: Final[str] = "E2E_NODE_STUCK"
E2E_BODY_WALL_EXCEEDED_TOKEN: Final[str] = "E2E_BODY_WALL_EXCEEDED"
E2E_TRANSPORT_PROGRESS_TOKEN: Final[str] = "E2E_TRANSPORT_PROGRESS"
E2E_BOOTSTRAP_OPEN_MCP_EXCEEDED_TOKEN: Final[str] = "E2E_BOOTSTRAP_OPEN_MCP_EXCEEDED"
E2E_SIGNOFF_NEW_PAGE_JOIN_EXCEEDED_TOKEN: Final[str] = (
    "E2E_SIGNOFF_NEW_PAGE_JOIN_EXCEEDED"
)
SIGNOFF_ATTACH_WAIT_SEC: Final[int] = 120
SIGNOFF_ATTACH_PARALLEL_CAP_SEC: Final[int] = 420
TRANSPORT_STALL_NODE_PREFIXES: Final[tuple[str, ...]] = (
    "open_mcp_page_",
    "open_page_",
    "force_chat_shell_",
    "mux_",
    "bootstrap_",
    "bridge_",
    "E2E_BOOTSTRAP",
)
# R282: ADMIT semantic nodes — node-level stall below process admit_wall (900s dev).
ADMIT_SEMANTIC_STALL_NODE_PREFIXES: Final[tuple[str, ...]] = ("E2E_ADMIT_",)
E2E_ADMIT_TEST_SH_NODE: Final[str] = "E2E_ADMIT_TEST_SH"
ADMIT_TEST_SH_STALL_CAP_DEV_SEC: Final[int] = 180
ADMIT_BATCH_PARENT_STALL_CAP_DEV_SEC: Final[int] = 180
E2E_ADMIT_NODE_STUCK_TOKEN: Final[str] = "E2E_ADMIT_NODE_STUCK"
E2E_BOOTSTRAP_CREDIT_HOG_TOKEN: Final[str] = "E2E_BOOTSTRAP_CREDIT_HOG"
# Process-level cap: bootstrap holder blocks private_credit_queue (node hops reset node_elapsed).
BOOTSTRAP_CREDIT_HOG_PROCESS_CAP_SEC: Final[int] = 300
BOOTSTRAP_CREDIT_HOG_NODE_NAMES: Final[frozenset[str]] = frozenset(
    {
        "wait_for_state",
        "wait_for_react_e2e_bridge",
        "wait_for_shell_layout",
        "wait_for_shell_ready",
        "open_page_transaction",
    }
)
E2E_SHELL_SKELETON_STALL_TOKEN: Final[str] = "E2E_SHELL_SKELETON_STALL"
MUX_RECLAIM_STALL_TOKEN: Final[str] = "MUX_RECLAIM_STALL"
E2E_USER_CLOSED_TAB_TOKEN: Final[str] = "E2E_USER_CLOSED_TAB"
BROWSER_ORCHESTRATOR_REQUIRED_TOKEN: Final[str] = "BROWSER_ORCHESTRATOR_REQUIRED"
E2E_CHROME_MCP_ENTRY_DENIED_TOKEN: Final[str] = "E2E_CHROME_MCP_ENTRY_DENIED"
E2E_ORCHESTRATOR_LEASE_DENIED_TOKEN: Final[str] = "E2E_ORCHESTRATOR_LEASE_DENIED"
E2E_MUX_RECOVERY_REMOVED_TOKEN: Final[str] = "E2E_MUX_RECOVERY_REMOVED"
E2E_ORPHAN_BUDGET_EXCEEDED_TOKEN: Final[str] = "E2E_ORPHAN_BUDGET_EXCEEDED"
ORPHAN_BUDGET_FAIL_SEC: Final[float] = 30.0
ORPHAN_BUDGET_SLACK: Final[int] = 1
_OPEN_PAGE_BODY_FRACTION: Final[float] = 0.35
_OPEN_PAGE_BODY_FRACTION_FLOOR_SEC: Final[float] = 90.0
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
SIGNOFF_SHPOIB_REBIND_WALL_SEC: Final[int] = 300
SIGNOFF_SHPOIB_REBIND_LOCATION_WAIT_SEC: Final[int] = 120
# R90: desktop signoff spans open/nav reserve inside pytest (not quality-gate BODY).
SIGNOFF_DESKTOP_OUTER_KILL_SEC: Final[int] = (
    SIGNOFF_DESKTOP_PYTEST_TIMEOUT_CEILING_SEC + SIGNOFF_PYTEST_SAFE_BUFFER_SEC
)
READ_CHROME_E2E_PYTEST_TIMEOUT_SEC: Final[int] = (
    MUX_UPSTREAM_WAIT_SEC + MAX_PAGE_TIMEOUT_MS // 1000 + 90
)
LIVE_CHROME_E2E_PYTEST_TIMEOUT_SEC: Final[int] = (
    LIVE_AGENT_BODY_BUFFER_SEC + MAX_PAGE_TIMEOUT_MS // 1000 + 90
)
CHROME_E2E_BROWSER_TAKEOVER_PYTEST_TIMEOUT_SEC: Final[int] = (
    LIVE_CHROME_E2E_PYTEST_TIMEOUT_SEC
)


def chrome_e2e_session_lane_from_profile(*, access_scope: str, workload: str) -> str:
    """Map chrome_e2e profile fields to Wave session lane (SSOT with test.sh)."""
    scope = access_scope.strip().upper()
    wl = workload.strip().upper()
    if scope == "NAMESPACE_WRITE":
        return "RESOURCE_WRITE"
    if scope == "GLOBAL_WRITE":
        return "GLOBAL_WRITE"
    if wl == "STANDARD":
        return "READ"
    return "LIVE_AGENT"


def chrome_e2e_pytest_timeout_for_lane(lane: str) -> int:
    """Return pytest-timeout floor for a formal chrome_e2e session lane."""
    if lane.strip().upper() == "READ":
        return READ_CHROME_E2E_PYTEST_TIMEOUT_SEC
    return LIVE_CHROME_E2E_PYTEST_TIMEOUT_SEC


def boot_mux_body_transport_gate_required() -> bool:
    """The mux scheduler owns physical dispatch; pytest has no second gate."""
    return False


def phase_c_burst_lane_count() -> int:
    """Declared Phase C parallel burst width (MYRM_E2E_PHASE_C_BURST_LANES)."""
    raw = os.environ.get("MYRM_E2E_PHASE_C_BURST_LANES", "").strip()
    if not raw.isdigit():
        return 0
    return max(0, int(raw))


def phase_c_burst_read_bootstrap_wall_sec() -> int | None:
    """READ dev bootstrap wall when Phase C burst lanes declare parallel mux pressure."""
    burst_lanes = phase_c_burst_lane_count()
    if burst_lanes < 2:
        return None
    from transport_supervisor import caps_for_explicit_peer_count

    pessimistic = burst_lanes >= 4
    bootstrap, mux_wait = caps_for_explicit_peer_count(
        burst_lanes,
        pessimistic=pessimistic,
    )
    if burst_lanes >= 4:
        return bootstrap + mux_wait
    return bootstrap


def phase_c_burst_read_queue_buffer_sec() -> int:
    """run_pytest_safe queue buffer for Phase C READ burst (mux open_mcp_page queue)."""
    burst_lanes = phase_c_burst_lane_count()
    if burst_lanes < 4:
        return 0
    from transport_supervisor import caps_for_explicit_peer_count

    _, mux_wait = caps_for_explicit_peer_count(burst_lanes, pessimistic=True)
    return mux_wait


def chrome_e2e_pytest_safe_queue_buffer_sec(
    lane: str,
    joined_argv: str,
    *,
    shpoib: bool | None = None,
) -> int:
    """Queue/admission wait excluded from R58 body wall clock but counted by run_pytest_safe."""
    if resolve_e2e_wall_profile() == "signoff":
        return admit_wall_clock_sec()
    private_mode = (
        shpoib
        if shpoib is not None
        else os.environ.get("MYRM_E2E_EXECUTION_MODE", "").strip() == "PRIVATE"
    )
    if private_mode:
        return E2E_ADMISSION_WALL_CLOCK_SEC
    burst_buffer = phase_c_burst_read_queue_buffer_sec()
    if burst_buffer > 0 and lane.strip().upper() == "READ":
        return burst_buffer
    del joined_argv
    return 0


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


def _signoff_batch_body_sec(joined_argv: str) -> int | None:
    """Batch BODY override from argv marker or MYRM_E2E_SIGNOFF_BATCH_BODY_SEC (R179/R180)."""
    batch_body = _parse_signoff_batch_body_sec(joined_argv)
    if batch_body is not None:
        return batch_body
    batch_env = os.environ.get("MYRM_E2E_SIGNOFF_BATCH_BODY_SEC", "").strip()
    if batch_env.isdigit():
        return int(batch_env)
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
    batch_body = _signoff_batch_body_sec(joined_argv)
    if batch_body is not None:
        return signoff_batch_pytest_timeout_ceiling_sec(batch_body)
    if CHROME_E2E_DESKTOP_MARKER in joined_argv:
        return SIGNOFF_DESKTOP_PYTEST_TIMEOUT_CEILING_SEC
    if _signoff_read_shpoib_leg(joined_argv):
        return SIGNOFF_READ_SHPOIB_PYTEST_TIMEOUT_CEILING_SEC
    return SIGNOFF_PYTEST_TIMEOUT_CEILING_SEC


def signoff_outer_kill_sec(joined_argv: str) -> int:
    """run_pytest_safe outer budget for signoff chrome_e2e legs."""
    batch_body = _signoff_batch_body_sec(joined_argv)
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
        (normalized_count + SHARED_BROWSER_WORKERS - 1) // SHARED_BROWSER_WORKERS,
    )
    queue_buffer = chrome_e2e_pytest_safe_queue_buffer_sec(lane, joined_argv)
    return min(raw, wave_cap) + PYTEST_SAFE_BOOTSTRAP_BUFFER_SEC + queue_buffer


def parallel_live_pytest_timeout_floor_sec(base: int) -> int:
    """Extend pytest-timeout when parallel mux inflates in-test bootstrap (R124).

    Observed: leases=5 bootstrap mono_elapsed≈730s before BODY — 810s floor kills at REAPPLY.
    """
    try:
        from pathlib import Path

        from stack_mutation_policy import wave_active_lease_count

        load = wave_active_lease_count(Path(__file__).resolve().parents[4])
    except (ImportError, OSError, RuntimeError, ValueError):
        load = 0
    if load < 2:
        return base
    scaled = base + int(load) * 180
    return min(1830, max(base, scaled))


def parallel_ramp_pytest_timeout_override_sec() -> int | None:
    """Phase C parallel ramp raises READ solo floor (510s) for mux queue depth."""
    raw = os.environ.get("E2E_PARALLEL_RAMP_PYTEST_TIMEOUT_SEC", "").strip()
    if raw.isdigit() and int(raw) > 0:
        return int(raw)
    burst = os.environ.get("MYRM_E2E_PHASE_C_BURST_LANES", "").strip()
    if not burst.isdigit():
        return None
    lanes = int(burst)
    if lanes >= 16:
        return 1200
    if lanes >= 8:
        return 1200
    if lanes >= 4:
        return 1140
    if lanes >= 2:
        return 600
    return None


def chrome_e2e_pytest_timeout_floor(lane: str, joined_argv: str) -> int:
    """Lane floor with marker-aware overrides; SHPOIB admission runs inside pytest fixture."""
    if resolve_e2e_wall_profile() == "signoff":
        return signoff_pytest_timeout_ceiling_sec(joined_argv)
    if CHROME_E2E_DESKTOP_MARKER in joined_argv:
        return CHROME_E2E_DESKTOP_TIMEOUT_SECONDS
    floor = chrome_e2e_pytest_timeout_for_lane(lane)
    private_mode = os.environ.get("MYRM_E2E_EXECUTION_MODE", "").strip() == "PRIVATE"
    normalized_lane = lane.strip().upper()
    shpoib = private_shpoib_runtime_active()
    if private_mode and normalized_lane in {"LIVE_AGENT", "READ"}:
        floor = max(floor, LIVE_AGENT_PYTEST_WALL_CAP_SEC)
    elif private_mode and shpoib and normalized_lane == "RESOURCE_WRITE":
        floor = max(floor, LIVE_AGENT_PYTEST_WALL_CAP_SEC)
    ramp_override = parallel_ramp_pytest_timeout_override_sec()
    if ramp_override is not None:
        floor = max(floor, ramp_override)
    if normalized_lane in {"LIVE_AGENT", "RESOURCE_WRITE"}:
        floor = parallel_live_pytest_timeout_floor_sec(floor)
    return floor


def chrome_e2e_skips_shared_approval_preflight(*, lane: str, shpoib: bool) -> bool:
    """True when LIVE E2E uses SHPOIB private backend — skip shared :8080 approval preflight."""
    return lane == "LIVE_AGENT" and shpoib


def chrome_e2e_skips_attach_health_reprobe(
    *,
    chrome_attach: bool,
    api_only: bool = False,
) -> bool:
    """True when test.sh bootstrap already verified Chrome attach — skip pytest fixture reprobe."""
    return chrome_attach or api_only


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
_SERVER_E2E_ROOT = Path(__file__).resolve().parents[3] / "myrm-agent-server"


def _resolve_chrome_e2e_test_path(path_arg: str) -> Path | None:
    file_part = path_arg.split("::", 1)[0]
    prefixes = (
        "myrm-agent/myrm-agent-server/",
        "myrm-agent-server/",
    )
    rel = file_part
    for prefix in prefixes:
        if rel.startswith(prefix):
            rel = rel.removeprefix(prefix)
            break
    candidate = _SERVER_E2E_ROOT / rel
    if candidate.is_file():
        return candidate
    return None


def explicit_node_has_chrome_e2e_marker(path_arg: str) -> bool:
    """True when path_arg selects a test function decorated with pytest.mark.chrome_e2e."""
    if "::" not in path_arg:
        return True
    file_path = _resolve_chrome_e2e_test_path(path_arg)
    if file_path is None:
        return True
    test_name = path_arg.split("::", 1)[1]
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if node.name != test_name:
            continue
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call) and isinstance(
                decorator.func, ast.Attribute
            ):
                if decorator.func.attr == "chrome_e2e":
                    return True
        return False
    return False


def pytest_argv_needs_live_chrome_e2e(
    argv: tuple[str, ...],
    *,
    run_e2e_tests: bool = False,
) -> bool:
    """True when ./myrm test argv selects formal chrome_e2e (marker or *_chrome_e2e.py).

    Must not match unit-test node ids or -k filters that merely contain the substring
    ``chrome_e2e`` (R99 gate tests live under scripts/dev/tests/).

    Explicit ``*_chrome_e2e.py::test_name`` node ids without ``@pytest.mark.chrome_e2e``
    (integration-only signoff legs) do not require live Chrome attach / ADMIT.
    """
    next_is_marker = False
    chrome_paths: list[str] = []
    for arg in argv:
        if next_is_marker:
            next_is_marker = False
            if "chrome_e2e" in arg:
                return True
            continue
        if arg in {"-m", "--markers"}:
            next_is_marker = True
            continue
        if arg.startswith("-"):
            continue
        if _CHROME_E2E_PYTEST_FILE.search(arg):
            chrome_paths.append(arg)
    if chrome_paths:
        return any(
            explicit_node_has_chrome_e2e_marker(path_arg) for path_arg in chrome_paths
        )
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
