"""The analyzer builds model prompts from the stored log, and the log may predate a redaction rule.

Every event here is stored the way an older version wrote it, with the credential in the clear: nothing is redacted on
the way in, so what the prompt holds is down to the analyzer.
"""

from __future__ import annotations

import json

import pytest

from myrm_agent_harness.agent.event_log.types import EventFilter, EventPayload, StructuredEvent
from myrm_agent_harness.agent.skills.evolution.pipeline.trace_analyzer import TraceAnalyzer, _redacted

_SESSION_ID = "sess-redact"
# A key with no prefix a text rule knows: only the entropy tier masks it.
_KEY = "Zq8Xv2Lm9Tp4Rk7Ws1Yb5Nc3Hd6Jf0GaQw"
_TOKEN = "Kd3Fm8Qw2Xz7Lp5Vt9Rb4Nh6Jc1Ys0UaEt"
# A call id as the providers issue it: a long mixed alphanumeric run a leak scan would take for a key.
_CALL_ID = "call_00_3nrnFlx48weKv0yTotV43729_vtx8763"


class _StoredLog:
    """A backend that holds the events as they were stored."""

    def __init__(self, events: list[StructuredEvent]) -> None:
        self._events = events

    async def get_events(self, session_id: str, event_filter: EventFilter | None = None) -> list[StructuredEvent]:
        if event_filter is None or event_filter.event_types is None:
            return list(self._events)
        return [event for event in self._events if event.event_type in event_filter.event_types]

    async def append(self, events: list[StructuredEvent]) -> None:
        raise AssertionError("the analyzer only reads")

    async def get_all_session_ids(self) -> list[str]:
        return [_SESSION_ID]

    async def close(self) -> None:
        return None


def _event(sequence: int, event_type: str, **data: object) -> StructuredEvent:
    return StructuredEvent(
        sequence=sequence,
        timestamp=1000.0 + sequence,
        event_type=event_type,
        session_id=_SESSION_ID,
        data=EventPayload(**data),
    )


async def test_a_takeover_read_from_an_older_log_carries_no_credential() -> None:
    log = _StoredLog(
        [
            _event(
                1,
                "takeover_trace",
                reason="login",
                pre_url=f"https://app.example.com/cb?access_token={_TOKEN}",
                post_url="https://app.example.com/home",
                post_aria_tree=f"textbox 'token' {_KEY}",
                duration_s=4,
            )
        ]
    )

    evidence = await TraceAnalyzer(log)._extract_takeover_evidence(_SESSION_ID)

    assert "https://app.example.com/home" in evidence
    assert _TOKEN not in evidence
    assert _KEY not in evidence


async def test_a_trajectory_read_from_an_older_log_carries_no_credential() -> None:
    log = _StoredLog(
        [
            _event(1, "tool_start", tool_call_id=_CALL_ID, tool_name="bash", args={"command": "ls"}),
            _event(2, "tool_failure", tool_call_id=_CALL_ID, tool_name="bash", error=f"401 for key {_KEY}"),
        ]
    )

    trajectory = await TraceAnalyzer(log).extract_trajectory(_SESSION_ID, "bash")

    assert "[tool_failure]" in trajectory
    assert "bash" in trajectory
    assert _KEY not in trajectory


async def test_a_malformed_tool_call_kept_as_a_tool_name_carries_no_credential() -> None:
    # A call the model wrote badly is stored whole, arguments included, where the tool name belongs.
    malformed = json.dumps(
        {"name": "bash", "arguments": {"code": f"curl -H 'Authorization: Bearer {_KEY}' https://api.example.com"}}
    )
    log = _StoredLog(
        [
            _event(1, "tool_start", tool_call_id=_CALL_ID, tool_name=malformed, args={}),
            _event(2, "tool_end", tool_call_id=_CALL_ID, tool_name=malformed, result="done"),
        ]
    )

    trajectory = await TraceAnalyzer(log).extract_trajectory(_SESSION_ID, "bash")

    assert "- tool_start:" in trajectory
    assert "api.example.com" in trajectory
    assert _KEY not in trajectory


async def test_a_payload_that_cannot_be_redacted_is_withheld(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(value: object, leaf: object, *, mask_keys: bool = False) -> object:
        raise RuntimeError("redaction failed")

    monkeypatch.setattr("myrm_agent_harness.agent.event_log._sanitize.redact_nested", fail)
    analyzer = TraceAnalyzer(
        _StoredLog(
            [
                _event(1, "tool_start", tool_call_id=_CALL_ID, tool_name="bash", args={"command": "ls"}),
                _event(2, "tool_failure", tool_call_id=_CALL_ID, tool_name="bash", error=f"401 for key {_KEY}"),
            ]
        )
    )

    assert _KEY not in await analyzer.extract_trajectory(_SESSION_ID, "bash")


async def test_a_payload_nested_deeper_than_the_redaction_walks_carries_no_credential() -> None:
    nested: object = {"note": f"password={_KEY}"}
    for _ in range(3_000):
        nested = {"inner": nested}
    stored = _event(1, "tool_start", tool_call_id=_CALL_ID, tool_name="bash", args=nested)

    read = _redacted([stored])

    assert _KEY not in json.dumps(read[0].data.model_dump())


async def test_events_with_nothing_to_redact_are_read_as_stored() -> None:
    stored = _event(
        1,
        "tool_start",
        tool_call_id=_CALL_ID,
        tool_name="web_search",
        args={"query": "weather in Paris", "limit": 5},
        duration_ms=12.5,
    )

    read = _redacted([stored])

    assert [event.data.model_dump() for event in read] == [stored.data.model_dump()]
    assert [event.sequence for event in read] == [stored.sequence]
