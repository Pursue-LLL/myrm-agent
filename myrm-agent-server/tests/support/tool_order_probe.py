"""What a live turn of conflicting tool calls leaves behind, and what that shows about the order they ran in.

[INPUT]
- (standard library only)

[OUTPUT]
- TAGS / STEP_LOG_NAME / LEDGER_NAME / BASH_STEP_KEY: the step names a turn asks for and the files it leaves in the chat's workspace
- Step / read_steps(): the steps the turn's shared log records, in the order they started
- step_script(): the program each step runs; it appends its start and its end to the shared log
- tool_round_ends_ns() / ran_in_one_message(): from the chat's usage ledger, whether two of the steps came from one model message
- bash_tags_in(): the step tags among the bash steps a chat stored

[POS]
Shared by tests/e2e/test_parallel_tool_order_live_chrome_e2e.py; the pure parsing is covered by tests/support/test_tool_order_probe.py.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

BASH_STEP_KEY = "bash_code_execute_tool"
TAGS = ("ALPHA", "BRAVO", "CHARLIE", "DELTA")
STEP_LOG_NAME = "order_e2e.log"
LEDGER_NAME = "usage_ledger.jsonl"

# Finish reasons of a model call that ended by asking for tools (OpenAI-style and Anthropic-style wire values).
_TOOL_ROUND_FINISH_REASONS = frozenset({"tool_calls", "tool_use"})
_STEP_TAG_PATTERN = re.compile(r"step\.py\s+([A-Z]+)")


@dataclass(frozen=True)
class Step:
    tag: str
    started_ns: int
    ended_ns: int


def step_script() -> str:
    """The program each step runs: record start and end in the shared log, with a pause between so overlap shows."""
    return "\n".join(
        (
            "import sys",
            "import time",
            "from pathlib import Path",
            "",
            f"log = Path(__file__).with_name({STEP_LOG_NAME!r})",
            "",
            "",
            "def stamp(phase: str) -> None:",
            '    with log.open("a", encoding="utf-8") as handle:',
            '        handle.write(f"{sys.argv[1]} {phase} {time.time_ns()}\\n")',
            "",
            "",
            'stamp("start")',
            "time.sleep(0.5)",
            'stamp("end")',
            "",
        )
    )


def read_steps(log: Path) -> list[Step]:
    """The steps that ended, in the order they started."""
    if not log.exists():
        return []
    starts: list[tuple[str, int]] = []
    ends: dict[str, int] = {}
    for line in log.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) != 3:
            continue  # a line another step is still writing
        tag, phase, stamp = parts
        if phase == "start":
            starts.append((tag, int(stamp)))
        else:
            ends[tag] = int(stamp)
    return [Step(tag, started, ends[tag]) for tag, started in starts if tag in ends]


def tool_round_ends_ns(ledger: Path) -> list[int]:
    """When each model call that ended by asking for tools finished, from the chat's usage ledger."""
    if not ledger.exists():
        return []
    ends: list[int] = []
    for line in ledger.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue  # a row still being appended
        if row.get("finish_reason") in _TOOL_ROUND_FINISH_REASONS:
            ends.append(int(datetime.fromisoformat(row["ts"]).timestamp() * 1_000_000_000))
    return ends


def ran_in_one_message(steps: list[Step], round_ends_ns: list[int]) -> bool:
    """Whether two consecutive steps came from one model message.

    A step that comes from a later message starts after that message's model call ended, so such a call ended between the
    two starts; when none did, the later step was already part of the message the earlier one came from.
    """
    return any(
        not any(earlier.started_ns < end <= later.started_ns for end in round_ends_ns)
        for earlier, later in zip(steps, steps[1:], strict=False)
    )


def bash_tags_in(messages: Iterable[object]) -> list[str]:
    """The tag of every bash step among the stored messages' progress steps, in the order they are listed."""
    tags: list[str] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        metadata = message.get("metadata")
        raw_steps = message.get("progressSteps") or (metadata.get("progressSteps") if isinstance(metadata, dict) else None)
        for step in raw_steps or []:
            if not isinstance(step, dict) or not str(step.get("step_key") or step.get("tool_name") or "").startswith(
                BASH_STEP_KEY
            ):
                continue
            found = _STEP_TAG_PATTERN.search(json.dumps(step, ensure_ascii=False))
            if found:
                tags.append(found.group(1))
    return tags
