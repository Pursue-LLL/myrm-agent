"""A line the analyzer cannot read in full is refused, and padding cannot push a payload out of the readings.

The readings are bounded (``MAX_COMMAND_READINGS`` texts, ``MAX_READING_CHARS`` characters), so a line can be padded
with decoys until the bounds run out. What a line hands to a shell stands in no other reading, so those scripts are
read first and a line whose scripts do not fit is refused. The commands apart only restate text the readings above
already hold, so a long script or heredoc is judged on what fits and is not refused for its length.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.core.security.shell_wrapper_peel import MAX_COMMAND_READINGS
from myrm_agent_harness.toolkits.code_execution.security.shell_command_analyzer import (
    ThreatLevel,
    analyze_command,
    has_block_threat,
)
from myrm_agent_harness.toolkits.code_execution.security.shell_command_readings import (
    MAX_READING_CHARS,
    command_readings,
)
from myrm_agent_harness.toolkits.code_execution.security.validator import validate_command

_PAYLOAD = "sh -c 'rm -rf ~'"
_GLUED_PAYLOAD = "sh -c 'rm -rf ~&&echo done'"
_SIZES = (0, MAX_COMMAND_READINGS // 2, MAX_COMMAND_READINGS - 1, MAX_COMMAND_READINGS, 4 * MAX_COMMAND_READINGS)


def _padded(decoy: str, count: int, payload: str, separator: str) -> str:
    """*payload* behind *count* distinct decoys; ``{i}`` in *decoy* makes each one different."""
    return separator.join([decoy.format(i=i) for i in range(count)] + [payload])


def _block_categories(command: str) -> set[str]:
    return {threat.category for threat in analyze_command(command) if threat.level is ThreatLevel.BLOCK}


@pytest.mark.parametrize("separator", ["\n", "; "], ids=["lines", "one-line"])
@pytest.mark.parametrize("count", _SIZES)
def test_a_script_behind_plain_padding_is_still_read(count: int, separator: str) -> None:
    assert "dangerous_command" in _block_categories(_padded("echo {i}", count, _PAYLOAD, separator))


@pytest.mark.parametrize("count", _SIZES)
def test_a_script_holding_a_glued_payload_behind_plain_padding_is_still_read(count: int) -> None:
    assert "dangerous_command" in _block_categories(_padded("echo {i}", count, _GLUED_PAYLOAD, "\n"))


def test_scripts_that_fit_the_readings_are_all_read() -> None:
    command = _padded("sh -c 'echo {i}'", MAX_COMMAND_READINGS - 10, _PAYLOAD, "\n")
    assert _block_categories(command) == {"dangerous_command"}


@pytest.mark.parametrize("count", [MAX_COMMAND_READINGS, 4 * MAX_COMMAND_READINGS])
def test_a_line_with_more_scripts_than_the_readings_hold_is_refused(count: int) -> None:
    command = _padded("sh -c 'echo {i}'", count, _PAYLOAD, "\n")
    refusals = [threat for threat in analyze_command(command) if threat.category == "obfuscation"]
    assert [threat.level for threat in refusals] == [ThreatLevel.BLOCK]
    assert "read in full" in refusals[0].detail


def test_a_script_longer_than_the_character_budget_is_refused() -> None:
    command = "sh -c '" + "echo x; " * (MAX_READING_CHARS // 8 + 1) + "'"
    assert "obfuscation" in _block_categories(command)


def test_a_long_script_within_the_character_budget_is_read() -> None:
    command = "sh -c '" + "echo x; " * 1_000 + "rm -rf ~'"
    assert _block_categories(command) == {"dangerous_command"}


def test_an_eval_chain_is_refused_once_it_nests_past_the_bounds() -> None:
    assert "obfuscation" in _block_categories("eval " * 5_000 + "rm -rf ~")
    assert "obfuscation" not in _block_categories("eval " * 20 + "rm -rf ~")


@pytest.mark.parametrize("tail", ["", "bash -c 'echo a'\nsh -c 'echo b'"], ids=["plain", "scripts-at-the-end"])
def test_a_long_script_written_through_a_heredoc_is_not_refused_for_its_length(tail: str) -> None:
    body = "\n".join(f"echo step {i}" for i in range(4 * MAX_COMMAND_READINGS))
    assert has_block_threat(f"cat > run.sh <<'EOF'\n{body}\n{tail}\nEOF") is None


def test_the_bash_validator_tells_the_model_what_to_do_about_a_refused_line() -> None:
    result = validate_command(_padded("sh -c 'echo {i}'", MAX_COMMAND_READINGS, _PAYLOAD, "\n"), check_paths=False)
    assert not result.is_safe
    assert result.reason is not None
    assert "run them as separate commands" in result.reason


def test_the_scripts_of_a_line_are_read_before_its_commands_apart() -> None:
    readings = command_readings("echo a\nsh -c 'echo b; echo c'")
    assert readings.complete
    assert readings.texts == (
        "echo a\nsh -c 'echo b; echo c'",
        "echo b; echo c",
        "echo b",
        "echo c",
        "echo a",
        "sh -c 'echo b; echo c'",
    )


def test_the_commands_apart_fill_what_the_scripts_leave_of_the_bounds() -> None:
    readings = command_readings("\n".join(f"echo {i}" for i in range(4 * MAX_COMMAND_READINGS)))
    assert readings.complete
    assert len(readings.texts) == MAX_COMMAND_READINGS


def test_the_scripts_of_a_line_are_read_when_its_commands_apart_run_out() -> None:
    readings = command_readings(_padded("echo {i}", 4 * MAX_COMMAND_READINGS, "sh -c 'echo last'", "\n"))
    assert readings.complete
    assert "echo last" in readings.texts
