"""Signoff runtime guard — detect and reap Agent ad-hoc signoff loops (P0-SAO-6).

[INPUT]
- pgrep/ps process command lines
- signoff_admission running episode + auto-launcher lockdir pid

[OUTPUT]
- scan_signoff_adhoc_violations() → violation rows
- guard_signoff_runtime(reap=...) → bool + SIGNOFF_* tokens on stdout
"""

from __future__ import annotations

import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

LAUNCHER_LOCK_DIR = Path("/tmp/e2e-signoff-auto-launcher.lockdir")
GATE_SCRIPT_MARKER = "e2e-p0a-1lane-gate.sh"

FORBIDDEN_CMD_SUBSTRINGS: tuple[str, ...] = (
    "p0a-gate-wait-loop",
    "p0a-gate-final-run",
    "p0a-gate-manual-run",
    "p0a-gate-live",
    "p0a-1lane-gate-live",
    "p0a-gate-auto",
    "p0a-gate-wait",
    "P0E_DEAD",
    "e2e-m3-signoff-goal-run",
    "TRIGGER gate",
    "wait_launch()",
)


@dataclass(frozen=True, slots=True)
class AdhocViolation:
    pid: int
    reason: str
    cmd_preview: str


def _read_launcher_pid() -> int | None:
    pid_file = LAUNCHER_LOCK_DIR / "pid"
    if not pid_file.is_file():
        return None
    raw = pid_file.read_text(encoding="utf-8").strip()
    if not raw.isdigit():
        return None
    pid = int(raw)
    try:
        os.kill(pid, 0)
    except OSError:
        return None
    return pid


def _read_sao_holder_pid() -> int | None:
    try:
        from signoff_admission import _connect, _running_episode
    except ImportError:
        return None
    try:
        with _connect() as conn:
            running = _running_episode(conn)
            if running is None:
                return None
            try:
                os.kill(running.owner_pid, 0)
            except OSError:
                return None
            return running.owner_pid
    except Exception:
        return None


def _pgrep_pids(pattern: str) -> list[int]:
    try:
        proc = subprocess.run(
            ["pgrep", "-f", pattern],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return []
    if proc.returncode != 0:
        return []
    pids: list[int] = []
    for line in proc.stdout.splitlines():
        raw = line.strip()
        if raw.isdigit():
            pids.append(int(raw))
    return sorted(set(pids))


def _ps_args(pid: int) -> str:
    try:
        proc = subprocess.run(
            ["ps", "-p", str(pid), "-o", "args="],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return ""
    return proc.stdout.strip()


def _ancestor_pids(pid: int, *, max_depth: int = 8) -> frozenset[int]:
    seen: set[int] = {pid}
    current = pid
    for _ in range(max_depth):
        try:
            proc = subprocess.run(
                ["ps", "-p", str(current), "-o", "ppid="],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            break
        raw = proc.stdout.strip()
        if not raw.isdigit():
            break
        parent = int(raw)
        if parent <= 1 or parent in seen:
            break
        seen.add(parent)
        current = parent
    return frozenset(seen)


def _gate_allowed_pids(
    gate_pids: list[int],
    *,
    launcher_pid: int | None,
    holder_pid: int | None,
) -> frozenset[int]:
    allowed: set[int] = set()
    for gate_pid in gate_pids:
        chain = _ancestor_pids(gate_pid)
        if launcher_pid is not None and launcher_pid in chain:
            allowed.add(gate_pid)
            continue
        if holder_pid is not None and (
            gate_pid == holder_pid or holder_pid in chain
        ):
            allowed.add(gate_pid)
    if not allowed and len(gate_pids) == 1 and holder_pid is not None:
        if gate_pids[0] == holder_pid:
            allowed.add(gate_pids[0])
    return frozenset(allowed)


def scan_signoff_adhoc_violations() -> list[AdhocViolation]:
    """Return ad-hoc signoff processes that must not run alongside SAO."""
    violations: list[AdhocViolation] = []
    launcher_pid = _read_launcher_pid()
    holder_pid = _read_sao_holder_pid()
    self_pid = os.getpid()
    checked_pids: set[int] = set()

    for token in FORBIDDEN_CMD_SUBSTRINGS:
        for pid in _pgrep_pids(token):
            if pid in {self_pid, os.getppid()} or pid in checked_pids:
                continue
            checked_pids.add(pid)
            cmd = _ps_args(pid)
            if not cmd or GATE_SCRIPT_MARKER in cmd:
                continue
            if "signoff_runtime_guard" in cmd or "guard_signoff_runtime" in cmd:
                continue
            violations.append(
                AdhocViolation(
                    pid=pid,
                    reason=f"forbidden_adhoc_loop:{token}",
                    cmd_preview=cmd[:240],
                )
            )

    gate_pids = [
        pid
        for pid in _pgrep_pids(GATE_SCRIPT_MARKER)
        if pid not in {self_pid, os.getppid()}
    ]
    allowed_gates = _gate_allowed_pids(
        gate_pids,
        launcher_pid=launcher_pid,
        holder_pid=holder_pid,
    )
    for gate_pid in gate_pids:
        if gate_pid in allowed_gates:
            continue
        cmd = _ps_args(gate_pid)
        reason = "rogue_gate_spawn"
        if len(gate_pids) > 1:
            reason = "duplicate_gate_spawn"
        violations.append(
            AdhocViolation(
                pid=gate_pid,
                reason=reason,
                cmd_preview=cmd[:240] or GATE_SCRIPT_MARKER,
            )
        )

    return violations


def _reap_violations(violations: list[AdhocViolation]) -> None:
    for row in violations:
        try:
            os.kill(row.pid, signal.SIGTERM)
        except OSError:
            continue
    if violations:
        time.sleep(1.0)
        for row in violations:
            try:
                os.kill(row.pid, 0)
            except OSError:
                continue
            try:
                os.kill(row.pid, signal.SIGKILL)
            except OSError:
                pass


def guard_signoff_runtime(*, reap: bool = False) -> bool:
    """Enforce single SSOT signoff orchestration path."""
    if os.environ.get("MYRM_SIGNOFF_GUARD_DISABLE", "").strip() == "1":
        print("SIGNOFF_RUNTIME_GUARD_SKIP: MYRM_SIGNOFF_GUARD_DISABLE=1")
        return True

    violations = scan_signoff_adhoc_violations()
    if reap and violations:
        print(f"SIGNOFF_RUNTIME_GUARD_REAP: count={len(violations)}")
        _reap_violations(violations)
        violations = scan_signoff_adhoc_violations()

    if violations:
        for row in violations:
            print(
                "SIGNOFF_ADHOC_VIOLATION: "
                f"pid={row.pid} reason={row.reason} cmd={row.cmd_preview!r}"
            )
        print(f"SIGNOFF_RUNTIME_GUARD_FAIL: violations={len(violations)}")
        return False

    print("SIGNOFF_RUNTIME_GUARD_OK")
    return True


def main(argv: list[str] | None = None) -> int:
    import sys

    args = list(sys.argv[1:] if argv is None else argv)
    reap = "--reap" in args
    ok = guard_signoff_runtime(reap=reap)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
