"""``CliRuntime`` turns against scripted CLI stand-ins: launch args, events, verdicts, status, stop and cleanup."""

from __future__ import annotations

import asyncio
import sys
from contextlib import aclosing
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.acp.runtime.cli.runtime import CliRuntime
from myrm_agent_harness.toolkits.acp.types import (
    AcpErrorCode,
    CliSessionRecord,
    McpServerConfig,
    RuntimeConfig,
    RuntimeEventType,
)

from ._fakes import FakeCli, RecordingStore, errors_of, make_runtime, run_turn, text_of, types_of

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the CLI stand-ins are POSIX shebang scripts")

_STREAM_JSON = ["--output-format", "stream-json"]


def _argv(fake_cli: FakeCli, index: int = 0) -> list[str]:
    argv = fake_cli.calls()[index]["argv"]
    assert isinstance(argv, list)
    return argv


class TestProperties:
    def test_claude_and_codex_resume_conversations_and_other_clis_do_not(self) -> None:
        def capabilities(command: str):
            return CliRuntime("t", RuntimeConfig(backend_type="cli", command=command)).capabilities

        for command in ("claude", "codex"):
            caps = capabilities(command)
            assert caps.supports_resume is True
            assert caps.supports_streaming is True
            assert caps.supports_mcp is False
            assert caps.supports_tools is False
        assert capabilities("gemini").supports_resume is False
        assert capabilities("/opt/custom/agent").supports_resume is False

    def test_is_alive_without_a_process_and_name(self) -> None:
        runtime = CliRuntime("my-cli", RuntimeConfig(backend_type="cli", command="claude"))

        assert runtime.is_alive is False
        assert runtime.name == "my-cli"


class TestRunTurn:
    @pytest.mark.asyncio
    async def test_requires_command(self) -> None:
        runtime = CliRuntime("test", RuntimeConfig(backend_type="cli", command=None))

        with pytest.raises(ValueError, match="requires 'command'"):
            async for _ in runtime._do_run_turn("hello", "s1"):
                pass

    @pytest.mark.asyncio
    async def test_a_turn_streams_text_and_usage_then_ends_with_done(self, fake_cli: FakeCli) -> None:
        runtime = make_runtime(fake_cli)
        fake_cli.set_scenario({"text": "the answer"})

        events = await run_turn(runtime)

        assert types_of(events) == [
            RuntimeEventType.STATUS_UPDATE,
            RuntimeEventType.TEXT_DELTA,
            RuntimeEventType.USAGE_UPDATE,
            RuntimeEventType.DONE,
        ]
        assert text_of(events) == "the answer"
        assert events[2].data["input_tokens"] == 10

    @pytest.mark.asyncio
    async def test_the_start_notice_carries_no_workspace_path(self, fake_cli: FakeCli) -> None:
        runtime = make_runtime(fake_cli)

        events = await run_turn(runtime)

        assert events[0].data == {"status": "starting"}

    @pytest.mark.asyncio
    async def test_the_prompt_goes_to_stdin_for_dash_p_and_after_the_args_otherwise(self, fake_cli: FakeCli) -> None:
        await run_turn(make_runtime(fake_cli), "via stdin")
        await run_turn(make_runtime(fake_cli, "my-agent", args=_STREAM_JSON), "positional prompt")

        claude, generic = fake_cli.calls("claude")[0], fake_cli.calls("my-agent")[0]
        assert claude["prompt"] == "via stdin\n"
        assert "via stdin" not in claude["argv"]
        assert generic["argv"][-1] == "positional prompt"

    @pytest.mark.asyncio
    async def test_a_line_longer_than_the_default_stream_limit_does_not_fail_the_turn(self, fake_cli: FakeCli) -> None:
        fake_cli.set_scenario({"big_line": 300_000})

        events = await run_turn(make_runtime(fake_cli, "my-agent", max_response_chars=1_000_000))

        assert not errors_of(events)
        assert text_of(events) == "x" * 300_000 + "ok"
        assert RuntimeEventType.DONE in types_of(events)

    @pytest.mark.asyncio
    async def test_tool_calls_and_results_become_events_in_order(self, fake_cli: FakeCli) -> None:
        fake_cli.set_scenario({"tools": 2, "text": "done"})

        events = await run_turn(make_runtime(fake_cli))

        tools = [e for e in events if e.type in (RuntimeEventType.TOOL_START, RuntimeEventType.TOOL_RESULT)]
        assert [e.type for e in tools] == [
            RuntimeEventType.TOOL_START,
            RuntimeEventType.TOOL_RESULT,
            RuntimeEventType.TOOL_START,
            RuntimeEventType.TOOL_RESULT,
        ]
        assert tools[0].data["tool_name"] == "Bash"
        assert tools[0].data["summary"] == "echo 0"
        assert tools[1].data["tool_call_id"] == tools[0].data["tool_call_id"] == "toolu_0"
        assert tools[1].data["output"] == "out 0"

    @pytest.mark.asyncio
    async def test_streamed_text_is_not_repeated_by_the_full_message(self, fake_cli: FakeCli) -> None:
        fake_cli.set_scenario({"text": "Hello world", "partial": True})

        events = await run_turn(make_runtime(fake_cli))

        deltas = [str(e.data["content"]) for e in events if e.type == RuntimeEventType.TEXT_DELTA]
        assert deltas == ["Hello", " world"]
        assert "--include-partial-messages" in _argv(fake_cli)


