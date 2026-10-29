"""A command an event carries is written without its credentials.

The leak detector recognises token shapes and high-entropy strings; the value after ``--key`` or
``--auth`` is an ordinary word to it. Strings under a key that names a command therefore also go through
the command-line redactor, the one the bash event already uses, so both events of one command read alike.
"""

import json
from pathlib import Path

import pytest

from myrm_agent_harness.agent.event_log.backends.file_backend import FileEventLogBackend
from myrm_agent_harness.agent.event_log.logger import EventLogger
from myrm_agent_harness.core.security.redact import redact_command_line

_VALUE = "Summer2024!"


def _args(key: str, command: str) -> dict[str, object]:
    return {"tool_name": "bash_code_execute_tool", "status": "started", "args": {key: command}}


@pytest.mark.parametrize("key", ["command", "verify_command", "rerun_cmd", "cmd"])
def test_a_string_under_a_command_key_is_masked(key: str) -> None:
    sanitized = EventLogger._sanitize(_args(key, f"tool --key {_VALUE}"))

    masked = sanitized["args"][key]  # type: ignore[index]
    assert _VALUE not in masked
    assert masked.startswith("tool --key")


@pytest.mark.parametrize(
    "command",
    [
        f"tool --key {_VALUE}",
        f"tool --auth {_VALUE}",
        f"tool --bearer {_VALUE}",
        f"psql --password={_VALUE} db",
        f"deploy --client-secret {_VALUE} --region eu",
        f"API_KEY={_VALUE} make deploy",
    ],
)
def test_every_credential_form_of_a_command_is_masked(command: str) -> None:
    assert _VALUE not in str(EventLogger._sanitize(_args("command", command)))


@pytest.mark.parametrize("key", ["query", "command_output", "command_type", "commands", "subcommand"])
def test_a_string_under_another_key_is_left_as_it_is(key: str) -> None:
    payload = _args(key, f"tool --key {_VALUE}")

    assert EventLogger._sanitize(payload) == payload


def test_strings_of_a_list_under_a_command_key_are_masked() -> None:
    sanitized = EventLogger._sanitize({"args": {"command": ["ok", f"tool --key {_VALUE}"]}})

    assert _VALUE not in str(sanitized)
    assert sanitized["args"]["command"][0] == "ok"  # type: ignore[index]


def test_a_key_that_is_not_text_does_not_disable_the_masking() -> None:
    sanitized = EventLogger._sanitize({"args": {7: "plain", "command": f"tool --key {_VALUE}"}})

    assert _VALUE not in str(sanitized)
    assert sanitized["args"][7] == "plain"  # type: ignore[index]


def test_a_command_the_bash_event_already_masked_is_unchanged() -> None:
    masked = redact_command_line(f"tool --key {_VALUE} --verbose")

    assert EventLogger._sanitize({"command": masked}) == {"command": masked}


@pytest.mark.asyncio
async def test_a_logged_tool_command_reaches_the_file_masked(tmp_path: Path) -> None:
    backend = FileEventLogBackend(tmp_path, "sess-1")
    event_logger = EventLogger(backend, "sess-1")
    await event_logger.start()
    await event_logger.log("tool_start", _args("verify_command", f"tool --key {_VALUE}"))
    await event_logger.close()

    lines = (tmp_path / "sess-1.jsonl").read_text(encoding="utf-8").splitlines()
    started = next(event for event in map(json.loads, lines) if event["type"] == "tool_start")
    assert _VALUE not in "".join(lines)
    assert started["data"]["args"]["verify_command"].startswith("tool --key")
