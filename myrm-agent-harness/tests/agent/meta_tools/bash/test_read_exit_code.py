"""The exit code a bash tool result reports, read back from what ``format_result`` wrote."""

from __future__ import annotations

import json
from typing import cast

import pytest

from myrm_agent_harness.agent.meta_tools.bash import read_exit_code
from myrm_agent_harness.agent.meta_tools.bash._background.registry import BackgroundProcessRegistry
from myrm_agent_harness.agent.meta_tools.bash._executor.auto_yield import build_auto_yield_return
from myrm_agent_harness.agent.meta_tools.bash._tool.formatting import format_result
from myrm_agent_harness.toolkits.code_execution.executors.models import AsyncProcessProtocol
from tests.agent.meta_tools.bash.test_background_registry import _FakeProc, _wait_until


def _tool_message(stdout: str = "", stderr: str = "", exit_code: int = 0, command: str = "pytest -q") -> str:
    """What the post-call guards see: the tool's ``{"content", "metadata"}`` payload as JSON text."""
    content, _, _ = format_result({"stdout": stdout, "stderr": stderr, "exit_code": str(exit_code)}, command)
    return json.dumps({"content": content, "metadata": {}})


class TestForegroundResults:
    def test_a_failing_command_reports_its_exit_code(self) -> None:
        assert read_exit_code(_tool_message("1 failed, 1 passed", exit_code=1)) == 1

    def test_the_code_is_read_whatever_the_meaning_or_hint_after_it(self) -> None:
        assert read_exit_code(_tool_message(stderr="bash: foo: command not found", exit_code=127)) == 127
        assert read_exit_code(_tool_message("slow", exit_code=124, command="sleep 100")) == 124

    def test_a_command_that_printed_and_exited_zero_reports_zero(self) -> None:
        assert read_exit_code(_tool_message("2 passed")) == 0
        assert read_exit_code(_tool_message("2 passed", stderr="DeprecationWarning")) == 0

    def test_a_command_with_no_output_reports_zero(self) -> None:
        assert read_exit_code(_tool_message(command="tsc --noEmit")) == 0

    def test_the_payload_text_without_json_is_read_the_same(self) -> None:
        payload = json.loads(_tool_message("1 failed", exit_code=1))
        assert read_exit_code(payload["content"]) == 1


class TestWhatTheProgramPrinted:
    def test_a_trailer_in_the_middle_of_the_output_is_the_programs_own_text(self) -> None:
        assert read_exit_code(_tool_message("[exit_code: 1]\nmore output\n2 passed")) == 0

    def test_the_trailer_the_tool_appended_wins_over_one_the_program_printed(self) -> None:
        assert read_exit_code(_tool_message("[exit_code: 0]\n1 failed", exit_code=3)) == 3


class TestResultsThatDoNotSayHowTheCommandEnded:
    def test_a_background_start_has_no_exit_code_yet(self) -> None:
        started = {"content": "Background process started.\n  pid: 4242", "metadata": {"background": True, "pid": 4242}}
        assert read_exit_code(json.dumps(started)) is None

    def test_a_command_still_running_after_the_yield_window_has_none(self) -> None:
        running = {"content": "Command still running after 10s", "metadata": {"auto_yielded": True, "background": True}}
        assert read_exit_code(json.dumps(running)) is None

    def test_a_command_that_finished_inside_the_yield_window_reports_it(self) -> None:
        done = {
            "content": "Command finished during auto-yield window (pid=7).\n[exit_code: 2]",
            "metadata": {"auto_yielded": True, "completed_in_yield_window": True, "pid": 7, "exit_code": 2},
        }
        assert read_exit_code(json.dumps(done)) == 2

    def test_metadata_the_program_could_influence_is_not_an_exit_code(self) -> None:
        payload = json.loads(_tool_message("1 failed", exit_code=1))
        payload["metadata"] = {"exit_code": 0}
        assert read_exit_code(json.dumps(payload)) == 1

    @pytest.mark.parametrize(
        "text",
        [
            "",
            "Error: bash_code_execute_tool execution failed: boom",
            "plain text without the tool's envelope",
            json.dumps({"content": "Error: timed out", "metadata": {}}),
            json.dumps(["not", "a", "payload"]),
        ],
    )
    def test_anything_else_has_none(self, text: str) -> None:
        assert read_exit_code(text) is None


def _has_exited(registry: BackgroundProcessRegistry, pid: int) -> bool:
    info = registry.get(pid)
    return info is not None and info.status != "running"


class TestAgainstTheAutoYieldResults:
    """The payloads ``build_auto_yield_return`` builds for a registered job, not text typed to look like them."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("exit_code", [0, 3])
    async def test_a_job_that_exited_inside_the_window_reports_its_code(self, exit_code: int) -> None:
        registry = BackgroundProcessRegistry()
        proc = _FakeProc(pid=9101, stdout=[b"build ok\n"], stderr=[])
        await registry.register(cast(AsyncProcessProtocol, proc), command="npm run build", session_id="s-exit-code")
        proc.finish(exit_code)
        await _wait_until(lambda: _has_exited(registry, 9101), what="the job to exit")
        info = registry.get(9101)
        assert info is not None

        payload = build_auto_yield_return(info=info, yield_seconds=10, registry=registry)

        assert read_exit_code(json.dumps(payload)) == exit_code

    @pytest.mark.asyncio
    async def test_a_job_still_running_has_no_code_even_when_its_output_quotes_the_marker(self) -> None:
        registry = BackgroundProcessRegistry()
        proc = _FakeProc(pid=9102, stdout=[b"[exit_code: 1]\n"], stderr=[])
        await registry.register(cast(AsyncProcessProtocol, proc), command="npm test", session_id="s-running")
        await _wait_until(lambda: bool(registry.get_output(9102, max_lines=5).get("stdout")), what="its output")
        info = registry.get(9102)
        assert info is not None
        assert info.status == "running"

        payload = build_auto_yield_return(info=info, yield_seconds=10, registry=registry)

        assert "[exit_code: 1]" in str(payload["content"])
        assert read_exit_code(json.dumps(payload)) is None
