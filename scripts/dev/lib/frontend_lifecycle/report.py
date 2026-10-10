"""Read-only health check: does every SIGTERM of the shared frontend have a journal entry?

[INPUT]
  frontend-restart-journal.jsonl(+.1), frontend.log, frontend-restart-baseline.json

[OUTPUT]
  build() / render(): admission outcomes and kills since the baseline, Next's own
  SIGTERM/cold-start counters from frontend.log, and the number of unexplained SIGTERMs

[POS]
  The acceptance number for the restart gate. dev.ts logs every SIGTERM it receives but not
  who sent it; the journal names every kill that went through dev-stack.sh. A SIGTERM
  without a journal kill came from a path outside the gate (operator cleanup, dev.ts or
  dev-lock.ts reclaim) and is the next suspect.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from frontend_lifecycle.journal import JOURNAL_NAME

BASELINE_NAME = "frontend-restart-baseline.json"
_CALLER_SHOWN = 3
_CLIP = 60
# Counter name -> marker printed by scripts/dev.ts / dev-lock.ts.
LOG_MARKERS = {
    "sigterm_received": "Received SIGTERM",
    "cold_starts": "Freeing port",
    "stale_lock_reclaims": "Stale dev lock",
    "already_running": "Dev server already running",
    "yielded_still_starting": "still starting",
}


@dataclass(frozen=True)
class Baseline:
    since_epoch: float
    log_offset: int


@dataclass(frozen=True)
class KillRecord:
    ts: str
    reason: str
    callers: tuple[str, ...]


@dataclass(frozen=True)
class Report:
    since_epoch: float
    until_epoch: float
    outcomes: dict[str, int]
    kills: tuple[KillRecord, ...]
    log_counts: dict[str, int]

    @property
    def unexplained_sigterms(self) -> int:
        return max(0, self.log_counts["sigterm_received"] - len(self.kills))


def load_baseline(state_dir: Path) -> Baseline | None:
    try:
        raw = json.loads((state_dir / BASELINE_NAME).read_text(encoding="utf-8"))
        return Baseline(float(raw["since_epoch"]), int(raw["log_offset"]))
    except (OSError, ValueError, KeyError, TypeError):
        return None


def save_baseline(state_dir: Path, log_file: Path, now: float) -> Baseline:
    baseline = Baseline(now, _size(log_file))
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / BASELINE_NAME).write_text(
        json.dumps(
            {"since_epoch": baseline.since_epoch, "log_offset": baseline.log_offset}
        ),
        encoding="utf-8",
    )
    return baseline


def build(state_dir: Path, log_file: Path, baseline: Baseline, now: float) -> Report:
    outcomes: Counter[str] = Counter()
    kills: list[KillRecord] = []
    for record in _journal_records(state_dir, baseline.since_epoch):
        if record.get("event") == "kill":
            callers = record.get("caller")
            kills.append(
                KillRecord(
                    str(record.get("ts", "")),
                    str(record.get("reason", "")),
                    tuple(str(c)[:_CLIP] for c in callers[:_CALLER_SHOWN])
                    if isinstance(callers, list)
                    else (),
                )
            )
        elif record.get("event") == "admit":
            outcomes[f"{record.get('reason')}:{record.get('verdict')}"] += 1
    log_counts = _count_log(log_file, baseline.log_offset)
    return Report(baseline.since_epoch, now, dict(outcomes), tuple(kills), log_counts)


def render(report: Report) -> str:
    hours = (report.until_epoch - report.since_epoch) / 3600
    lines = [f"FRONTEND_RESTART_REPORT window={hours:.1f}h"]
    healthy = sum(n for key, n in report.outcomes.items() if key.endswith(":healthy"))
    denied = sum(n for key, n in report.outcomes.items() if key.endswith(":deny"))
    lines.append(f"  restarts prevented by the gate: healthy={healthy} denied={denied}")
    for key, count in sorted(report.outcomes.items()):
        lines.append(f"    admit {key} x{count}")
    lines.append(f"  kills through the gate (journal): {len(report.kills)}")
    for kill in report.kills[-10:]:
        lines.append(
            f"    {kill.ts} reason={kill.reason} via {' < '.join(kill.callers)}"
        )
    lines.append("  frontend.log counters since the baseline:")
    for name, count in report.log_counts.items():
        lines.append(f"    {name}={count}")
    unexplained = report.unexplained_sigterms
    if unexplained == 0 and report.log_counts["stale_lock_reclaims"] == 0:
        lines.append("VERDICT: CLEAN — every SIGTERM has a journal entry")
    else:
        lines.append(
            f"VERDICT: UNEXPLAINED_SIGTERM={unexplained} "
            f"stale_lock_reclaims={report.log_counts['stale_lock_reclaims']} — "
            "a kill path outside the gate (bun run cleanup / dev.ts / dev-lock.ts) is active"
        )
    return "\n".join(lines)


def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _journal_records(
    state_dir: Path, since_epoch: float
) -> Iterator[dict[str, object]]:
    for name in (JOURNAL_NAME + ".1", JOURNAL_NAME):
        try:
            lines = (state_dir / name).read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                record = json.loads(line)
                stamp = datetime.strptime(str(record["ts"]), "%Y-%m-%dT%H:%M:%S%z")
                if stamp.timestamp() >= since_epoch:
                    yield record
            except (ValueError, KeyError, TypeError):
                continue


def _count_log(log_file: Path, offset: int) -> dict[str, int]:
    counts = dict.fromkeys(LOG_MARKERS, 0)
    try:
        with log_file.open("rb") as handle:
            if offset > _size(log_file):  # rotated since the baseline
                offset = 0
            handle.seek(offset)
            for raw in handle:
                text = raw.decode("utf-8", errors="replace")
                for name, marker in LOG_MARKERS.items():
                    if marker in text:
                        counts[name] += 1
    except OSError:
        pass
    return counts
