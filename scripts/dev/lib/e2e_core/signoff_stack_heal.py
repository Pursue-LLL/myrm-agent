"""Signoff stack heal — SHC wrapper for e2e-m3-signoff.sh (Phase3 P0#1).

Routes shared-stack backend heal through StackHealCoordinator instead of
direct dev-stack frontend-only / verify-api --ensure-backend dogpile paths.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

_DEFAULT_LOCK = Path("/tmp/myrm-stack-heal.flock")
_DEFAULT_WAIT_SEC = 45.0


def _monorepo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _dev_stack(root: Path) -> Path:
    return root / "myrm-agent/scripts/dev/dev-stack.sh"


def _server_dir(root: Path) -> Path:
    return root / "myrm-agent/myrm-agent-server"


def _parallel_active_test_count(root: Path) -> int:
    try:
        proc = subprocess.run(
            ["bash", str(root / "scripts/dev/myrm"), "e2e-context"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return -1
    text = proc.stdout or ""
    match = re.search(r"^E2E_PARALLEL_SNAPSHOT_JSON=(.+)$", text, re.M)
    if not match:
        return -1
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return -1
    active_tests = payload.get("active_tests")
    if isinstance(active_tests, list):
        return len(active_tests)
    try:
        return int(payload.get("active_test_count", -1))
    except (TypeError, ValueError):
        return -1


def signoff_parallel_stack_busy(*, root: Path | None = None) -> bool:
    """True when parallel chrome_e2e or wave leases imply shared-stack mutate skip."""
    repo = root or _monorepo_root()
    active = _parallel_active_test_count(repo)
    if active == -1:
        return True
    if active > 0:
        return True
    try:
        proc = subprocess.run(
            ["bash", str(repo / "scripts/dev/myrm"), "e2e-context"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return True
    headroom = ""
    for line in (proc.stdout or "").splitlines():
        if line.startswith("E2E_CAP_HEADROOM:"):
            headroom = line
    if re.search(r"wave_leases(?:_total)?=[1-9]", headroom):
        return True
    return False


def run_signoff_attach_crash_heal(
    *,
    root: Path | None = None,
    wait_sec: float = _DEFAULT_WAIT_SEC,
) -> int:
    """Shared :8080 crash heal via StackHealCoordinator (single-writer)."""
    repo = root or _monorepo_root()
    sys.path.insert(0, str(repo / "myrm-agent/scripts/dev/lib"))
    from stack_heal_coordinator import request_attach_crash_heal  # noqa: PLC0415

    if signoff_parallel_stack_busy(root=repo):
        print(
            "SIGNOFF_STACK_HEAL: skip attach crash heal (parallel busy; mux-only SSOT)",
            file=sys.stderr,
        )
        return 0
    return request_attach_crash_heal(
        monorepo_root=repo,
        dev_stack=_dev_stack(repo),
        lock_file=_DEFAULT_LOCK,
        wait_sec=wait_sec,
        shpoib=False,
    )


def run_signoff_health_canary(
    *,
    method: str = "GET",
    path: str = "/api/v1/health",
    ensure: bool = False,
    root: Path | None = None,
) -> int:
    """Read-only verify-api; optional SHC attach-heal when ensure=1 and not parallel busy."""
    repo = root or _monorepo_root()
    myrm = repo / "scripts/dev/myrm"
    probe = subprocess.run(
        ["bash", str(myrm), "verify-api", method, path],
        cwd=str(repo),
        check=False,
    )
    if probe.returncode == 0:
        print(f"SIGNOFF_HEALTH_CANARY: ok {method} {path}", flush=True)
        return 0
    if not ensure:
        print(
            f"SIGNOFF_HEALTH_CANARY: fail {method} {path} rc={probe.returncode}",
            file=sys.stderr,
            flush=True,
        )
        return int(probe.returncode)
    if signoff_parallel_stack_busy(root=repo):
        print(
            "SIGNOFF_HEALTH_CANARY: skip ensure (parallel busy; SHPOIB/mux-only SSOT)",
            file=sys.stderr,
            flush=True,
        )
        return 0
    print(
        f"SIGNOFF_HEALTH_CANARY: attach-heal then retry {method} {path}",
        file=sys.stderr,
        flush=True,
    )
    run_signoff_attach_crash_heal(root=repo)
    retry = subprocess.run(
        ["bash", str(myrm), "verify-api", method, path],
        cwd=str(repo),
        check=False,
    )
    if retry.returncode == 0:
        print(f"SIGNOFF_HEALTH_CANARY: ok after heal {method} {path}", flush=True)
        return 0
    print(
        f"SIGNOFF_HEALTH_CANARY: still fail after heal rc={retry.returncode}",
        file=sys.stderr,
        flush=True,
    )
    return int(retry.returncode)


def cmd_attach_heal(_: argparse.Namespace) -> int:
    return run_signoff_attach_crash_heal()


def cmd_parallel_busy(_: argparse.Namespace) -> int:
    print("1" if signoff_parallel_stack_busy() else "0")
    return 0


def cmd_health_canary(ns: argparse.Namespace) -> int:
    return run_signoff_health_canary(
        method=str(ns.method),
        path=str(ns.path),
        ensure=bool(ns.ensure),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    attach = sub.add_parser("attach-heal", help="SHC shared backend heal for signoff")
    attach.set_defaults(handler=cmd_attach_heal)
    busy = sub.add_parser(
        "parallel-busy", help="Print 1 if signoff should skip shared mutate"
    )
    busy.set_defaults(handler=cmd_parallel_busy)
    health = sub.add_parser(
        "health-canary",
        help="verify-api health probe; --ensure runs SHC attach-heal when not parallel busy",
    )
    health.add_argument("method", nargs="?", default="GET")
    health.add_argument("path", nargs="?", default="/api/v1/health")
    health.add_argument(
        "--ensure",
        action="store_true",
        help="On probe failure, SHC attach-heal then retry (skip when parallel busy)",
    )
    health.set_defaults(handler=cmd_health_canary)
    ns = parser.parse_args(argv)
    return int(ns.handler(ns))


if __name__ == "__main__":
    raise SystemExit(main())
