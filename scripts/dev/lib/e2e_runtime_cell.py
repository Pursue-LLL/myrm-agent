"""E2E Runtime Cell — parallel chrome_e2e slot isolation (R73-F).

[INPUT]
- dev_gate_contract (stall caps)
- MYRM_DEV_STATE_DIR

[OUTPUT]
- allocate_runtime_cell() / release_runtime_cell()
- cell_hydrate_lock_path() / current_cell_id()
- runtime_cell_snapshot()

[POS]
Dev Gate parallel slot SSOT. Each formal chrome_e2e session owns one cell with
exclusive mux budget key (MYRM_E2E_CELL_ID) and per-cell UI hydrate flock.
Shared read-only: Chrome :9333 + Frontend :3000 HMR.
"""

from __future__ import annotations

import fcntl
import os
import sys
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

_CELL_ENV = "MYRM_E2E_CELL_ID"
_HYDRATE_WAIT_DEFAULT_SEC = 300
_HYDRATE_POLL_DEFAULT_SEC = 2


@dataclass(frozen=True, slots=True)
class RuntimeCell:
    cell_id: str
    run_id: str
    pid: int


def _state_dir() -> Path:
    raw = os.environ.get("MYRM_DEV_STATE_DIR", "").strip()
    if raw:
        return Path(raw)
    return Path.home() / ".local/state/myrm-dev"


def _cells_root() -> Path:
    return _state_dir() / "runtime-cells"


def current_cell_id() -> str:
    return os.environ.get(_CELL_ENV, "").strip()


def cell_hydrate_lock_path(cell_id: str) -> Path:
    safe = cell_id.replace("/", "_").replace(":", "_")
    return _cells_root() / safe / "ui-hydrate.lock"


def _resolve_run_id(explicit: str | None) -> str:
    if explicit and explicit.strip():
        return explicit.strip()
    for name in ("MYRM_E2E_RUN_ID", "MYRM_E2E_AGENT_ID", "MYRM_WAVE_AGENT_ID"):
        raw = os.environ.get(name, "").strip()
        if raw:
            return raw
    return f"pytest-{os.getpid()}-{uuid.uuid4().hex[:8]}"


def allocate_runtime_cell(*, run_id: str | None = None) -> RuntimeCell:
    """Assign a runtime cell for the current chrome_e2e pytest session."""
    existing = current_cell_id()
    if existing:
        resolved_run = _resolve_run_id(run_id)
        return RuntimeCell(cell_id=existing, run_id=resolved_run, pid=os.getpid())
    cell_id = f"cell-{uuid.uuid4().hex[:12]}"
    resolved_run = _resolve_run_id(run_id)
    root = _cells_root() / cell_id.replace("/", "_")
    root.mkdir(parents=True, exist_ok=True)
    os.environ[_CELL_ENV] = cell_id
    if not os.environ.get("MYRM_E2E_RUN_ID", "").strip():
        os.environ["MYRM_E2E_RUN_ID"] = resolved_run
    print(
        f"E2E_RUNTIME_CELL_ACQUIRED: cell={cell_id} run={resolved_run} pid={os.getpid()}",
        file=sys.stderr,
        flush=True,
    )
    return RuntimeCell(cell_id=cell_id, run_id=resolved_run, pid=os.getpid())


def release_runtime_cell(cell_id: str | None = None) -> None:
    """Drop cell env binding; hydrate lock file remains for diagnostics."""
    resolved = (cell_id or current_cell_id()).strip()
    os.environ.pop(_CELL_ENV, None)
    if resolved:
        print(
            f"E2E_RUNTIME_CELL_RELEASED: cell={resolved} pid={os.getpid()}",
            file=sys.stderr,
            flush=True,
        )


def runtime_cell_snapshot() -> dict[str, object]:
    cell_id = current_cell_id()
    return {
        "cellId": cell_id or None,
        "runId": os.environ.get("MYRM_E2E_RUN_ID", "").strip() or None,
        "pid": os.getpid(),
    }


@contextmanager
def cell_ui_hydrate_slot(*, wait_sec: int | None = None) -> Iterator[None]:
    """Per-cell exclusive UI navigate/reload slot (R73-F hydrate lease)."""
    cell_id = current_cell_id()
    if not cell_id or os.environ.get("MYRM_E2E_SHPOIB", "").strip() != "1":
        yield
        return

    resolved_wait = wait_sec
    if resolved_wait is None:
        resolved_wait = int(
            os.environ.get(
                "MYRM_E2E_SHARED_UI_HYDRATE_WAIT_SEC",
                str(_HYDRATE_WAIT_DEFAULT_SEC),
            )
        )
    poll_sec = max(
        1,
        int(
            os.environ.get(
                "MYRM_E2E_SHARED_UI_HYDRATE_POLL_SEC",
                str(_HYDRATE_POLL_DEFAULT_SEC),
            )
        ),
    )
    lock_path = cell_hydrate_lock_path(cell_id)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()

    with lock_path.open("a+", encoding="utf-8") as handle:
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                elapsed = int(time.monotonic() - started)
                print(
                    f"E2E_CELL_UI_HYDRATE_LOCK: cell={cell_id} pid={os.getpid()} "
                    f"elapsed={elapsed}s",
                    file=sys.stderr,
                    flush=True,
                )
                break
            except BlockingIOError:
                elapsed = int(time.monotonic() - started)
                if elapsed >= resolved_wait:
                    raise TimeoutError(
                        f"E2E_CELL_UI_HYDRATE_WAIT_TIMEOUT: cell={cell_id} "
                        f"waited {resolved_wait}s"
                    ) from None
                print(
                    f"E2E_CELL_UI_HYDRATE_WAIT: cell={cell_id} "
                    f"elapsed={elapsed}s/{resolved_wait}s",
                    file=sys.stderr,
                    flush=True,
                )
                time.sleep(poll_sec)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
