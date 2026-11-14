"""Wall-clock budgets of the four-phase E2E lifecycle (admit, bootstrap, body, teardown), the runtime predicates that
select them and the send-turn waits."""

from __future__ import annotations

import os
from typing import Final, Literal

E2eWallProfile = Literal["dev", "signoff"]

# Single LIVE chrome_e2e test wall-clock stall budget (fail-fast, not pytest floor).
LIVE_SINGLE_TEST_WALL_CLOCK_SEC: Final[int] = 600
# LIVE_AGENT body phase aligns with @pytest.mark.timeout(600) on chrome_e2e LIVE tests.
LIVE_AGENT_BODY_WALL_CLOCK_SEC: Final[int] = LIVE_SINGLE_TEST_WALL_CLOCK_SEC
# Multi-round HITL LIVE (delegate → subagent bash → subagent_approval → resume) exceeds 600s
# with real LLM; hung-reap cap when MYRM_E2E_HITL_MULTI_ROUND=1 (test.sh SSOT).
LIVE_AGENT_HITL_MULTI_ROUND_BODY_WALL_CLOCK_SEC: Final[int] = 900

_HITL_MULTI_ROUND_TEST_ID_MARKERS: Final[tuple[str, ...]] = (
    "test_subagent_interrupt_live_e2e",
    "test_subagent_approval_flow_chrome_e2e",
)


def hitl_multi_round_chrome_e2e_test_id(test_id: str | None) -> bool:
    """True for multi-round subagent HITL LIVE chrome_e2e (BODY cap 900s SSOT)."""
    if not test_id:
        return False
    normalized = test_id.replace("\\", "/")
    return any(marker in normalized for marker in _HITL_MULTI_ROUND_TEST_ID_MARKERS)


# signoff four-phase budgets (ADMIT/BOOTSTRAP independent from BODY 600s).
E2E_SIGNOFF_ADMIT_WALL_CLOCK_SEC: Final[int] = 300
E2E_BOOTSTRAP_WALL_CLOCK_SEC_DEV: Final[int] = 180
E2E_BOOTSTRAP_WALL_CLOCK_SEC_SIGNOFF: Final[int] = 240
# minimum bridge-hydrate + shared UI session reserve inside bootstrap wall.
E2E_BOOTSTRAP_BRIDGE_HYDRATE_RESERVE_SEC: Final[float] = 90.0
E2E_BOOTSTRAP_SHELL_MIN_SEC: Final[float] = 60.0
E2E_TEARDOWN_WALL_CLOCK_SEC: Final[int] = 30
# parallel burst SQLite lock + observed seal can exceed 60s; client must wait.
E2E_TEARDOWN_FINISH_CLIENT_TIMEOUT_SEC: Final[int] = 120
# Legacy alias: BODY budget for signoff quality gate (not queue+bootstrap merged).
SIGNOFF_LEG_MTB_SEC: Final[int] = LIVE_SINGLE_TEST_WALL_CLOCK_SEC
# pytest-timeout spans ADMIT+BOOTSTRAP fixtures + BODY (func_only=False); must not
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


def private_shpoib_runtime_active() -> bool:
    """True when pytest runs PRIVATE backend via SHPOIB (MYRM_E2E_SHPOIB or legacy alias)."""
    if os.environ.get("MYRM_E2E_EXECUTION_MODE", "").strip().upper() != "PRIVATE":
        return False
    return (
        os.environ.get("MYRM_E2E_SHPOIB", "").strip() == "1"
        or os.environ.get("E2E_PROFILE_SHPOIB", "").strip() == "1"
    )


# Unified E2E admission (UEA v3).
# lease/mux/SHPOIB bootstrap queue budget (separate from 600s body wall clock).
E2E_ADMISSION_WALL_CLOCK_SEC: Final[int] = 900

E2E_RUNTIME_HEAL_AGENT_PREFIXES: Final[tuple[str, ...]] = (
    "e2e-parent-",
    "myrm-test-e2e:",
    "goal-focus-",
    "execution-cache-",
)


def is_e2e_signoff_runtime() -> bool:
    """True when E2E_SIGNOFF=1 (desktop soak / signoff batch extended budgets)."""
    return os.environ.get("E2E_SIGNOFF", "").strip().lower() in _SIGNOFF_TRUTHY


