"""Frontend SSE known-type manifest must cover harness AgentEventType values."""

from __future__ import annotations

import json
from pathlib import Path

from myrm_agent_harness.core.events.types import AgentEventType

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "frontend_sse_event_types.json"

# Harness value -> frontend canonical type (see knownSseEventTypes.ts)
_TYPE_ALIASES: dict[str, str] = {
    AgentEventType.CANCELLED.value: "agent_cancelled",
}


def test_harness_agent_event_types_covered_by_frontend_manifest() -> None:
    frontend_types = set(json.loads(_FIXTURE.read_text(encoding="utf-8")))
    harness_types = {member.value for member in AgentEventType}

    missing: set[str] = set()
    for harness_value in harness_types:
        if harness_value in frontend_types:
            continue
        alias = _TYPE_ALIASES.get(harness_value)
        if alias is not None and alias in frontend_types:
            continue
        missing.add(harness_value)

    assert not missing, (
        "Harness AgentEventType values missing from frontend SSE manifest: "
        f"{sorted(missing)}. Regenerate via: "
        "cd myrm-agent-frontend && bun run scripts/export-known-sse-event-types.ts"
    )
