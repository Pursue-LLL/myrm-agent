"""What the safety rules stopped during one cron run, in the shape the run history stores.

[INPUT]
- myrm_agent_harness.core.security.audit::SecurityDecision, is_blocking_decision (POS: The run's audit entries and the rule for which of them refused an action.)
- myrm_agent_harness.api::redact_sensitive_text (POS: Masks credentials in text before it is stored or shown.)

[OUTPUT]
- blocked_actions_metadata: ``blockedCount`` and ``blockedActions`` run-metadata fragment

[POS]
An unattended job has nobody to tell when a rule stops one of its actions, and the agent's own
account of the run may not mention it. The run record keeps a short, bounded list so the history
can say what was stopped and why, instead of the whole audit log.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from itertools import islice

from myrm_agent_harness.api import redact_sensitive_text
from myrm_agent_harness.core.security.audit import SecurityDecision, is_blocking_decision

# A run that keeps hitting one wall must not grow its record: rows are capped, ``blockedCount`` stays exact.
_MAX_ROWS = 10
_MAX_REASON_CHARS = 160
# Bounds the masking work. A secret cut by this limit lies beyond the characters a row shows.
_MAX_RAW_CHARS = 1000
_WHITESPACE = re.compile(r"\s+")


def blocked_actions_metadata(entries: Sequence[SecurityDecision]) -> dict[str, object]:
    """Run-metadata fragment naming what the safety rules stopped; empty when nothing was stopped."""
    rows: dict[tuple[str, str], int] = {}
    total = 0
    for entry in entries:
        if is_blocking_decision(entry.decision):
            total += 1
            key = (entry.tool_name, entry.reason[:_MAX_RAW_CHARS])
            rows[key] = rows.get(key, 0) + 1
    if not total:
        return {}
    return {
        "blockedCount": total,
        "blockedActions": [
            {"tool": tool, "reason": _display_reason(reason), "count": count}
            for (tool, reason), count in islice(rows.items(), _MAX_ROWS)
        ],
    }


def _display_reason(reason: str) -> str:
    """The reason as one credential-free line short enough for a history row."""
    line = _WHITESPACE.sub(" ", redact_sensitive_text(reason)).strip()
    return line if len(line) <= _MAX_REASON_CHARS else f"{line[: _MAX_REASON_CHARS - 1]}…"
