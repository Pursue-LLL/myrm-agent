"""A credential-named field an event carries is written masked, whatever the shape of its value.

The leak detector recognises token shapes and high-entropy strings; a ``Cookie`` value (``sessionid=…``) or a bare
password has no such shape. The name of the field says what the value does not, so ``sanitize_event_data`` masks the
value of a credential-named field like the exits do (chat export, dataset export, approval display) and leaves the
other fields to the light leak scan that runs on every event.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from myrm_agent_harness.agent.event_log._sanitize import sanitize_event_data
from myrm_agent_harness.agent.event_log.backends.file_backend import FileEventLogBackend
from myrm_agent_harness.agent.event_log.logger import EventLogger

_COOKIE = "sessionid=abc123def456ghi789"
_BASIC = "Basic dXNlcjpwYXNzd29yZA=="
_PASSWORD = "hunter2xyz"
_NESTED_PASSWORD = "correct-horse-battery"


def _tool_start() -> dict[str, object]:
    return {
        "tool_name": "http_request",
        "status": "started",
        "args": {
            "url": "https://api.example.com/v1/me",
            "headers": {"Cookie": _COOKIE, "Authorization": _BASIC},
            "password": _PASSWORD,
            "steps": [{"db_password": _NESTED_PASSWORD}],
        },
    }


def test_the_value_of_a_credential_named_field_is_masked_at_any_depth() -> None:
    written = str(sanitize_event_data(_tool_start()))

    for value in (_COOKIE, _BASIC, _PASSWORD, _NESTED_PASSWORD):
        assert value not in written


def test_the_fields_around_a_credential_are_left_as_they_are() -> None:
    sanitized = sanitize_event_data(_tool_start())

    args = sanitized["args"]
    assert isinstance(args, dict)
    assert args["url"] == "https://api.example.com/v1/me"
    assert sanitized["tool_name"] == "http_request"


@pytest.mark.parametrize("key", ["max_tokens", "tokens", "token_count", "cache_key", "author", "keyboard", "note"])
def test_an_ordinary_field_is_not_taken_for_a_credential(key: str) -> None:
    payload: dict[str, object] = {"args": {key: "4096", "count": 4096}}

    assert sanitize_event_data(payload) == payload


def test_a_variable_reference_under_a_credential_name_stays_readable() -> None:
    payload: dict[str, object] = {"args": {"api_key": "${API_KEY}"}}

    assert sanitize_event_data(payload) == payload


def test_a_secret_shape_in_an_ordinary_field_is_still_masked() -> None:
    token = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"

    assert token not in str(sanitize_event_data({"args": {"note": f"deploy with {token}"}}))


@pytest.mark.asyncio
async def test_the_event_file_holds_no_credential_of_a_credential_named_field(tmp_path: Path) -> None:
    backend = FileEventLogBackend(tmp_path, "sess-1")
    event_logger = EventLogger(backend, "sess-1")
    await event_logger.start()
    await event_logger.log("tool_start", _tool_start())
    await event_logger.close()

    written = (tmp_path / "sess-1.jsonl").read_text(encoding="utf-8")
    tool_start = next(json.loads(line) for line in written.splitlines() if '"tool_start"' in line)
    for value in (_COOKIE, _BASIC, _PASSWORD, _NESTED_PASSWORD):
        assert value not in written
    assert tool_start["data"]["args"]["url"] == "https://api.example.com/v1/me"
