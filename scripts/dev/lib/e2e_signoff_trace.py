"""Append-only Chrome E2E signoff trace — survives pytest -q stdout capture."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

_TRACE_DIR_NAME = "myrm-e2e-signoff-trace"


def _trace_root() -> Path:
    tmp = os.environ.get("TMPDIR", "/tmp").strip() or "/tmp"
    return Path(tmp) / _TRACE_DIR_NAME


def resolve_signoff_trace_path(*, nodeid: str) -> Path:
    safe = nodeid.replace("/", "_").replace("::", "__").replace("[", "_").replace("]", "_")
    return _trace_root() / f"{safe}.trace.log"


def begin_signoff_trace(*, nodeid: str) -> Path:
    path = resolve_signoff_trace_path(nodeid=nodeid)
    path.parent.mkdir(parents=True, exist_ok=True)
    os.environ["E2E_SIGNOFF_TRACE_PATH"] = str(path)
    _append(path, f"E2E_SIGNOFF_TRACE_START nodeid={nodeid}")
    print(f"E2E_SIGNOFF_TRACE: path={path}", file=sys.stderr, flush=True)
    return path


def signoff_trace_path() -> Path | None:
    raw = os.environ.get("E2E_SIGNOFF_TRACE_PATH", "").strip()
    return Path(raw) if raw else None


def _append(path: Path, line: str) -> None:
    ts = time.strftime("%Y-%m-%dT%H:%M:%S")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{ts} {line}\n")
        handle.flush()


def signoff_trace_emit(line: str) -> None:
    path = signoff_trace_path()
    if path is None:
        return
    _append(path, line)
    if line.startswith("E2E_"):
        print(line, file=sys.stderr, flush=True)


def end_signoff_trace(*, outcome: str) -> None:
    path = signoff_trace_path()
    if path is None:
        return
    _append(path, f"E2E_SIGNOFF_TRACE_END outcome={outcome}")
    os.environ.pop("E2E_SIGNOFF_TRACE_PATH", None)
