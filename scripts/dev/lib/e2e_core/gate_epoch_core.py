"""Gate epoch preflight core: outcome types, the solo-cluster snapshot and the flocked heal commands.

[INPUT]
- `e2e_core.api_verify::resolve_e2e_api_context`, `e2e_core.peer_count_ssot` peer counts (POS: SSOT for what is running on the shared stack)
- `e2e_core.stack_mutation_policy` backend-heal flock (POS: one backend heal at a time across sessions)

[OUTPUT]
- `PreflightOutcome` / `PreflightResult` / `SoloSnapshot`: the verdict types of the preflight
- `read_solo_snapshot()` / `solo_cluster_clear()` / `epoch_ready()`: whether the solo cluster is idle and the epoch matches
- `emit()` / `myrm_cmd()` / `run_heal_flocked()`: gate tokens on stdout and `./myrm-dev` commands run under the heal flock

[POS]
Dev gate layer only. Shared by `gate_epoch_chrome_heal.py`, `gate_epoch_ready.py` and `gate_epoch_preflight.py`; holds no heal policy of its own.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class PreflightOutcome(StrEnum):
    OK = "OK"
    DEFER = "DEFER"
    FAIL = "FAIL"


@dataclass(frozen=True, slots=True)
class SoloSnapshot:
    peers: int
    active_leases: int
    mux_peers: int
    epoch_match: bool
    blocked: bool
    drift_pending: bool


@dataclass(frozen=True, slots=True)
class PreflightResult:
    outcome: PreflightOutcome
    reason: str
    attempts: int = 0
    snapshot: SoloSnapshot | None = None
    tokens: tuple[str, ...] = field(default_factory=tuple)


def emit(token: str) -> None:
    print(token, flush=True)


def _read_api_context():
    from e2e_core.api_verify import resolve_e2e_api_context

    return resolve_e2e_api_context(retry_after_apply=False)


def read_solo_snapshot() -> SoloSnapshot:
    from e2e_core.peer_count_ssot import (
        chrome_e2e_pytest_peer_count,
        solo_gate_active_mux_peer_count,
    )

    ctx = _read_api_context()
    return SoloSnapshot(
        peers=chrome_e2e_pytest_peer_count(),
        active_leases=int(ctx.active_leases),
        mux_peers=solo_gate_active_mux_peer_count(),
        epoch_match=bool(ctx.epoch_match),
        blocked=bool(ctx.blocked),
        drift_pending=bool(ctx.drift_pending),
    )


def solo_cluster_clear(snapshot: SoloSnapshot) -> bool:
    return (
        snapshot.peers == 0 and snapshot.active_leases == 0 and snapshot.mux_peers <= 1
    )


def epoch_ready(snapshot: SoloSnapshot) -> bool:
    return snapshot.epoch_match and snapshot.active_leases == 0


def run_heal_flocked(
    cmd: list[str],
    *,
    wait_sec: float,
) -> int:
    from e2e_core.stack_mutation_policy import (
        default_backend_heal_flock_file,
        run_command_with_backend_heal_flock,
    )

    return run_command_with_backend_heal_flock(
        cmd=cmd,
        lock_file=default_backend_heal_flock_file(),
        wait_sec=wait_sec,
    )


def myrm_cmd(monorepo_root: Path, *parts: str) -> list[str]:
    """Developer CLI command line: `ready`, `restart` and `verify-api` live there, not in the user CLI."""
    return [str(monorepo_root / "myrm-dev"), *parts]
