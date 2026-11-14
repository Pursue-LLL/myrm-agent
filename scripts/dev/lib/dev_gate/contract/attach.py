"""Attach, launch-check and frontend-heal budgets, and the host-load scaling they share."""

from __future__ import annotations

import os
from typing import Final

from dev_gate.contract import parallel_pressure
from dev_gate.contract.wall_clock import E2E_ADMISSION_WALL_CLOCK_SEC, E2E_SIGNOFF_ADMIT_WALL_CLOCK_SEC, is_e2e_signoff_runtime

E2E_ATTACH_FRONTEND_MS: Final[int] = 90_000
E2E_ATTACH_CDP_GRACE_SEC: Final[float] = 30.0

# launch-check / test.sh readiness subprocess wall — scales under parallel attach.
E2E_LAUNCH_CHECK_WALL_SOLO_SEC: Final[float] = 45.0
E2E_LAUNCH_CHECK_WALL_LEASE_SCALE_SEC: Final[float] = 15.0
E2E_LAUNCH_CHECK_WALL_MAX_SEC: Final[float] = 180.0

SHARED_ATTACH_RECOVERY_WAIT_SEC: Final[int] = 360
# contract: attach recovery must cover a full frontend heal cycle
# (STACK_FRONTEND_ATTACH_HEAL_ENSURE_WAIT_SEC=360). The previous 20s cap made
# parallel attach fail before ui-heal could restore a cold-compiling frontend
# (regression vs"≥ heal+120"; dogpile is solved by flock, not by cap).
# attach UI heal must cover frontend cold compile + post-ensure warm streak (not 72s).
# Measured 2026-09-17 with the Turbopack disk cache off: dev cold compile of `/` takes 85s–282s.
# `next.config.ts` enables the cache by default, but a first start, a poisoned-cache recovery and
# MYRM_DISABLE_TURBOPACK_DISK_CACHE=1 still pay the full cold compile, so the ensure subprocess budget
# must exceed the coldest observed compile or the heal leader SIGTERMs its own child mid-compile.
# This stays SSOT: no caller may hardcode a smaller subprocess_timeout_sec.
E2E_ATTACH_UI_HEAL_POST_ENSURE_FLOOR_SEC: Final[int] = 120
E2E_ATTACH_UI_HEAL_TIMEOUT_FLOOR_SEC: Final[int] = 300
E2E_ATTACH_UI_HEAL_TIMEOUT_CAP_SEC: Final[int] = 600
E2E_ATTACH_UI_HEAL_ENSURE_SUBPROCESS_CAP_SEC: Final[int] = 420
STACK_FRONTEND_ENSURE_WAIT_SEC: Final[int] = 180
STACK_FRONTEND_ATTACH_HEAL_ENSURE_WAIT_SEC: Final[int] = 360
# Frontend restart admission (frontend_lifecycle): a running Next dev server is killed only on
# proof of a stall, never because a probe was slow. Thresholds derive from the measured cold
# compile above so no budget can drift below what a healthy compile needs.
FRONTEND_COLD_COMPILE_MAX_SEC: Final[int] = 282
# Continuous non-200 for three coldest compiles means the server is wedged even if it burns CPU.
FRONTEND_RESTART_EPISODE_CAP_SEC: Final[int] = 3 * FRONTEND_COLD_COMPILE_MAX_SEC
# A process tree whose CPU time and log stay flat this long is stalled, not compiling.
FRONTEND_RESTART_STALL_SEC: Final[int] = 90
# A server younger than this is still booting; refuse to kill it.
FRONTEND_RESTART_MIN_AGE_SEC: Final[int] = 60
# One admission call may observe a progressing compile this long before refusing the restart.
FRONTEND_RESTART_GATE_WAIT_SEC: Final[int] = FRONTEND_COLD_COMPILE_MAX_SEC
# Physical-memory ceiling for the Next dev server's whole process tree (macOS phys_footprint, the
# figure Activity Monitor bills; Linux sums RSS). Turbopack keeps its module graph in memory, so a
# healthy tree grows with the number of compiled routes; past this the machine pages and every
# other tool on it slows down, so the supervisor restarts the tree instead (scripts/next-supervisor.ts).
FRONTEND_FOOTPRINT_LIMIT_MB: Final[int] = 10 * 1024
# Solo ADMIT attach: readiness + dev_servers + chrome_cdp + attach_health exceed 180s under cold UI.
READY_CHROME_ATTACH_WALL_SOLO_SEC: Final[int] = SHARED_ATTACH_RECOVERY_WAIT_SEC
# Parallel ADMIT attach: must cover one full frontend heal cycle.
READY_CHROME_ATTACH_WALL_PARALLEL_SEC: Final[int] = SHARED_ATTACH_RECOVERY_WAIT_SEC


