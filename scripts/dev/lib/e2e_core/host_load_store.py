"""Daily JSONL store for host load samples: append, retention and windowed read.

[INPUT]
- LoadSample rows from host_load_sampler
- bootstrap_deadline.dev_state_dir (MYRM_DEV_STATE_DIR or ~/.local/state/myrm-dev)

[OUTPUT]
- append_sample(directory, sample) -> Path
- prune_expired(directory, today=...) -> int removed
- read_window(directory, since=...) -> list[LoadSample]

[POS]
One file per local day (``host-load-YYYYMMDD.jsonl``) so retention is a file delete, never a
rewrite of a large log. Readers skip torn or foreign lines instead of failing the report.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Final, cast

from e2e_core.host_load_sampler import LoadSample

FILE_PREFIX: Final = "host-load-"
RETENTION_DAYS: Final = 7
_DAY_FORMAT: Final = "%Y%m%d"


def _file_day(path: Path) -> date | None:
    try:
        return datetime.strptime(path.stem[len(FILE_PREFIX) :], _DAY_FORMAT).date()
    except ValueError:
        return None


def append_sample(directory: Path, sample: LoadSample) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    day = datetime.fromtimestamp(sample["ts"]).strftime(_DAY_FORMAT)
    path = directory / f"{FILE_PREFIX}{day}.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(sample, separators=(",", ":")) + "\n")
    return path


def prune_expired(
    directory: Path, *, today: date, keep_days: int = RETENTION_DAYS
) -> int:
    """Delete day files older than ``keep_days``; returns how many were removed."""
    cutoff = today - timedelta(days=keep_days)
    removed = 0
    for path in directory.glob(f"{FILE_PREFIX}*.jsonl"):
        day = _file_day(path)
        if day is not None and day < cutoff:
            path.unlink(missing_ok=True)
            removed += 1
    return removed


def read_window(directory: Path, *, since: float) -> list[LoadSample]:
    """Samples with ``ts >= since``, oldest first; rows missing any field are skipped."""
    first_day = datetime.fromtimestamp(since).date()
    required = LoadSample.__required_keys__
    samples: list[LoadSample] = []
    for path in sorted(directory.glob(f"{FILE_PREFIX}*.jsonl")):
        day = _file_day(path)
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
                samples.append(cast(LoadSample, row))
    return samples
