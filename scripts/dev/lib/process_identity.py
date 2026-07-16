"""Capture and terminate an owned Unix process without trusting a bare PID.

The identity combines PID with the OS-reported process start token. A recycled
PID therefore never authorizes a signal. This module intentionally uses only
the standard library so Bash dev primitives can call it from any Python venv.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import NotRequired, TypedDict

SCHEMA_VERSION = 1


class ProcessIdentity(TypedDict):
    schemaVersion: int
    role: str
    runtimeId: str
    pid: int
    pgid: int
    startedAt: str
    command: str
    recordedAt: float
    parentPid: NotRequired[int]


class ProcessOwnershipError(RuntimeError):
    """Raised when current OS process identity differs from recorded owner."""


def _capture_ps_line(pid: int) -> str | None:
    result = subprocess.run(
        [
            "ps",
            "-p",
            str(pid),
            "-o",
            "pgid=",
            "-o",
            "stat=",
            "-o",
            "lstart=",
            "-o",
            "command=",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return result.stdout.strip()


def capture_process(pid: int, *, role: str, runtime_id: str) -> ProcessIdentity | None:
    if pid <= 0:
        return None
    line = _capture_ps_line(pid)
    if line is None:
        return None
    parts = line.split(maxsplit=7)
    if len(parts) != 8 or not parts[0].isdigit():
        raise RuntimeError(f"PROCESS_IDENTITY_PARSE_FAILED: pid={pid} output={line!r}")
    if parts[1].startswith("Z"):
        return None
    try:
        parent_pid = os.getppid() if pid == os.getpid() else _read_parent_pid(pid)
    except RuntimeError:
        parent_pid = 0
    identity: ProcessIdentity = {
        "schemaVersion": SCHEMA_VERSION,
        "role": role,
        "runtimeId": runtime_id,
        "pid": pid,
        "pgid": int(parts[0]),
        "startedAt": " ".join(parts[2:7]),
        "command": parts[7],
        "recordedAt": time.time(),
    }
    if parent_pid > 0:
        identity["parentPid"] = parent_pid
    return identity


def _read_parent_pid(pid: int) -> int:
    result = subprocess.run(
        ["ps", "-p", str(pid), "-o", "ppid="],
        capture_output=True,
        text=True,
        check=False,
    )
    raw = result.stdout.strip()
    if result.returncode != 0 or not raw.isdigit():
        raise RuntimeError(f"PROCESS_PARENT_READ_FAILED: pid={pid}")
    return int(raw)


def parse_identity(payload: object) -> ProcessIdentity:
    if not isinstance(payload, dict):
        raise RuntimeError("PROCESS_IDENTITY_INVALID: root must be an object")
    required = {
        "schemaVersion": int,
        "role": str,
        "runtimeId": str,
        "pid": int,
        "pgid": int,
        "startedAt": str,
        "command": str,
        "recordedAt": (int, float),
    }
    for key, expected in required.items():
        value = payload.get(key)
        if not isinstance(value, expected):
            raise RuntimeError(f"PROCESS_IDENTITY_INVALID: field={key}")
    if payload["schemaVersion"] != SCHEMA_VERSION:
        raise RuntimeError(
            f"PROCESS_IDENTITY_INVALID: expected schema {SCHEMA_VERSION}"
        )
    identity: ProcessIdentity = {
        "schemaVersion": payload["schemaVersion"],
        "role": payload["role"],
        "runtimeId": payload["runtimeId"],
        "pid": payload["pid"],
        "pgid": payload["pgid"],
        "startedAt": payload["startedAt"],
        "command": payload["command"],
        "recordedAt": float(payload["recordedAt"]),
    }
    parent_pid = payload.get("parentPid")
    if isinstance(parent_pid, int) and parent_pid > 0:
        identity["parentPid"] = parent_pid
    return identity


def load_identity(path: Path) -> ProcessIdentity:
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"PROCESS_IDENTITY_INVALID: {path}") from exc
    return parse_identity(payload)


def write_identity(path: Path, identity: ProcessIdentity) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(identity, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.chmod(0o600)
    os.replace(temporary, path)


def identity_matches(expected: ProcessIdentity, current: ProcessIdentity) -> bool:
    return (
        expected["pid"] == current["pid"]
        and expected["startedAt"] == current["startedAt"]
        and expected["runtimeId"] == current["runtimeId"]
        and expected["role"] == current["role"]
    )


def verify_identity(identity: ProcessIdentity) -> bool:
    current = capture_process(
        identity["pid"], role=identity["role"], runtime_id=identity["runtimeId"]
    )
    if current is None:
        return False
    if not identity_matches(identity, current):
        raise ProcessOwnershipError(
            "PROCESS_OWNERSHIP_MISMATCH: "
            f"pid={identity['pid']} expectedStart={identity['startedAt']} "
            f"actualStart={current['startedAt']}"
        )
    return True


def _descendant_pids(root_pid: int) -> list[int]:
    result = subprocess.run(
        ["ps", "-axo", "pid=", "-o", "ppid="],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    children: dict[int, list[int]] = {}
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) != 2 or not all(field.isdigit() for field in fields):
            continue
        pid, parent = (int(field) for field in fields)
        children.setdefault(parent, []).append(pid)
    descendants: list[int] = []

    def collect(parent: int) -> None:
        for child in children.get(parent, []):
            collect(child)
            descendants.append(child)

    collect(root_pid)
    return descendants


def _signal_if_same(identity: ProcessIdentity, sig: signal.Signals) -> None:
    current = capture_process(
        identity["pid"], role=identity["role"], runtime_id=identity["runtimeId"]
    )
    if current is None:
        return
    if not identity_matches(identity, current):
        return
    try:
        os.kill(identity["pid"], sig)
    except ProcessLookupError:
        return


def terminate_owned_process(identity: ProcessIdentity, *, timeout_sec: float = 15.0) -> None:
    if not verify_identity(identity):
        return
    descendants = [
        snapshot
        for pid in _descendant_pids(identity["pid"])
        if (
            snapshot := capture_process(
                pid, role=f"{identity['role']}-child", runtime_id=identity["runtimeId"]
            )
        )
        is not None
    ]
    _signal_if_same(identity, signal.SIGTERM)
    for descendant in descendants:
        _signal_if_same(descendant, signal.SIGTERM)

    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if not verify_identity(identity):
            break
        time.sleep(0.2)

    for descendant in descendants:
        _signal_if_same(descendant, signal.SIGKILL)
    if verify_identity(identity):
        _signal_if_same(identity, signal.SIGKILL)

    kill_deadline = time.monotonic() + 5.0
    while time.monotonic() < kill_deadline:
        if not verify_identity(identity):
            return
        time.sleep(0.1)
    raise RuntimeError(f"PROCESS_TERMINATION_TIMEOUT: pid={identity['pid']}")


def _assert_expected(identity: ProcessIdentity, args: argparse.Namespace) -> None:
    expected_pid = getattr(args, "expected_pid", None)
    expected_start = getattr(args, "expected_started_at", None)
    expected_runtime = getattr(args, "expected_runtime_id", None)
    if expected_pid is not None and identity["pid"] != expected_pid:
        raise ProcessOwnershipError("PROCESS_OWNERSHIP_MISMATCH: registry pid differs")
    if expected_start and identity["startedAt"] != expected_start:
        raise ProcessOwnershipError("PROCESS_OWNERSHIP_MISMATCH: start identity differs")
    if expected_runtime and identity["runtimeId"] != expected_runtime:
        raise ProcessOwnershipError("PROCESS_OWNERSHIP_MISMATCH: runtime differs")


def _add_expected_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--expected-pid", type=int)
    parser.add_argument("--expected-started-at")
    parser.add_argument("--expected-runtime-id")


def main() -> int:
    parser = argparse.ArgumentParser(description="Owned dev process identity")
    sub = parser.add_subparsers(dest="command", required=True)
    record = sub.add_parser("record")
    record.add_argument("--pid", type=int, required=True)
    record.add_argument("--identity-file", type=Path, required=True)
    record.add_argument("--runtime-id", required=True)
    record.add_argument("--role", required=True)
    record.add_argument("--expected-command-token", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--identity-file", type=Path, required=True)
    _add_expected_args(verify)
    terminate = sub.add_parser("terminate")
    terminate.add_argument("--identity-file", type=Path, required=True)
    terminate.add_argument("--pid-file", type=Path)
    terminate.add_argument("--timeout", type=float, default=15.0)
    _add_expected_args(terminate)
    show = sub.add_parser("show")
    show.add_argument("--identity-file", type=Path, required=True)
    args = parser.parse_args()

    if args.command == "record":
        identity = capture_process(args.pid, role=args.role, runtime_id=args.runtime_id)
        if identity is None:
            raise RuntimeError(f"PROCESS_NOT_RUNNING: pid={args.pid}")
        if args.expected_command_token not in identity["command"]:
            raise RuntimeError(
                "PROCESS_COMMAND_MISMATCH: "
                f"pid={args.pid} command={identity['command']!r}"
            )
        write_identity(args.identity_file, identity)
        print(json.dumps(identity, sort_keys=True))
        return 0

    identity = load_identity(args.identity_file)
    if args.command == "show":
        print(json.dumps(identity, indent=2, sort_keys=True))
        return 0
    _assert_expected(identity, args)
    if args.command == "verify":
        if not verify_identity(identity):
            return 3
        print(json.dumps(identity, sort_keys=True))
        return 0
    terminate_owned_process(identity, timeout_sec=args.timeout)
    if args.pid_file is not None:
        args.pid_file.unlink(missing_ok=True)
    args.identity_file.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
