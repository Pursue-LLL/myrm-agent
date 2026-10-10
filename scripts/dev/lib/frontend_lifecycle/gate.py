"""Restart admission gate: observe the running frontend, then allow or refuse the kill.

[INPUT]
  policy::decide / Policy, process_tree (ps/lsof), episode::EpisodeStore, journal::append

[OUTPUT]
  admit(): Decision after observing the server for up to ``policy.wait_sec``
  is_stalled(): pure stall test over CPU-time/log history

[POS]
  Choke point in front of every heuristic SIGTERM of the shared Next dev server. While the
  process tree keeps consuming CPU or writing its log it is compiling, however long a probe
  takes; the gate waits that out and reports HEALTHY the moment the server answers.
"""

from __future__ import annotations

import http.client
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from frontend_lifecycle import journal
from frontend_lifecycle.episode import EpisodeStore
from frontend_lifecycle.policy import (
    Decision,
    Observation,
    Policy,
    Reason,
    Verdict,
    decide,
)
from frontend_lifecycle.process_tree import (
    ProcSample,
    descendants,
    listener_pids,
    read_pid_file,
    snapshot,
)


@dataclass(frozen=True)
class GateContext:
    port: int
    url: str
    state_dir: Path
    pid_file: Path
    log_file: Path


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Report 3xx as-is, like ``curl -w %{http_code}`` (the stack's definition of healthy)."""

    def redirect_request(self, *_args: object, **_kwargs: object) -> None:
        return None


def http_status(url: str, timeout_sec: float) -> int:
    """HTTP status of GET ``url``; 0 when nothing answered in time."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    try:
        with opener.open(url, timeout=timeout_sec) as response:
            return int(response.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)
    except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError):
        return 0


def file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


@dataclass(frozen=True)
class Probes:
    """Side-effect boundary, replaceable in tests."""

    monotonic: Callable[[], float] = time.monotonic
    wall: Callable[[], float] = time.time
    sleep: Callable[[float], None] = time.sleep
    snapshot: Callable[[], dict[int, ProcSample]] = field(default=snapshot)
    listeners: Callable[[int], tuple[int, ...]] = field(default=listener_pids)
    http_status: Callable[[str, float], int] = field(default=http_status)
    log_size: Callable[[Path], int] = field(default=file_size)


@dataclass(frozen=True)
class _Sample:
    at: float
    cpu_by_pid: dict[int, float]
    log_bytes: int


def is_stalled(
    history: Sequence[_Sample], stall_sec: float, cpu_eps_sec: float
) -> bool:
    """True when the newest sample shows no CPU/log growth over the last ``stall_sec``.

    Needs a baseline at least ``stall_sec`` old, so a short observation never proves a
    stall. Children spawned after the baseline count with their whole CPU time.
    """
    if not history:
        return False
    newest = history[-1]
    baseline = next(
        (sample for sample in reversed(history) if newest.at - sample.at >= stall_sec),
        None,
    )
    if baseline is None:
        return False
    growth = sum(
        cpu - baseline.cpu_by_pid.get(pid, 0.0)
        for pid, cpu in newest.cpu_by_pid.items()
    )
    return growth < cpu_eps_sec and newest.log_bytes <= baseline.log_bytes


def _alive_roots(
    ctx: GateContext, probes: Probes, procs: dict[int, ProcSample]
) -> list[int]:
    candidates = list(probes.listeners(ctx.port))
    supervisor_pid = read_pid_file(ctx.pid_file)
    if supervisor_pid is not None:
        candidates.append(supervisor_pid)
    return sorted({pid for pid in candidates if pid in procs})


def admit(
    reason: Reason, ctx: GateContext, policy: Policy, probes: Probes | None = None
) -> Decision:
    """Decide whether the frontend on ``ctx.port`` may be killed for ``reason``."""
    probes = probes or Probes()
    if reason.deterministic:
        decision = decide(reason, Observation(True, 0, None, False, 0.0), policy)
        _record(ctx, reason, decision, None, 0.0)
        return decision

    episodes = EpisodeStore(ctx.state_dir, policy.episode_gap_sec, probes.wall)
    started = probes.monotonic()
    history: list[_Sample] = []
    while True:
        procs = probes.snapshot()
        roots = _alive_roots(ctx, probes, procs)
        tree = descendants(procs, roots)
        now = probes.monotonic()
        if not tree:
            obs = Observation(False, 0, None, False, 0.0)
        else:
            instance = str(min(roots))
            history.append(
                _Sample(
                    now,
                    {pid: procs[pid].cpu_sec for pid in tree},
                    probes.log_size(ctx.log_file),
                )
            )
            del history[: -_history_cap(policy)]
            status = probes.http_status(ctx.url, policy.http_timeout_sec)
            obs = Observation(
                process_alive=True,
                http_status=status,
                age_sec=min(procs[pid].age_sec for pid in roots),
                stalled=is_stalled(
                    history, policy.stall_sec, policy.cpu_growth_eps_sec
                ),
                episode_sec=_episode_sec(episodes, instance, status),
            )
        decision = decide(reason, obs, policy)
        if decision.verdict is not Verdict.DENY or now - started >= policy.wait_sec:
            break
        probes.sleep(policy.tick_sec)
    _record(ctx, reason, decision, obs, now - started)
    return decision


def _history_cap(policy: Policy) -> int:
    # Enough ticks to span the stall window plus one baseline sample.
    return int(policy.stall_sec / policy.tick_sec) + 3


def _episode_sec(episodes: EpisodeStore, instance: str, status: int) -> float:
    if status == 200:
        episodes.clear(instance)
        return 0.0
    return episodes.touch(instance)


def _record(
    ctx: GateContext,
    reason: Reason,
    decision: Decision,
    obs: Observation | None,
    waited_sec: float,
) -> None:
    journal.append(
        ctx.state_dir,
        "admit",
        {
            "reason": reason.value,
            "verdict": decision.verdict.value,
            "rule": decision.rule,
            "detail": decision.detail,
            "port": ctx.port,
            "waited_sec": round(waited_sec, 1),
            "http": obs.http_status if obs else None,
            "age_sec": (
                round(obs.age_sec, 1) if obs and obs.age_sec is not None else None
            ),
            "episode_sec": round(obs.episode_sec, 1) if obs else None,
        },
    )
