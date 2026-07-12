"""Live probes for dev stack health — never trust cached warmth alone."""

from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from stack_supervisor.paths import StackPaths

ProcessState = Literal["alive", "dead", "missing"]


@dataclass(frozen=True)
class StackProbe:
    backend_pid: int | None
    backend_process: ProcessState
    frontend_lock_pid: int | None
    frontend_process: ProcessState
    frontend_port_listening: bool
    api_http_ok: bool
    frontend_http_ok: bool
    warmth_generation: str | None
    epoch: int | None
    epoch_backend_pid: int | None


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _read_int_pid_file(path: Path) -> int | None:
    if not path.is_file():
        return None
    raw = path.read_text(encoding="utf-8").strip()
    if raw.isdigit():
        return int(raw)
    return None


def _read_lock_pid(path: Path) -> int | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    pid = data.get("pid")
    if isinstance(pid, int):
        return pid
    return None


def _read_epoch(path: Path) -> tuple[int | None, int | None]:
    if not path.is_file():
        return None, None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None, None
    epoch = data.get("epoch")
    backend_pid = data.get("backend_pid")
    epoch_int = int(epoch) if isinstance(epoch, int) else None
    backend_int = int(backend_pid) if isinstance(backend_pid, int) else None
    return epoch_int, backend_int


def _read_warmth_generation(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    generation = data.get("generation")
    return generation if isinstance(generation, str) else None


def _lock_generation(lock_path: Path, frontend_dir: Path) -> str | None:
    if not lock_path.is_file():
        return None
    try:
        data = json.loads(lock_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    bundler_stamp = frontend_dir / ".next/dev-bundler-mode"
    bundler_mode = ""
    if bundler_stamp.is_file():
        bundler_mode = bundler_stamp.read_text(encoding="utf-8").strip()
    parts = [
        str(data.get("pid", "")),
        str(data.get("startedAt", "")),
        str(data.get("port", "")),
        bundler_mode,
    ]
    return ":".join(parts)


def _http_ok(url: str, timeout_sec: float) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout_sec) as response:
            return 200 <= response.status < 300
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _port_listening(port: int) -> bool:
    try:
        result = subprocess.run(
            ["lsof", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return bool(result.stdout.strip())


def probe_stack(paths: StackPaths) -> StackProbe:
    backend_pid = _read_int_pid_file(paths.backend_pid_file)
    if backend_pid is None:
        backend_state: ProcessState = "missing"
    elif _pid_alive(backend_pid):
        backend_state = "alive"
    else:
        backend_state = "dead"

    lock_pid = _read_lock_pid(paths.frontend_lock_file)
    if lock_pid is None:
        frontend_state: ProcessState = "missing"
    elif _pid_alive(lock_pid):
        frontend_state = "alive"
    else:
        frontend_state = "dead"

    epoch, epoch_backend_pid = _read_epoch(paths.epoch_file)
    warmth_gen = _read_warmth_generation(paths.warmth_file)
    lock_gen = _lock_generation(paths.frontend_lock_file, paths.frontend_dir)

    return StackProbe(
        backend_pid=backend_pid,
        backend_process=backend_state,
        frontend_lock_pid=lock_pid,
        frontend_process=frontend_state,
        frontend_port_listening=_port_listening(paths.frontend_port),
        api_http_ok=_http_ok(paths.api_health_url, 5.0),
        frontend_http_ok=_http_ok(paths.app_url, 8.0),
        warmth_generation=warmth_gen if warmth_gen == lock_gen else None,
        epoch=epoch,
        epoch_backend_pid=epoch_backend_pid,
    )


def stack_warm(probe: StackProbe) -> bool:
    return (
        probe.backend_process == "alive"
        and probe.frontend_process == "alive"
        and probe.api_http_ok
        and probe.frontend_http_ok
        and probe.warmth_generation is not None
    )
