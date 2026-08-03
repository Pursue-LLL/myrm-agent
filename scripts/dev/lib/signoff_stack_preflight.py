"""Signoff stack preflight SSOT — hot attach vs bounded heal for solo signoff gates (§17).

[INPUT]
- gate_epoch_preflight.SoloSnapshot, e2e_api_verify, runtime_identity hot state

[OUTPUT]
- run_signoff_ready_under_flock() → exit rc for subprocess myrm ready

[POS]
Dev gate layer only. Replaces blind full `ready --chrome` during solo signoff preflight.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from gate_epoch_preflight import SoloSnapshot, read_solo_snapshot


class SignoffReadyMode(StrEnum):
    HOT_ATTACH = "hot_attach"
    BOUNDED_HEAL = "bounded_heal"


@dataclass(frozen=True, slots=True)
class StackHotSnapshot:
    epoch_match: bool
    blocked: bool
    backend_healthy: bool
    shell_hot: bool
    client_hot: bool


def _emit(token: str) -> None:
    print(token, flush=True)


def _myrm_cmd(monorepo_root: Path, *parts: str) -> list[str]:
    return [str(monorepo_root / "myrm"), *parts]


def shared_stack_ports_reachable() -> bool:
    """True when shared :8080 health + :3000 UI respond — attach-safe without full heal."""
    from runtime_identity import api_health_errors, classify_ui_endpoint_error

    api_base = os.environ.get("E2E_API_BASE", "http://127.0.0.1:8080")
    ui_base = os.environ.get("E2E_UI_BASE", "http://127.0.0.1:3000")
    if api_health_errors(api_base):
        return False
    return classify_ui_endpoint_error(ui_base) is None


def read_stack_hot_snapshot() -> StackHotSnapshot:
    from e2e_api_verify import resolve_e2e_api_context
    from runtime_identity import collect_runtime_parts, read_frontend_hot_state

    ctx = resolve_e2e_api_context(retry_after_apply=False)
    parts = collect_runtime_parts()
    shell_hot, client_hot = read_frontend_hot_state(parts.get("frontend_epoch"))
    backend_healthy = bool(ctx.epoch_match and not ctx.blocked)
    for candidate in ctx.candidates:
        if candidate.source == "shared" and candidate.epoch_match and candidate.health_ok:
            backend_healthy = True
            break
    return StackHotSnapshot(
        epoch_match=bool(ctx.epoch_match),
        blocked=bool(ctx.blocked),
        backend_healthy=backend_healthy,
        shell_hot=bool(shell_hot),
        client_hot=bool(client_hot),
    )


def choose_signoff_ready_mode(
    solo: SoloSnapshot,
    hot: StackHotSnapshot,
) -> SignoffReadyMode:
    if solo.peers > 0 or solo.mux_peers > 1:
        return SignoffReadyMode.BOUNDED_HEAL
    if (
        hot.epoch_match
        and not hot.blocked
        and hot.backend_healthy
        and hot.shell_hot
        and hot.client_hot
    ):
        return SignoffReadyMode.HOT_ATTACH
    # Backend epoch-aligned + ports live → attach-wait shell_hot (avoid dev-stack ensure SIGTERM under wave pin).
    if (
        hot.epoch_match
        and not hot.blocked
        and hot.backend_healthy
        and shared_stack_ports_reachable()
    ):
        return SignoffReadyMode.HOT_ATTACH
    # Solo + ports live + shell already hot → fast attach (≤60s).
    if shared_stack_ports_reachable() and hot.shell_hot:
        return SignoffReadyMode.HOT_ATTACH
    return SignoffReadyMode.BOUNDED_HEAL


def _run_heal_flocked(
    cmd: list[str],
    *,
    wait_sec: float,
    cwd: Path | None = None,
) -> int:
    from stack_mutation_policy import (
        default_backend_heal_flock_file,
        run_command_with_backend_heal_flock,
    )

    if cwd is None:
        return run_command_with_backend_heal_flock(
            cmd=cmd,
            lock_file=default_backend_heal_flock_file(),
            wait_sec=wait_sec,
        )
    from stack_mutation_policy import backend_heal_file_lock
    import subprocess

    try:
        with backend_heal_file_lock(default_backend_heal_flock_file(), wait_sec):
            completed = subprocess.run(cmd, check=False, cwd=str(cwd))
        return int(completed.returncode)
    except TimeoutError as exc:
        print(f"GATE_STACK_HEAL_FLOCK_TIMEOUT: {exc}", file=sys.stderr)
        return 1


def run_signoff_ready_under_flock(
    monorepo_root: Path,
    *,
    wall_sec: int = 180,
) -> int:
    """Run attach-first or bounded full ready for solo signoff; return subprocess rc."""
    solo = read_solo_snapshot()
    hot = read_stack_hot_snapshot()
    mode = choose_signoff_ready_mode(solo, hot)

    saved_attach = os.environ.get("MYRM_CHROME_E2E_ATTACH")
    saved_wall = os.environ.get("MYRM_READY_CHROME_SOLO_WALL_SEC")

    if mode == SignoffReadyMode.HOT_ATTACH:
        attach_wall = min(60, max(15, wall_sec))
        os.environ["MYRM_CHROME_E2E_ATTACH"] = "1"
        os.environ["MYRM_READY_CHROME_SOLO_WALL_SEC"] = str(attach_wall)
        full_hot = (
            hot.epoch_match
            and not hot.blocked
            and hot.backend_healthy
            and hot.shell_hot
            and hot.client_hot
        )
        token = (
            "SIGNOFF_PREFLIGHT_HOT_ATTACH"
            if full_hot
            else "SIGNOFF_PREFLIGHT_SOLO_PORTS_ATTACH"
        )
        _emit(
            f"{token}: "
            f"shell_hot={hot.shell_hot} client_hot={hot.client_hot} "
            f"epoch_match={hot.epoch_match} blocked={hot.blocked} wall={attach_wall}s"
        )
        cmd = _myrm_cmd(monorepo_root, "ready", "--attach", "--chrome")
        flock_wait = float(min(90, attach_wall + 30))
    else:
        heal_wall = min(120, max(30, wall_sec))
        os.environ.pop("MYRM_CHROME_E2E_ATTACH", None)
        os.environ["MYRM_READY_CHROME_SOLO_WALL_SEC"] = str(heal_wall)
        _emit(
            "SIGNOFF_PREFLIGHT_BOUNDED_HEAL: "
            f"shell_hot={hot.shell_hot} client_hot={hot.client_hot} "
            f"epoch_match={hot.epoch_match} blocked={hot.blocked} wall={heal_wall}s"
        )
        cmd = _myrm_cmd(monorepo_root, "ready", "--chrome")
        flock_wait = float(min(150, heal_wall + 30))

    try:
        return _run_heal_flocked(cmd, wait_sec=flock_wait, cwd=monorepo_root)
    finally:
        if saved_attach is None:
            os.environ.pop("MYRM_CHROME_E2E_ATTACH", None)
        else:
            os.environ["MYRM_CHROME_E2E_ATTACH"] = saved_attach
        if saved_wall is None:
            os.environ.pop("MYRM_READY_CHROME_SOLO_WALL_SEC", None)
        else:
            os.environ["MYRM_READY_CHROME_SOLO_WALL_SEC"] = saved_wall
