"""Positive proof that a process was started by a dev-stack runtime.

The dev stack stamps every process it spawns with ``MYRM_RUNTIME_NAMESPACE`` and
``MYRM_DEV_STATE_DIR`` (inherited through the environment). The desktop sidecar and
``myrm start`` runtimes never carry that stamp, so the stamp is what separates a
dev-owned listener from a user's runtime that merely sits on a dev default port
(8080 / 3000). Dev tooling may adopt, record or signal a listener only after this
module returns ``owned``; ``foreign`` and ``unknown`` both fail closed.

stdlib only: bash dev primitives call it from any interpreter, so psutil is an
optional accelerator, never a requirement.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

NAMESPACE_KEY: Final = "MYRM_RUNTIME_NAMESPACE"
STATE_DIR_KEY: Final = "MYRM_DEV_STATE_DIR"

Verdict = Literal["owned", "foreign", "unknown"]

EXIT_OWNED: Final = 0
EXIT_FOREIGN: Final = 4
EXIT_UNKNOWN: Final = 5

# Environment tokens are `KEY=value` separated by spaces; the namespace never contains
# spaces, and the state dir only needs to be non-empty, so a truncated value is enough.
_TOKEN_RE: Final = {
    key: re.compile(rf"(?:^|\s){key}=(\S+)") for key in (NAMESPACE_KEY, STATE_DIR_KEY)
}


@dataclass(frozen=True)
class DevStamp:
    namespace: str
    state_dir: str


def _stamp_from_mapping(env: dict[str, str]) -> DevStamp:
    return DevStamp(
        namespace=env.get(NAMESPACE_KEY, "").strip(),
        state_dir=env.get(STATE_DIR_KEY, "").strip(),
    )


def _read_via_psutil(pid: int) -> DevStamp | None:
    try:
        import psutil  # type: ignore[import-not-found]
    except ImportError:
        return None
    try:
        return _stamp_from_mapping(psutil.Process(pid).environ())
    except (psutil.Error, OSError):
        return None


def _read_via_proc(pid: int) -> DevStamp | None:
    try:
        raw = Path(f"/proc/{pid}/environ").read_bytes()
    except OSError:
        return None
    env: dict[str, str] = {}
    for item in raw.split(b"\0"):
        key, sep, value = item.decode("utf-8", "replace").partition("=")
        if sep:
            env[key] = value
    return _stamp_from_mapping(env)


def _ps_text(args: list[str]) -> str | None:
    try:
        result = subprocess.run(args, capture_output=True, text=True, check=False)
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def _read_via_ps(pid: int) -> DevStamp | None:
    """BSD `ps eww` appends the environment to the command column.

    The exact command (without environment) is stripped first so a stamp-looking
    argument of a foreign process can never be mistaken for its environment.
    """
    command = _ps_text(["ps", "-ww", "-p", str(pid), "-o", "command="])
    with_env = _ps_text(["ps", "eww", "-p", str(pid)])
    if command is None or with_env is None:
        return None
    lines = [line for line in with_env.splitlines() if line.strip()]
    if len(lines) < 2:
        return None
    fields = lines[-1].split(None, 4)
    if len(fields) < 5:
        return None
    tail = fields[4]
    command = command.strip()
    if not command or not tail.startswith(command):
        return None
    env_text = tail[len(command):]
    found = {
        key: match.group(1)
        for key, pattern in _TOKEN_RE.items()
        if (match := pattern.search(env_text))
    }
    return _stamp_from_mapping(found)


def read_stamp(pid: int) -> DevStamp | None:
    """Return the process's dev stamp, or None when its environment is unreadable."""
    if pid <= 0:
        return None
    for reader in (_read_via_psutil, _read_via_proc, _read_via_ps):
        stamp = reader(pid)
        if stamp is not None:
            return stamp
    return None


def classify(pid: int, runtime_id: str) -> Verdict:
    stamp = read_stamp(pid)
    if stamp is None:
        return "unknown"
    if stamp.namespace == runtime_id.strip() and stamp.state_dir:
        return "owned"
    return "foreign"


def _command_of(pid: int) -> str:
    text = _ps_text(["ps", "-ww", "-p", str(pid), "-o", "command="])
    return (text or "").strip()[:160]


def _cmd_owned(args: argparse.Namespace) -> int:
    verdict = classify(args.pid, args.runtime_id)
    print(verdict)
    return {"owned": EXIT_OWNED, "foreign": EXIT_FOREIGN}.get(verdict, EXIT_UNKNOWN)


def _cmd_filter(args: argparse.Namespace) -> int:
    """Print owned pids on stdout; report every skipped pid on stderr."""
    for pid in args.pids:
        verdict = classify(pid, args.runtime_id)
        if verdict == "owned":
            print(pid)
            continue
        print(
            f"STACK_SKIP_FOREIGN: pid={pid} verdict={verdict} "
            f"runtime={args.runtime_id} command={_command_of(pid)!r}",
            file=sys.stderr,
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dev-stack process ownership proof")
    sub = parser.add_subparsers(dest="command", required=True)
    owned = sub.add_parser("owned", help="exit 0 owned | 4 foreign | 5 unknown")
    owned.add_argument("--pid", type=int, required=True)
    owned.add_argument("--runtime-id", required=True)
    owned.set_defaults(handler=_cmd_owned)
    filtered = sub.add_parser("filter", help="print the owned subset of the given pids")
    filtered.add_argument("--runtime-id", required=True)
    filtered.add_argument("pids", nargs="*", type=int)
    filtered.set_defaults(handler=_cmd_filter)
    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