def ready_chrome_attach_wall_sec(active_leases: int = 0) -> int:
    """Outer wall for ready.sh wrapping chrome-e2e-preflight.sh during ADMIT attach."""
    if max(active_leases, 0) > 0:
        return READY_CHROME_ATTACH_WALL_PARALLEL_SEC
    return READY_CHROME_ATTACH_WALL_SOLO_SEC


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


def attach_ui_heal_ensure_subprocess_sec(active_leases: int = 0) -> int:
    """Budget for the ``dev-stack.sh frontend-only ensure`` child inside the heal leader.

    Must exceed the coldest Turbopack dev compile plus the inner ensure wait, otherwise
    the leader kills a healthy in-flight compile (observed 282s compile vs a 90s budget)
    and enters a restart loop that never reaches HTTP 200. The outer wall is always at
    least as large as this budget, so bounding it cannot exceed the attach contract.
    """
    scaled = STACK_FRONTEND_ENSURE_WAIT_SEC + max(active_leases, 0) * 30
    return min(
        E2E_ATTACH_UI_HEAL_ENSURE_SUBPROCESS_CAP_SEC,
        max(E2E_ATTACH_UI_HEAL_TIMEOUT_FLOOR_SEC, scaled),
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


def _sync_probe_cdp_timeout_sec(*, live: bool = True) -> float:
    """SYNC_PROBE stays fail-fast (mux_max_attempts=0) but scales under parallel mux pressure."""
    base = 12.0 if live else 6.0
    peers = parallel_pressure.parallel_chrome_e2e_pressure()
    if peers >= 2:
        max_sec = 30.0 if live else 12.0
        return min(max_sec, base + peers * (4.0 if live else 2.0))
    return base


def e2e_launch_check_wall_sec(*, active_leases: int | None = None) -> float:
    """Readiness emit subprocess budget for launch-check and test.sh gate.

    Solo 45s; under parallel chrome_e2e pressure min(180, 45+peers×15)s so
    ``e2e_core.readiness emit`` is not falsely denied while peers hold the stack.
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
        active_leases if active_leases is not None else parallel_pressure.parallel_chrome_e2e_pressure()
    )
    if pressure <= 0:
        return E2E_LAUNCH_CHECK_WALL_SOLO_SEC
    scaled = (
        E2E_LAUNCH_CHECK_WALL_SOLO_SEC
        + pressure * E2E_LAUNCH_CHECK_WALL_LEASE_SCALE_SEC
    )
    return min(E2E_LAUNCH_CHECK_WALL_MAX_SEC, scaled)


def attach_ui_liveness_probe_timeout_sec() -> float:
    """Short shared-UI probe for LISTEN-but-hung / post-heal streak.

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
    pressure = parallel_pressure.parallel_chrome_e2e_pressure()
    if pressure <= 0:
        return 8.0
    return min(15.0, 8.0 + pressure * 2.0)


# A shared-UI probe that fails decides to restart the shared frontend, so a host that is merely
# busy must not be read as "half dead". Wave leases are not the only load source: a solo
# session on a host whose cores are already saturated sees the same seconds-long answers.
# Measured 2026-10-17 (12 cores): `/` answered HTTP 200 in 0.67s idle, 8.11s and 23.29s at
# load 55-65, while the old 8s cap aborted the probe and declared the UI stale.
ATTACH_UI_STALE_PROBE_BASE_SEC: Final[float] = 8.0
ATTACH_UI_STALE_PROBE_MAX_SEC: Final[float] = 30.0
# The "slow" band is a separate threshold on the same probe; it must stay under its budget.
ATTACH_UI_STALE_SLOW_BASE_SEC: Final[float] = 5.0
ATTACH_UI_STALE_SLOW_MAX_SEC: Final[float] = 25.0
# Load-per-core band the host governor already uses to downgrade browser/PRIVATE capacity.
HOST_LOAD_UPGRADE_RATIO: Final[float] = 0.55
HOST_LOAD_STALE_SCALE_MAX_RATIO: Final[float] = 1.50


def _host_load_ratio() -> float:
    """Load per core from the governed host snapshot; 0.0 when it cannot be read.

    The snapshot is the SSOT the browser/PRIVATE credit governor uses, so the probe
    budget and the capacity both react to one notion of "how busy is this host".
    """
    try:
        from e2e_core.host_resource_governor import collect_host_pressure_snapshot

        snapshot = collect_host_pressure_snapshot()
        return max(0.0, float(snapshot.load_avg_1m) / max(1, int(snapshot.cpu_count)))
    except (ImportError, OSError, AttributeError, RuntimeError, ValueError):
        return 0.0


def host_load_ratio() -> float:
    """Public load per core (0.0 when unreadable), shared by every load-scaled E2E budget."""
    return _host_load_ratio()


def load_scaled_budget_sec(base: float, maximum: float) -> float:
    """Scale a wall-clock budget from ``base`` up to ``maximum`` with the host load.

    One public entry point for every load-sensitive E2E budget, so a budget is not tuned in one layer while
    a sibling layer keeps a hard-coded value: a busy host answers slower (and the dev server needs longer
    to compile a cold chunk), and a fixed ceiling then aborts exactly when the work needed the most time.
    """
    ratio = _host_load_ratio()
    if ratio <= HOST_LOAD_UPGRADE_RATIO:
        return base
    span = (ratio - HOST_LOAD_UPGRADE_RATIO) / (
        HOST_LOAD_STALE_SCALE_MAX_RATIO - HOST_LOAD_UPGRADE_RATIO
    )
    return min(maximum, base + (maximum - base) * min(1.0, span))


def _stale_probe_scaled_sec(base: float, maximum: float) -> float:
    """Scale a stale-verdict threshold from ``base`` up to ``maximum`` with host load."""
    return load_scaled_budget_sec(base, maximum)


def attach_ui_stale_probe_timeout_sec() -> float:
    """Probe budget for the "is the shared UI stale?" verdict that may restart the frontend.

    Unlike the post-heal liveness streak, this probe decides whether a running Next dev
    server is killed, so it scales with host load: a busy host answers in seconds and a
    cap that aborts there forces a cold compile that is far more expensive than waiting.
    """
    override = os.environ.get("MYRM_E2E_ATTACH_UI_STALE_PROBE_TIMEOUT_SEC", "").strip()
    if override:
        try:
            value = float(override)
            if value > 0:
                return value
        except ValueError:
            pass
    return _stale_probe_scaled_sec(
        ATTACH_UI_STALE_PROBE_BASE_SEC, ATTACH_UI_STALE_PROBE_MAX_SEC
    )


def attach_ui_stale_slow_sec() -> float:
    """Wall-clock band above which a stale-probe answer counts as "still compiling".

    Scales on the same load band as ``attach_ui_stale_probe_timeout_sec`` and stays under it for
    every input, because both ends of the two ranges are ordered that way (8/30 over 5/25) — a
    test pins the invariant. An explicit ``MYRM_UI_HEAL_SLOW_SEC`` is an operator instruction and
    is honored as given.
    """
    override = os.environ.get("MYRM_UI_HEAL_SLOW_SEC", "").strip()
    if override:
        try:
            value = float(override)
            if value > 0:
                return value
        except ValueError:
            pass
    return _stale_probe_scaled_sec(
        ATTACH_UI_STALE_SLOW_BASE_SEC, ATTACH_UI_STALE_SLOW_MAX_SEC
    )


def attach_ui_probe_timeout_sec() -> float:
    """Shared UI HTTP probe timeout; scales under parallel chrome_e2e.

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
    pressure = parallel_pressure.parallel_chrome_e2e_pressure()
    if os.environ.get("MYRM_E2E_SHPOIB", "").strip() != "1":
        if pressure <= 0:
            return 8.0
        return min(210.0, 30.0 + pressure * 15.0)
    if pressure <= 0:
        return 8.0
    return min(25.0, 8.0 + pressure * 2.0)


def shared_ui_hydrate_wait_sec() -> int:
    """SHPOIB shared UI hydrate burst queue; dev ADMIT 900s."""
    override = os.environ.get("MYRM_E2E_SHARED_UI_HYDRATE_WAIT_SEC", "").strip()
    if override.isdigit() and int(override) > 0:
        return int(override)
    if is_e2e_signoff_runtime():
        return E2E_SIGNOFF_ADMIT_WALL_CLOCK_SEC
    return E2E_ADMISSION_WALL_CLOCK_SEC


SIGNOFF_ATTACH_PARALLEL_CAP_SEC: Final[int] = 420
