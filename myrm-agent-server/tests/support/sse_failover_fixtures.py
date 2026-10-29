"""Event and chunk factories for the tests of the failover emitter and the stream merge.

[INPUT]
- myrm_agent_harness.toolkits.llms (POS: the failover and recovery event types the emitter serializes)

[OUTPUT]
- make_failover_event / make_recovery_event: realistic harness events
- parse_sse_chunk / try_parse_sse_chunk: the JSON payload of a ``data: {...}`` SSE chunk

[POS]
Server pytest-only helpers shared by ``test_sse_failover_emitter.py`` and ``test_sse_merge_context.py``.
"""

from __future__ import annotations

import json

from myrm_agent_harness.toolkits.llms.errors import FailoverReason
from myrm_agent_harness.toolkits.llms.fallback import FailoverEvent, RecoveryEvent


def make_failover_event() -> FailoverEvent:
    return FailoverEvent(
        from_model="gpt-4",
        to_model="claude-3-opus",
        reason=FailoverReason.RATE_LIMIT,
        error_message="rate limited",
        cooldown_ms=10_000,
        attempt_count=1,
        available_candidates=["gpt-4", "claude-3-opus"],
        scenario="balanced",
    )


def make_recovery_event() -> RecoveryEvent:
    return RecoveryEvent(
        model="gpt-4",
        downtime_ms=15_000,
        probe_count=2,
        was_in_cooldown=True,
    )


def parse_sse_chunk(chunk: str) -> dict[str, object]:
    """Extract the JSON payload from a ``data: {...}\\n\\n`` SSE chunk."""
    assert chunk.startswith("data: "), f"unexpected chunk shape: {chunk!r}"
    json_body = chunk[len("data: ") :].rstrip()
    return json.loads(json_body)


def try_parse_sse_chunk(chunk: str) -> dict[str, object] | None:
    """Best-effort JSON parse; returns None for raw text chunks used in tests."""
    if not chunk.startswith("data: "):
        return None
    try:
        return json.loads(chunk[len("data: ") :].rstrip())
    except json.JSONDecodeError:
        return None
