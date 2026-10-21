"""Persistent "how long has this server been unhealthy" clock across gate invocations.

[INPUT]
  state dir (frontend-gate-episodes.json + sidecar flock)

[OUTPUT]
  EpisodeStore.touch / clear: seconds the current unhealthy episode of one server instance has lasted

[POS]
  Backstop for the stall detector: a server that burns CPU forever without ever answering
  is wedged too. Episodes only chain observations that arrive within ``gap_sec`` of each
  other, so a server that recovered in between starts a fresh clock.
"""

from __future__ import annotations

import fcntl
import json
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class _Mark:
    instance: str
    since: float
    last_seen: float


class EpisodeStore:
    def __init__(
        self, state_dir: Path, gap_sec: float, clock: Callable[[], float]
    ) -> None:
        self._path = state_dir / "frontend-gate-episodes.json"
        self._lock_path = state_dir / "frontend-gate-episodes.lock"
        self._gap_sec = gap_sec
        self._clock = clock

    def touch(self, instance: str) -> float:
        """Record one unhealthy observation of ``instance``; return the episode length in seconds."""
        now = self._clock()
        with self._locked():
            mark = self._load()
            chained = (
                mark is not None
                and mark.instance == instance
                and now - mark.last_seen <= self._gap_sec
            )
            since = mark.since if mark is not None and chained else now
            self._save(_Mark(instance, since, now))
        return now - since

    def clear(self, instance: str) -> None:
        with self._locked():
            mark = self._load()
            if mark is not None and mark.instance == instance:
                self._path.unlink(missing_ok=True)

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(self._lock_path), os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    def _load(self) -> _Mark | None:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            return _Mark(
                str(raw["instance"]), float(raw["since"]), float(raw["last_seen"])
            )
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def _save(self, mark: _Mark) -> None:
        payload = {
            "instance": mark.instance,
            "since": mark.since,
            "last_seen": mark.last_seen,
        }
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        os.replace(tmp, self._path)
