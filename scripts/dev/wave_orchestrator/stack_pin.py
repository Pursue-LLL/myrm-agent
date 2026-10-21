"""Stack pin — freeze backend/frontend PIDs for an open test wave.

[INPUT]
- wave_orchestrator.paths::WavePaths (POS: shared dev state root)
- wave_orchestrator.types::WaveRecord (POS: open wave metadata)

[OUTPUT]
- write_stack_pin() / clear_stack_pin() / read_stack_pin()
- probe_stack_pids() — live pid snapshot from dev stack pid files

[POS]
Mechanical stack immutability during an open wave. Supervisor and dev-stack consult
check_stack_write_gate() which treats open waves without STACK_WRITE lease as pinned.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import TypedDict

from wave_orchestrator.paths import WavePaths, resolve_wave_paths
from wave_orchestrator.types import WaveRecord


class StackPinRecord(TypedDict):
    waveId: str
    runtimeId: str
    openedBy: str
    pinnedAt: str
    backendPid: int | None
    frontendPid: int | None


def _pin_file(paths: WavePaths) -> Path:
    return paths.state_dir / "stack-pin.json"


def _read_pid_file(path: Path) -> int | None:
    if not path.is_file():
        return None
    raw = path.read_text(encoding="utf-8").strip()
    if raw.isdigit():
        return int(raw)
    return None


def probe_stack_pids(paths: WavePaths) -> tuple[int | None, int | None]:
    backend_pid = _read_pid_file(paths.state_dir / "backend.pid")
    frontend_pid = _read_pid_file(paths.state_dir / "frontend.pid")
    return backend_pid, frontend_pid


def write_stack_pin(wave: WaveRecord, *, paths: WavePaths, pinned_at: str) -> StackPinRecord:
    backend_pid, frontend_pid = probe_stack_pids(paths)
    record: StackPinRecord = {
        "waveId": wave["waveId"],
        "runtimeId": wave["runtimeId"],
        "openedBy": wave["openedBy"],
        "pinnedAt": pinned_at,
        "backendPid": backend_pid,
        "frontendPid": frontend_pid,
    }
    pin_path = _pin_file(paths)
    pin_path.parent.mkdir(parents=True, exist_ok=True)
    # Unique tmp name: concurrent writers (supervisor watchdog reap, attach heal,
    # pytest coordinators) share one pin path. A fixed `.tmp` name races — one
    # process os.replace() consumes the tmp file, the next gets FileNotFoundError.
    tmp = pin_path.with_name(f".{pin_path.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")
    tmp.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        os.replace(tmp, pin_path)
    finally:
        tmp.unlink(missing_ok=True)
    return record


def read_stack_pin(*, paths: WavePaths | None = None) -> StackPinRecord | None:
    resolved = paths or resolve_wave_paths()
    pin_path = _pin_file(resolved)
    if not pin_path.is_file():
        return None
    try:
        data = json.loads(pin_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    wave_id = data.get("waveId")
    runtime_id = data.get("runtimeId")
    opened_by = data.get("openedBy")
    pinned_at = data.get("pinnedAt")
    if not all(isinstance(item, str) and item for item in (wave_id, runtime_id, opened_by, pinned_at)):
        return None
    backend_pid = data.get("backendPid")
    frontend_pid = data.get("frontendPid")
    return {
        "waveId": wave_id,
        "runtimeId": runtime_id,
        "openedBy": opened_by,
        "pinnedAt": pinned_at,
        "backendPid": int(backend_pid) if isinstance(backend_pid, int) else None,
        "frontendPid": int(frontend_pid) if isinstance(frontend_pid, int) else None,
    }


def clear_stack_pin(*, paths: WavePaths) -> None:
    pin_path = _pin_file(paths)
    if pin_path.is_file():
        pin_path.unlink()
