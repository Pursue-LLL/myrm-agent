"""Append-only, attributable journal of every frontend restart decision and kill.

[INPUT]
  state dir, event fields, ps(1) parent chain of the caller

[OUTPUT]
  append(): one JSON line per event in frontend-restart-journal.jsonl (rotated at 2 MiB)

[POS]
  Attribution. frontend.log records that Next received SIGTERM but not who sent it or why;
  this journal names the caller chain, the reason and the evidence behind each decision.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Mapping
from pathlib import Path

from frontend_lifecycle.process_tree import CommandRunner, run_command

JOURNAL_NAME = "frontend-restart-journal.jsonl"
_ROTATE_BYTES = 2 * 1024 * 1024
_CHAIN_DEPTH = 8
_COMMAND_CLIP = 120
FieldValue = str | int | float | bool | list[str] | None


def caller_chain(start_pid: int, runner: CommandRunner = run_command) -> list[str]:
    """``pid:command`` for ``start_pid`` and its ancestors (closest first)."""
    rows: dict[int, tuple[int, str]] = {}
    for line in runner(["ps", "-axo", "pid=,ppid=,command="]).splitlines():
        fields = line.split(None, 2)
        if len(fields) >= 2 and fields[0].isdigit() and fields[1].isdigit():
            rows[int(fields[0])] = (
                int(fields[1]),
                fields[2] if len(fields) == 3 else "",
            )
    chain: list[str] = []
    pid = start_pid
    while pid > 1 and pid in rows and len(chain) < _CHAIN_DEPTH:
        ppid, command = rows[pid]
        chain.append(f"{pid}:{command[:_COMMAND_CLIP]}")
        pid = ppid
    return chain


def append(
    state_dir: Path,
    event: str,
    fields: Mapping[str, FieldValue],
    *,
    runner: CommandRunner = run_command,
) -> None:
    """Best-effort: the journal must never turn a restart decision into a failure."""
    record: dict[str, FieldValue] = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "event": event,
        "cell": os.environ.get("MYRM_E2E_CELL_ID", ""),
        "test": os.environ.get("PYTEST_CURRENT_TEST", "")[:_COMMAND_CLIP],
        "caller": caller_chain(os.getppid(), runner),
    }
    record.update(fields)
    path = state_dir / JOURNAL_NAME
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        if path.is_file() and path.stat().st_size > _ROTATE_BYTES:
            os.replace(path, path.with_suffix(".jsonl.1"))
        with path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
            )
    except OSError:
        return
