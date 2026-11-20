"""The batch risk layer judges every command a shell line runs, not only the first word of the line."""

from __future__ import annotations

import pytest

from myrm_agent_harness.core.security.device_policy import BatchRiskAssessment, evaluate_batch_risk


def _assess(command: str, tool: str = "bash_code_execute_tool") -> BatchRiskAssessment:
    return evaluate_batch_risk([{"name": tool, "args": {"command": command}}])


@pytest.mark.parametrize("tool", ["shell_exec", "code_interpreter", "bash_code_execute_tool"])
def test_every_shell_tool_is_read(tool: str) -> None:
    assert _assess("rm -rf build", tool).is_high_risk is True


@pytest.mark.parametrize(
    "command",
    [
        "echo a;rm -rf build",
        "echo a ; rm -rf build",
        "echo a && rm -rf build",
        "echo a || rm -rf build",
        "cat list | rm -rf build",
        "echo a & rm -rf build",
        "echo a\nrm -rf build",
        "echo a\r\nrm -rf build",
        "# clean up\nrm -rf build",
        "cd build\n\nrm -rf cache",
    ],
)
def test_a_high_risk_command_behind_any_separator_escalates(command: str) -> None:
    assessment = _assess(command)

    assert assessment.is_high_risk is True
    assert assessment.requires_dual_insurance is True
    assert assessment.allow_always_blocked is True
    assert any("rm -rf" in reason for reason in assessment.reasons)


@pytest.mark.parametrize(
    "command",
    [
        "if true; then rm -rf build; fi",
        "if [ -d build ]\nthen\n  rm -rf build\nfi",
        "for f in a b; do rm -f $f; done",
        "while true; do kill $pid; done",
        "if ! rm -rf build; then echo failed; fi",
        "{ rm -rf build; }",
        "! rm -rf build",
        "time rm -rf build",
    ],
)
def test_a_verb_behind_a_shell_keyword_counts(command: str) -> None:
    assert _assess(command).is_high_risk is True


@pytest.mark.parametrize(
    "command",
    [
        'echo "done; rm -rf build"',
        "echo 'a && rm -rf build'",
        'grep -E "a|rm -rf" notes.txt',
        "echo hi # ; rm -rf build",
        "ls -la",
        "git status && git log --oneline",
        "cat a | grep b | wc -l",
        "echo ok; pwd",
        "cd build\nmake\nls",
        "if true; then echo yes; fi",
        "for f in a b; do echo $f; done",
    ],
)
def test_text_that_only_mentions_a_verb_stays_clear(command: str) -> None:
    assessment = _assess(command)

    assert assessment.is_high_risk is False
    assert assessment.reasons == ()


@pytest.mark.parametrize(
    "command",
    [
        "Remove-Item -Recurse -Force C:/",
        "remove-item old.log",
        "ri old.log",
        "rd /s /q C:\\",
        "rmdir old",
        "Format-Volume -DriveLetter C",
        "Clear-Disk -Number 1",
        "Stop-Process -Name chrome -Force",
        "Restart-Computer -Force",
        "Stop-Computer",
        "Get-ChildItem; Remove-Item old.log",
    ],
)
def test_windows_destructive_commands_rank_with_their_posix_counterparts(command: str) -> None:
    assessment = _assess(command)

    assert assessment.is_high_risk is True
    assert assessment.requires_dual_insurance is True


def test_two_high_risk_commands_on_separate_lines_count_as_a_batch() -> None:
    assert _assess("rm a\nrm b").is_batch is True
    assert _assess("rm a\necho done").is_batch is False


@pytest.mark.parametrize(
    "command",
    [
        "\\rm -rf build",
        '"rm" -rf build',
        "'rm' -rf build",
        "r\\m -rf build",
        "(rm -rf build)",
        "(cd build; rm -rf cache)",
        "( rm -rf build ) && echo done",
    ],
)
def test_the_program_is_the_word_the_shell_runs(command: str) -> None:
    assert _assess(command).is_high_risk is True


def test_the_reason_names_the_command_as_written() -> None:
    assert _assess('echo a; "rm" -rf "my dir"').reasons == (
        'Batch contains high-risk destructive operations: "rm" -rf "my dir"',
    )


@pytest.mark.parametrize("separator", [";", "&&", "||", "\n"])
def test_the_separator_does_not_change_the_verdict(separator: str) -> None:
    assessment = _assess(f"rm -rf build{separator}echo done")

    assert assessment.is_high_risk is True
    assert assessment.reasons == ("Batch contains high-risk destructive operations: rm -rf build",)
