"""What ``bash_process_tool`` tells the model: each rule has one home, and the numbers come from the code."""

from __future__ import annotations

import re
import time
from typing import cast

import pytest

from myrm_agent_harness.agent.meta_tools.bash._background.types import (
    INPUT_WAIT_IDLE_SECONDS,
    WAIT_MAX_SECONDS,
    BackgroundProcessInfo,
    build_input_wait_hint,
)
from myrm_agent_harness.agent.meta_tools.bash.bash_process_tools import (
    create_bash_process_tool,
    resolve_bash_process_tool_description,
)

_IDLE_SECONDS = str(int(INPUT_WAIT_IDLE_SECONDS))
_LOCALES = ("en", "zh")
_OPENING = {"en": "Manage background bash processes", "zh": "管理通过 bash_code_execute_tool"}
_IGNORE_THE_FLAG = {"en": "ignore the flag", "zh": "忽略该标记"}
_RETURNS_IMMEDIATELY = {"en": "returns immediately", "zh": "立即返回"}


def _properties() -> dict[str, dict[str, object]]:
    schema = create_bash_process_tool().args_schema.model_json_schema()  # type: ignore[union-attr]
    return cast(dict[str, dict[str, object]], schema["properties"])


@pytest.mark.parametrize("locale", _LOCALES)
def test_the_description_opens_with_what_the_tool_manages(locale: str) -> None:
    assert resolve_bash_process_tool_description(locale).startswith(_OPENING[locale])


@pytest.mark.parametrize("locale", _LOCALES)
def test_the_description_states_the_idle_flag_once_with_both_readings(locale: str) -> None:
    text = resolve_bash_process_tool_description(locale)

    assert text.count("waiting_for_input") == 1
    rule = text.split("waiting_for_input", 1)[1]
    assert _IDLE_SECONDS in rule
    assert "submit_stdin" in rule
    assert _IGNORE_THE_FLAG[locale] in rule
    assert "blind" not in text.lower()
    assert "盲" not in text


@pytest.mark.parametrize("locale", _LOCALES)
def test_the_description_names_the_auto_detach_entry_the_kill_escalation_and_the_limits(locale: str) -> None:
    text = resolve_bash_process_tool_description(locale)

    assert "yield_after_seconds" in text
    assert _RETURNS_IMMEDIATELY[locale] in text
    assert text.index("SIGTERM") < text.index("SIGKILL")
    assert "force=true" in text
    assert str(WAIT_MAX_SECONDS) in text


def test_the_action_description_has_a_line_for_every_action_and_no_idle_flag_rule() -> None:
    action = _properties()["action"]
    description = str(action["description"])

    for name in cast(list[str], action["enum"]):
        assert f"{name}: " in description
    assert description.index("SIGTERM") < description.index("SIGKILL")
    for moved_to_the_description in ("waiting_for_input", "input_wait_hint", "since_cursor", "still_running", "blind"):
        assert moved_to_the_description not in description


def test_the_pid_description_names_where_a_pid_comes_from_and_forbids_a_job_id() -> None:
    pid = _properties()["pid"]
    description = str(pid["description"])

    assert "start message" in description
    assert "job_id" in description
    assert "do not pass a string" in description
    assert "integer" in {branch.get("type") for branch in cast(list[dict[str, str]], pid["anyOf"])}


def _waiting_job(idle_seconds: int) -> BackgroundProcessInfo:
    now = time.time()
    return BackgroundProcessInfo(
        job_id="job",
        pid=1,
        command="installer",
        session_id="session",
        started_at=now - 600,
        status="running",
        last_output_at=now - idle_seconds,
        waiting_for_input=True,
    )


def test_the_input_wait_hint_reads_the_silence_both_ways() -> None:
    hint = build_input_wait_hint(_waiting_job(idle_seconds=20))

    seconds = re.match(r"No new output for (\d+) s and stdin is open", hint)
    assert seconds is not None
    assert 20 <= int(seconds.group(1)) <= 22
    assert "waiting for input" in hint
    assert "just quiet" in hint
    assert hint.index("submit_stdin") < hint.index("write_stdin")
    assert "close_stdin" in hint
    assert "ignore this hint" in hint


@pytest.mark.asyncio
async def test_a_call_without_a_session_says_so_without_explaining_tenancy() -> None:
    result = await create_bash_process_tool().ainvoke({"action": "list"}, config={})

    assert result["metadata"] == {"error": "missing_session_id"}
    assert "no session_id is bound" in result["content"]
    assert "tenant" not in result["content"]
