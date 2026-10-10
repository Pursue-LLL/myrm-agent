"""Pure restart-admission policy for the shared frontend dev server.

[INPUT]
  dev_gate.contract: measured cold-compile bound and the restart thresholds derived from it

[OUTPUT]
  Reason / Verdict / Observation / Decision / Policy / decide()

[POS]
  The single rule set deciding whether tooling may SIGTERM a running Next dev server.
  A slow server is not a dead server: heuristic restarts (probe timeouts, HTTP errors,
  orphan guesses) are admitted only on proof of a stall, never on probe latency alone.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum

from dev_gate.contract import (
    FRONTEND_RESTART_EPISODE_CAP_SEC,
    FRONTEND_RESTART_GATE_WAIT_SEC,
    FRONTEND_RESTART_MIN_AGE_SEC,
    FRONTEND_RESTART_STALL_SEC,
)


class Reason(Enum):
    # Deterministic: the caller holds hard evidence or the operator asked for it.
    RESET = "reset"
    PAUSE = "pause"
    BINDING_MISMATCH = "binding_mismatch"
    PANIC_RESIDUE = "panic_residue"
    # Heuristic: inferred from probes that a busy server also fails.
    UNRESPONSIVE = "unresponsive"
    BAD_HTTP = "bad_http"
    ORPHAN = "orphan"
    CLIENT_HOT_NO = "client_hot_no"

    @property
    def deterministic(self) -> bool:
        return self in _DETERMINISTIC


_DETERMINISTIC = frozenset(
    {Reason.RESET, Reason.PAUSE, Reason.BINDING_MISMATCH, Reason.PANIC_RESIDUE}
)


class Verdict(Enum):
    ALLOW = "allow"
    HEALTHY = "healthy"
    DENY = "deny"


@dataclass(frozen=True)
class Observation:
    process_alive: bool
    http_status: int
    age_sec: float | None
    stalled: bool
    episode_sec: float


@dataclass(frozen=True)
class Decision:
    verdict: Verdict
    rule: str
    detail: str = ""


@dataclass(frozen=True)
class Policy:
    tick_sec: float
    wait_sec: float
    stall_sec: float
    min_age_sec: float
    episode_cap_sec: float
    episode_gap_sec: float
    cpu_growth_eps_sec: float
    http_timeout_sec: float

    @classmethod
    def from_env(cls) -> Policy:
        return cls(
            tick_sec=_env_float("MYRM_FRONTEND_GATE_TICK_SEC", 5.0),
            wait_sec=_env_float(
                "MYRM_FRONTEND_GATE_WAIT_SEC", FRONTEND_RESTART_GATE_WAIT_SEC
            ),
            stall_sec=_env_float(
                "MYRM_FRONTEND_GATE_STALL_SEC", FRONTEND_RESTART_STALL_SEC
            ),
            min_age_sec=_env_float(
                "MYRM_FRONTEND_GATE_MIN_AGE_SEC", FRONTEND_RESTART_MIN_AGE_SEC
            ),
            episode_cap_sec=_env_float(
                "MYRM_FRONTEND_GATE_EPISODE_CAP_SEC", FRONTEND_RESTART_EPISODE_CAP_SEC
            ),
            # An episode only spans observations that follow each other closely;
            # a long silence means the server recovered in between.
            episode_gap_sec=_env_float("MYRM_FRONTEND_GATE_EPISODE_GAP_SEC", 120.0),
            cpu_growth_eps_sec=_env_float("MYRM_FRONTEND_GATE_CPU_EPS_SEC", 1.0),
            http_timeout_sec=_env_float("MYRM_FRONTEND_GATE_HTTP_TIMEOUT_SEC", 8.0),
        )


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return float(default)
    try:
        value = float(raw)
    except ValueError:
        return float(default)
    return value if value > 0 else float(default)


def decide(reason: Reason, obs: Observation, policy: Policy) -> Decision:
    """Admit or refuse killing the running frontend. Order encodes precedence."""
    if reason.deterministic:
        return Decision(Verdict.ALLOW, f"deterministic:{reason.value}")
    if not obs.process_alive:
        return Decision(Verdict.ALLOW, "no_live_process", "nothing to protect")
    if obs.http_status == 200:
        # Includes CLIENT_HOT_NO: a restart clears the hydration record itself, so killing a
        # serving server never produces the hot client the caller is missing.
        return Decision(
            Verdict.HEALTHY, "http_200", "server answers GET / — restart refused"
        )
    if obs.age_sec is not None and obs.age_sec < policy.min_age_sec:
        return Decision(Verdict.DENY, "young", f"age={obs.age_sec:.0f}s")
    if obs.episode_sec >= policy.episode_cap_sec:
        return Decision(
            Verdict.ALLOW, "episode_cap", f"unhealthy for {obs.episode_sec:.0f}s"
        )
    if obs.stalled:
        return Decision(
            Verdict.ALLOW, "stalled", f"no progress for {policy.stall_sec:.0f}s"
        )
    return Decision(Verdict.DENY, "progressing", f"http={obs.http_status}")
