"""Daily JSONL stores for host load samples and hotspot rows: append, retention, windowed read.

[INPUT]
- LoadSample rows from host_load_sampler
- Hotspot rows from host_hotspot_capture
- bootstrap_deadline.dev_state_dir (MYRM_DEV_STATE_DIR or ~/.local/state/myrm-dev)

[OUTPUT]
- append_sample(directory, sample) -> Path
- prune_expired(directory, today=...) -> int removed
- read_window(directory, since=...) -> list[LoadSample]
- append_hotspot(directory, hotspot) -> Path
- prune_expired_hotspots(directory, today=...) -> int removed
- read_hotspots(directory, since=...) -> list[Hotspot]

[POS]
One file per local day and kind (``host-load-YYYYMMDD.jsonl``, ``hotspots-YYYYMMDD.jsonl``) so
retention is a file delete, never a rewrite of a large log. Readers skip torn or foreign lines
instead of failing the report. Hotspot files are created owner-only: their rows carry
redacted command lines.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Final, cast

from e2e_core.host_hotspot_capture import Hotspot
from e2e_core.host_load_sampler import LoadSample

FILE_PREFIX: Final = "host-load-"
HOTSPOT_PREFIX: Final = "hotspots-"
RETENTION_DAYS: Final = 7
_DAY_FORMAT: Final = "%Y%m%d"
# Default creation mode (the umask applies), as ``open(path, "a")`` would use.
_SHARED_MODE: Final = 0o666
_OWNER_ONLY_MODE: Final = 0o600


def _file_day(path: Path, prefix: str) -> date | None:
    try:
        return datetime.strptime(path.stem[len(prefix) :], _DAY_FORMAT).date()
    except ValueError:
        return None


def _append_row(
    directory: Path, prefix: str, ts: float, row: Mapping[str, object], *, mode: int
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    day = datetime.fromtimestamp(ts).strftime(_DAY_FORMAT)
    path = directory / f"{prefix}{day}.jsonl"
    descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, mode)
    with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, separators=(",", ":")) + "\n")
    return path


def _prune(directory: Path, prefix: str, *, today: date, keep_days: int) -> int:
    cutoff = today - timedelta(days=keep_days)
    removed = 0
    for path in directory.glob(f"{prefix}*.jsonl"):
        day = _file_day(path, prefix)
        if day is not None and day < cutoff:
            path.unlink(missing_ok=True)
            removed += 1
    return removed


def _read_rows(
    directory: Path, prefix: str, *, since: float, required: frozenset[str]
) -> list[dict[str, object]]:
    first_day = datetime.fromtimestamp(since).date()
    rows: list[dict[str, object]] = []
    for path in sorted(directory.glob(f"{prefix}*.jsonl")):
        day = _file_day(path, prefix)
        if day is None or day < first_day:
            continue
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict) or not required.issubset(row.keys()):
                continue
            ts = row["ts"]
            if isinstance(ts, int | float) and ts >= since:
                rows.append(row)
    return rows


def append_sample(directory: Path, sample: LoadSample) -> Path:
    return _append_row(directory, FILE_PREFIX, sample["ts"], sample, mode=_SHARED_MODE)


def prune_expired(
    directory: Path, *, today: date, keep_days: int = RETENTION_DAYS
) -> int:
    """Delete day files older than ``keep_days``; returns how many were removed."""
    return _prune(directory, FILE_PREFIX, today=today, keep_days=keep_days)


def read_window(directory: Path, *, since: float) -> list[LoadSample]:
    """Samples with ``ts >= since``, oldest first; rows missing any field are skipped."""
    rows = _read_rows(
        directory, FILE_PREFIX, since=since, required=LoadSample.__required_keys__
    )
    return cast(list[LoadSample], rows)


def append_hotspot(directory: Path, hotspot: Hotspot) -> Path:
    return _append_row(
        directory, HOTSPOT_PREFIX, hotspot["ts"], hotspot, mode=_OWNER_ONLY_MODE
    )


def prune_expired_hotspots(
    directory: Path, *, today: date, keep_days: int = RETENTION_DAYS
) -> int:
    return _prune(directory, HOTSPOT_PREFIX, today=today, keep_days=keep_days)


def read_hotspots(directory: Path, *, since: float) -> list[Hotspot]:
    """Hotspots with ``ts >= since``, oldest first; rows missing any field are skipped."""
    rows = _read_rows(
        directory, HOTSPOT_PREFIX, since=since, required=Hotspot.__required_keys__
    )
    return cast(list[Hotspot], rows)