# Beats PRIVATE_AGING (+1 per 60s) so E2E_SIGNOFF sessions queue ahead of parallel chrome_e2e.
E2E_SIGNOFF_PRIVATE_QUEUE_PRIORITY: Final[int] = 1000


def resolve_dev_gate_submit_priority() -> int:
    """Dev Gate submit priority for private_admission ordering."""
    if is_e2e_signoff_runtime():
        return E2E_SIGNOFF_PRIVATE_QUEUE_PRIORITY
    return 0


def is_desktop_soak_signoff_runtime() -> bool:
    """True when M3 desktop leg soak runs under signoff (parallel chrome_e2e)."""
    return (
        is_e2e_signoff_runtime()
        and os.environ.get("MYRM_E2E_DESKTOP_SOAK", "").strip() in _SIGNOFF_TRUTHY
    )


def signoff_effective_bootstrap_wall_sec() -> float:
    """Signoff bootstrap cap; explicit batch override only, never peer-scaled."""
    bootstrap_sec = float(E2E_BOOTSTRAP_WALL_CLOCK_SEC_SIGNOFF)
    batch_bootstrap_raw = os.environ.get(
        "MYRM_E2E_SIGNOFF_BATCH_BOOTSTRAP_SEC", ""
    ).strip()
    if batch_bootstrap_raw.isdigit():
        bootstrap_sec = max(bootstrap_sec, float(int(batch_bootstrap_raw)))
    return bootstrap_sec


def chrome_e2e_skips_signoff_private_preflight() -> bool:
    """Private SHPOIB preflight seed always runs (no API-only signoff bypass)."""
    return False


def resolve_e2e_wall_profile() -> E2eWallProfile:
    """Return dev or signoff lifecycle profile (both use four-phase budgets)."""
    return "signoff" if is_e2e_signoff_runtime() else "dev"


def formal_chrome_e2e_runtime_heal_agent(agent_id: str) -> bool:
    """True when agentId belongs to a formal chrome E2E parent session."""
    normalized = agent_id.strip()
    return any(
        normalized.startswith(prefix) for prefix in E2E_RUNTIME_HEAL_AGENT_PREFIXES
    )


# SendTurnContract: single evaluate budget (kickoff observe + API poll + margin).
# The observe window is the longest a new chat may take to commit its first assistant output
# (the user row is persisted after it). Real sends sealed in 10.8 to 45.3 s, the slowest under
# host load, so the window keeps about twice that; the page declares the same value as
# SEND_TURN_OBSERVE_MS in E2EChatBridge.tsx.
SEND_TURN_OBSERVE_SEC: Final[int] = 90
SEND_TURN_API_POLL_SEC: Final[int] = 60
# Cap on one message-list poll in the page (SEND_TURN_API_POLL_TIMEOUT_MS in E2EChatBridge.tsx);
# a poll that never answers would otherwise hold the observe loop until the Python wall.
SEND_TURN_API_POLL_TIMEOUT_SEC: Final[int] = 10
SEND_TURN_EVAL_RECV_SEC: Final[float] = float(
    SEND_TURN_OBSERVE_SEC + SEND_TURN_API_POLL_SEC + 10
)
SEND_TURN_PYTHON_WALL_SEC: Final[float] = SEND_TURN_EVAL_RECV_SEC + 10.0


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


def boot_mux_body_transport_gate_required() -> bool:
    """The mux scheduler owns physical dispatch; pytest has no second gate."""
    return False


def chrome_e2e_skips_shared_approval_preflight(*, lane: str, shpoib: bool) -> bool:
    """True when LIVE E2E uses SHPOIB private backend — skip shared backend approval preflight."""
    return lane == "LIVE_AGENT" and shpoib


def chrome_e2e_skips_attach_health_reprobe(
    *,
    chrome_attach: bool,
    api_only: bool = False,
) -> bool:
    """True when test.sh bootstrap already verified Chrome attach — skip pytest fixture reprobe."""
    if os.environ.get("MYRM_E2E_PHASE_C_BURST_SKIP_ATTACH", "").strip() == "1":
        return True
    return chrome_attach or api_only