class TestFailures:
    @pytest.mark.asyncio
    async def test_a_crash_without_output_is_one_retryable_error_with_the_stderr(self, fake_cli: FakeCli) -> None:
        fake_cli.set_scenario({"fail_before_output": True, "stderr": "fatal: no credentials"})

        events = await run_turn(make_runtime(fake_cli, "my-agent"))

        errors = errors_of(events)
        assert len(errors) == 1
        assert errors[0].data["error"].code is AcpErrorCode.PROCESS_CRASHED
        assert errors[0].data["error"].retryable is True
        assert "fatal: no credentials" in errors[0].data["error"].message
        assert RuntimeEventType.DONE not in types_of(events)

    @pytest.mark.asyncio
    async def test_a_nonzero_exit_after_text_keeps_the_text_and_still_ends_the_turn(
        self, fake_cli: FakeCli, caplog: pytest.LogCaptureFixture
    ) -> None:
        fake_cli.set_scenario({"text": "partial answer", "fail": "crash", "stderr": "late warning"})

        with caplog.at_level("WARNING", logger="myrm_agent_harness.toolkits.acp.runtime.cli.runtime"):
            events = await run_turn(make_runtime(fake_cli))

        assert text_of(events) == "partial answer"
        assert not errors_of(events)
        assert types_of(events)[-1] is RuntimeEventType.DONE
        assert any("cli_process_exited_nonzero" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_the_cli_own_api_error_is_the_error_and_its_notice_is_not_answertext_of(
        self, fake_cli: FakeCli
    ) -> None:
        fake_cli.set_scenario({"text": "", "fail": "api_error"})

        events = await run_turn(make_runtime(fake_cli))

        errors = errors_of(events)
        assert len(errors) == 1
        assert errors[0].data["error"].code is AcpErrorCode.UNKNOWN
        assert errors[0].data["error"].message == "API Error: 400 bad"
        assert errors[0].data["error"].retryable is False
        assert text_of(events) == ""
        assert RuntimeEventType.DONE not in types_of(events)

    @pytest.mark.asyncio
    async def test_the_cli_turn_limit_is_its_own_error_code_after_the_work_it_did(self, fake_cli: FakeCli) -> None:
        fake_cli.set_scenario({"text": "got this far", "fail": "max_turns"})

        events = await run_turn(make_runtime(fake_cli))

        errors = errors_of(events)
        assert [e.data["error"].code for e in errors] == [AcpErrorCode.MAX_TURNS]
        assert errors[0].data["error"].message == "Reached maximum number of turns (3)"
        assert text_of(events) == "got this far"

    @pytest.mark.asyncio
    async def test_a_failure_the_cli_streamed_is_not_reported_a_second_time_for_its_exit_code(
        self, fake_cli: FakeCli
    ) -> None:
        fake_cli.set_scenario({"fail": "turn_failed"})

        events = await run_turn(make_runtime(fake_cli, "codex"))

        errors = errors_of(events)
        assert [e.data["error"].message for e in errors] == ["stream disconnected"]
        assert types_of(events)[-1] is RuntimeEventType.ERROR
        assert RuntimeEventType.DONE not in types_of(events)

    @pytest.mark.asyncio
    async def test_a_missing_executable_is_an_error_event_not_a_raised_exception(self, tmp_path: Path) -> None:
        runtime = CliRuntime("t", RuntimeConfig(backend_type="cli", command=str(tmp_path / "nope"), cwd=str(tmp_path)))

        events = await run_turn(runtime)

        errors = errors_of(events)
        assert len(errors) == 1
        assert "FileNotFoundError" in errors[0].data["error"].message


class TestLaunchArgs:
    @pytest.mark.asyncio
    async def test_claude_gets_verbose_partial_messages_and_its_turn_limit(self, fake_cli: FakeCli) -> None:
        await run_turn(make_runtime(fake_cli, max_turns=10))

        argv = _argv(fake_cli)
        assert "--verbose" in argv
        assert "--include-partial-messages" in argv
        assert argv[argv.index("--max-turns") + 1] == "10"
        assert "--resume" not in argv

    @pytest.mark.asyncio
    async def test_no_turn_limit_flag_when_unlimited_or_for_clis_without_one(self, fake_cli: FakeCli) -> None:
        await run_turn(make_runtime(fake_cli, max_turns=0))
        await run_turn(make_runtime(fake_cli, "codex", args=["exec", "--json"], max_turns=10))
        await run_turn(make_runtime(fake_cli, "gemini", max_turns=10))

        assert all("--max-turns" not in call["argv"] for call in fake_cli.calls())

    @pytest.mark.asyncio
    async def test_codex_runs_exec_in_a_directory_that_is_not_a_git_repository(self, fake_cli: FakeCli) -> None:
        runtime = make_runtime(fake_cli, "codex", args=["exec", "--json"], permission_mode="allow_all")

        await run_turn(runtime)

        argv = _argv(fake_cli)
        assert argv[argv.index("exec") + 1 :][:2] == ["--json", "--skip-git-repo-check"]
        assert argv.index("--sandbox") < argv.index("exec")

    @pytest.mark.asyncio
    async def test_permission_mode_args_are_resolved_per_backend(self, fake_cli: FakeCli) -> None:
        async def launched(name: str, **overrides: object) -> list[str]:
            before = len(fake_cli.calls())
            await run_turn(make_runtime(fake_cli, name, **overrides), "test prompt")
            argv = fake_cli.calls()[before]["argv"]
            assert isinstance(argv, list)
            return argv

        claude_all = await launched("claude", permission_mode="allow_all")
        assert claude_all[claude_all.index("--permission-mode") + 1] == "bypassPermissions"

        claude_safe = await launched("claude", permission_mode="safe")
        assert claude_safe[claude_safe.index("--permission-mode") + 1] == "default"
        assert "--dangerously-skip-permissions" not in claude_safe

        codex_safe = await launched("codex", args=["exec", "--json"], permission_mode="safe")
        assert codex_safe[codex_safe.index("--sandbox") + 1] == "read-only"
        assert "--full-auto" not in codex_safe

        codex_bypass = await launched("codex", args=["exec", "--json"], permission_mode="bypass")
        assert "--dangerously-bypass-approvals-and-sandbox" in codex_bypass
        assert "--sandbox" not in codex_bypass

        codex_dup = await launched("codex", args=["exec", "--json", "-s", "read-only"], permission_mode="allow_all")
        assert codex_dup.count("--sandbox") == 1
        assert codex_dup[codex_dup.index("--sandbox") + 1] == "workspace-write"

        gemini_eq = await launched(
            "gemini", args=[*_STREAM_JSON, "--approval-mode=plan", "--yolo"], permission_mode="allow_all"
        )
        assert gemini_eq.count("--approval-mode") == 1
        assert gemini_eq[gemini_eq.index("--approval-mode") + 1] == "yolo"

        for name, expected in (("gemini", "auto_edit"), ("qwen", "auto-edit")):
            edit = await launched(name, args=[], permission_mode="ask")
            assert edit[edit.index("--approval-mode") + 1] == expected

        gemini_sandbox = await launched("gemini", args=["-s"], permission_mode="safe")
        assert "-s" in gemini_sandbox

        custom = await launched("my-agent", args=["-s", "--silent"], permission_mode="safe")
        assert custom == ["-s", "--silent", "test prompt"]


class TestStatusAndClose:
    @pytest.mark.asyncio
    async def test_status_follows_the_last_process(self, fake_cli: FakeCli) -> None:
        runtime = make_runtime(fake_cli)
        assert await runtime._do_get_status() == "stopped"

        await run_turn(runtime)
        assert await runtime._do_get_status() == "stopped"
        assert runtime.is_alive is False

        fake_cli.set_scenario({"fail_before_output": True})
        await run_turn(runtime)
        assert await runtime._do_get_status() == "error"

    @pytest.mark.asyncio
    async def test_close_releases_the_process_and_the_sessions_held_in_memory(self, fake_cli: FakeCli) -> None:
        runtime = make_runtime(fake_cli)
        await run_turn(runtime)
        assert await runtime._do_resume("s1") is True

        await runtime.close()

        assert runtime._process is None
        assert await runtime._do_resume("s1") is False

    @pytest.mark.asyncio
    async def test_cancel_without_a_process_is_a_no_op(self, fake_cli: FakeCli) -> None:
        await make_runtime(fake_cli)._do_cancel("s1")


class _GatedStore(RecordingStore):
    """A store whose ``load`` parks the turn until released, so a stop can land before any process exists."""

    def __init__(self) -> None:
        super().__init__()
        self.reached = asyncio.Event()
        self.gate = asyncio.Event()

    async def load(self, session_id: str) -> CliSessionRecord | None:
        self.reached.set()
        await self.gate.wait()
        return await super().load(session_id)


class TestStopping:
    @staticmethod
    async def _until_running(fake_cli: FakeCli, runtime: CliRuntime) -> None:
        async with asyncio.timeout(15):
            while not (fake_cli.calls() and runtime.is_alive):
                await asyncio.sleep(0.02)

    @pytest.mark.asyncio
    async def test_stop_ends_a_silent_turn_as_a_cancellation_and_kills_the_cli(self, fake_cli: FakeCli) -> None:
        fake_cli.set_scenario({"hang_before_output": True})
        runtime = make_runtime(fake_cli)
        turn = asyncio.create_task(run_turn(runtime))
        await self._until_running(fake_cli, runtime)

        await runtime.cancel("s1")
        events = await asyncio.wait_for(turn, 15)

        assert [e.data["error"].code for e in errors_of(events)] == [AcpErrorCode.CANCELLED]
        assert RuntimeEventType.DONE not in types_of(events)
        assert runtime.is_alive is False
        assert runtime._process is not None and runtime._process.killed_by_us is True

    @pytest.mark.asyncio
    async def test_a_stop_that_lands_before_the_process_exists_stops_it_as_it_is_spawned(
        self, fake_cli: FakeCli
    ) -> None:
        fake_cli.set_scenario({"hang_before_output": True})
        store = _GatedStore()
        runtime = make_runtime(fake_cli, store=store, timeout_seconds=60)
        turn = asyncio.create_task(run_turn(runtime))
        await asyncio.wait_for(store.reached.wait(), 15)

        await runtime.cancel("s1")
        store.gate.set()
        events = await asyncio.wait_for(turn, 15)

        assert [e.data["error"].code for e in errors_of(events)] == [AcpErrorCode.CANCELLED]
        assert runtime._process is not None and runtime._process.killed_by_us is True

    @pytest.mark.asyncio
    async def test_a_stop_is_forgotten_by_the_next_turn(self, fake_cli: FakeCli) -> None:
        runtime = make_runtime(fake_cli)

        await runtime.cancel("s1")
        events = await run_turn(runtime)

        assert not errors_of(events)
        assert types_of(events)[-1] is RuntimeEventType.DONE

    @pytest.mark.asyncio
    async def test_a_consumer_that_walks_away_kills_the_cli(self, fake_cli: FakeCli) -> None:
        fake_cli.set_scenario({"hang_after_text": True})
        runtime = make_runtime(fake_cli)

        async with aclosing(runtime.run_turn("hello", "s1")) as stream:
            async for event in stream:
                if event.type == RuntimeEventType.TEXT_DELTA:
                    assert runtime.is_alive
                    break

        assert runtime._process is not None
        assert runtime._process.returncode is not None

    @pytest.mark.asyncio
    async def test_a_cancelled_consuming_task_kills_the_cli(self, fake_cli: FakeCli) -> None:
        fake_cli.set_scenario({"hang_before_output": True})
        runtime = make_runtime(fake_cli)
        turn = asyncio.create_task(run_turn(runtime))
        await self._until_running(fake_cli, runtime)

        turn.cancel()
        with pytest.raises(asyncio.CancelledError):
            await turn

        assert runtime._process is not None
        assert runtime._process.returncode is not None

    @pytest.mark.asyncio
    async def test_a_turn_over_its_time_limit_ends_as_a_timeout_and_leaves_no_process(self, fake_cli: FakeCli) -> None:
        fake_cli.set_scenario({"hang_before_output": True})
        runtime = make_runtime(fake_cli, timeout_seconds=1)

        events = await run_turn(runtime)

        errors = errors_of(events)
        assert [e.data["error"].code for e in errors] == [AcpErrorCode.TIMEOUT]
        assert runtime._process is not None
        assert runtime._process.returncode is not None


class TestMcpIgnored:
    @pytest.mark.asyncio
    async def test_session_mcp_servers_are_ignored_with_a_warning(
        self, fake_cli: FakeCli, caplog: pytest.LogCaptureFixture
    ) -> None:
        runtime = make_runtime(fake_cli)
        servers = [
            McpServerConfig(name="fs", command="mcp-fs", args=["--ro"]),
            McpServerConfig(name="git", command="mcp-git"),
        ]

        with caplog.at_level("WARNING", logger="myrm_agent_harness.toolkits.acp.runtime.cli.runtime"):
            events = [e async for e in runtime._do_run_turn("hello", "s1", mcp_servers=servers)]

        assert RuntimeEventType.DONE in types_of(events)
        assert any("cli_runtime_mcp_ignored" in r.message and "mcp_servers=2" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_a_turn_without_mcp_servers_does_not_warn(
        self, fake_cli: FakeCli, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level("WARNING", logger="myrm_agent_harness.toolkits.acp.runtime.cli.runtime"):
            await run_turn(make_runtime(fake_cli))

        assert not any("cli_runtime_mcp_ignored" in r.message for r in caplog.records)
