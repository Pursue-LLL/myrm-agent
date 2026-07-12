"""Garbage-collect stale dev-stack state when processes die."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from stack_supervisor.paths import StackPaths
from stack_supervisor.probe import StackProbe, probe_stack


@dataclass(frozen=True)
class GcAction:
    cleared_warmth: bool
    cleared_epoch: bool
    cleared_backend_pid: bool
    cleared_frontend_pid: bool
    cleared_frontend_lock: bool


def _remove_file(path: Path) -> bool:
    if not path.is_file():
        return False
    path.unlink()
    return True


def collect_stale_state(paths: StackPaths, probe: StackProbe | None = None) -> tuple[StackProbe, GcAction]:
    live = probe if probe is not None else probe_stack(paths)

    cleared_warmth = False
    cleared_epoch = False
    cleared_backend_pid = False
    cleared_frontend_pid = False
    cleared_frontend_lock = False

    if live.backend_process == "dead":
        cleared_backend_pid = _remove_file(paths.backend_pid_file)
        if live.epoch_backend_pid is not None and live.epoch_backend_pid == live.backend_pid:
            cleared_epoch = _remove_file(paths.epoch_file)

    if live.frontend_process == "dead":
        cleared_frontend_lock = _remove_file(paths.frontend_lock_file)
        cleared_frontend_pid = _remove_file(paths.frontend_pid_file)
        cleared_warmth = _remove_file(paths.warmth_file)
    elif not live.frontend_port_listening:
        cleared_warmth = _remove_file(paths.warmth_file) or cleared_warmth
    elif live.warmth_generation is None and paths.warmth_file.is_file():
        cleared_warmth = _remove_file(paths.warmth_file)

    if live.backend_process != "alive" and paths.epoch_file.is_file():
        cleared_epoch = _remove_file(paths.epoch_file) or cleared_epoch

    refreshed = probe_stack(paths)
    return refreshed, GcAction(
        cleared_warmth=cleared_warmth,
        cleared_epoch=cleared_epoch,
        cleared_backend_pid=cleared_backend_pid,
        cleared_frontend_pid=cleared_frontend_pid,
        cleared_frontend_lock=cleared_frontend_lock,
    )


def write_supervisor_state(paths: StackPaths, probe: StackProbe, gc: GcAction | None = None) -> None:
    paths.state_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "updated_at": datetime.now(UTC).isoformat(),
        "backend_pid": probe.backend_pid,
        "backend_process": probe.backend_process,
        "frontend_lock_pid": probe.frontend_lock_pid,
        "frontend_process": probe.frontend_process,
        "frontend_port_listening": probe.frontend_port_listening,
        "api_http_ok": probe.api_http_ok,
        "frontend_http_ok": probe.frontend_http_ok,
        "shell_hot": probe.warmth_generation is not None,
        "stack_epoch": probe.epoch,
        "stack_warm": (
            probe.backend_process == "alive"
            and probe.frontend_process == "alive"
            and probe.api_http_ok
            and probe.frontend_http_ok
            and probe.warmth_generation is not None
        ),
    }
    if gc is not None:
        payload["last_gc"] = {
            "cleared_warmth": gc.cleared_warmth,
            "cleared_epoch": gc.cleared_epoch,
            "cleared_backend_pid": gc.cleared_backend_pid,
            "cleared_frontend_pid": gc.cleared_frontend_pid,
            "cleared_frontend_lock": gc.cleared_frontend_lock,
        }
    paths.supervisor_state_file.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
