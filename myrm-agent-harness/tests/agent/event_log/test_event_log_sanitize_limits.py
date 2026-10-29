"""The event redactor walks a bounded depth and withholds a payload it cannot redact."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from myrm_agent_harness.agent.event_log._sanitize import _MAX_DEPTH, sanitize_event_data
from myrm_agent_harness.agent.event_log.backends.file_backend import FileEventLogBackend
from myrm_agent_harness.agent.event_log.logger import EventLogger
from myrm_agent_harness.agent.streaming.broadcast.tool_call_broadcaster import ToolCallBroadcaster

_TOKEN = "sk-test-abcdefghijklmnopqrstuvwxyz1234567890abcdef"
_LEAK_DETECTOR = "myrm_agent_harness.agent.event_log._sanitize.redact_leaks"


def _chain(levels: int, leaf: object) -> dict[str, object]:
    """A payload that holds ``leaf`` under exactly ``levels`` nested dicts."""
    payload: dict[str, object] = {"a": leaf}
    for _ in range(levels - 1):
        payload = {"a": payload}
    return payload


def _events(log_file: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines()]


def test_a_payload_at_the_depth_limit_is_redacted_in_place() -> None:
    sanitized = sanitize_event_data(_chain(_MAX_DEPTH, _TOKEN))

    assert _TOKEN not in json.dumps(sanitized)
    assert "nesting too deep" not in json.dumps(sanitized)


def test_a_container_below_the_depth_limit_is_replaced_by_a_marker() -> None:
    sanitized = sanitize_event_data(_chain(_MAX_DEPTH + 1, _TOKEN))

    assert _TOKEN not in json.dumps(sanitized)
    assert "[nesting too deep]" in json.dumps(sanitized)


def test_the_rest_of_the_payload_is_still_redacted_beside_a_too_deep_branch() -> None:
    sanitized = sanitize_event_data({"note": f"key {_TOKEN}", "args": _chain(500, _TOKEN)})

    assert _TOKEN not in json.dumps(sanitized)
    assert str(sanitized["note"]).startswith("key ")


def test_a_payload_that_contains_itself_is_cut_at_the_depth_limit() -> None:
    payload: dict[str, object] = {"token": _TOKEN}
    payload["loop"] = payload

    sanitized = sanitize_event_data(payload)

    assert _TOKEN not in json.dumps(sanitized)
    assert "[nesting too deep]" in json.dumps(sanitized)


def test_a_payload_the_redactor_fails_on_is_withheld() -> None:
    with patch(_LEAK_DETECTOR, side_effect=RuntimeError("boom")):
        sanitized = sanitize_event_data({"args": {"key": _TOKEN}})

    assert sanitized == {"_redaction_failed": True}


def test_the_failure_is_logged_without_the_payload(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING), patch(_LEAK_DETECTOR, side_effect=RuntimeError(f"boom {_TOKEN}")):
        sanitize_event_data({"args": {"key": _TOKEN}})

    assert "RuntimeError" in caplog.text
    assert _TOKEN not in caplog.text


@pytest.mark.asyncio
async def test_an_event_whose_payload_cannot_be_redacted_is_persisted_as_a_marker(tmp_path: Path) -> None:
    event_logger = EventLogger(FileEventLogBackend(tmp_path, "sess-1"), "sess-1")
    await event_logger.start()
    with patch(_LEAK_DETECTOR, side_effect=RuntimeError("boom")):
        await event_logger.log("tool_start", {"tool_name": "bash", "args": {"key": _TOKEN}})
    await event_logger.close()

    log_file = tmp_path / "sess-1.jsonl"
    started = next(event for event in _events(log_file) if event["type"] == "tool_start")
    assert _TOKEN not in log_file.read_text(encoding="utf-8")
    assert started["data"] == {"_redaction_failed": True}


@pytest.mark.asyncio
async def test_a_tool_call_nested_past_the_recursion_limit_does_not_persist_its_token(tmp_path: Path) -> None:
    event_logger = EventLogger(FileEventLogBackend(tmp_path, "sess-1"), "sess-1")
    broadcaster = ToolCallBroadcaster(event_logger=event_logger)
    broadcaster._event_bus = AsyncMock()
    await event_logger.start()
    await broadcaster.on_pre_tool_use(
        "pre_tool_use",
        {
            "tool_name": "bash_code_execute_tool",
            "tool_input": {"command": "ls", "extra": _chain(1200, f"Authorization: Bearer {_TOKEN}")},
            "tool_call_id": "call-1",
        },
    )
    await event_logger.close()

    log_file = tmp_path / "sess-1.jsonl"
    text = log_file.read_text(encoding="utf-8")
    assert any(event["type"] == "tool_start" for event in _events(log_file))
    assert _TOKEN not in text
    assert "[nesting too deep]" in text
