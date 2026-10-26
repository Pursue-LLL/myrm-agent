"""What a user has to be told when a CLI turn fails: a missing or rejected login, a CLI that is not installed.

Each scenario replays the frames the real binaries print (claude 2.1.x, codex 0.164) through ``CliRuntime``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.acp.runtime.cli.runtime import CliRuntime
from myrm_agent_harness.toolkits.acp.types import AcpErrorCode, RuntimeConfig, RuntimeEventType

from ._fakes import FakeCli, RecordingStore, errors_of, make_runtime, run_turn, statuses_of, text_of, types_of

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the CLI stand-ins are POSIX shebang scripts")


class TestLogin:
    @pytest.mark.asyncio
    async def test_claude_without_a_login_is_one_auth_error_with_the_cli_own_words(self, fake_cli: FakeCli) -> None:
        fake_cli.set_scenario({"text": "", "fail": "not_logged_in"})

        events = await run_turn(make_runtime(fake_cli))

        errors = errors_of(events)
        assert [e.data["error"].code for e in errors] == [AcpErrorCode.AUTH_FAILED]
        assert errors[0].data["error"].message == "Not logged in \u00b7 Please run /login"
        assert errors[0].data["error"].retryable is False
        assert text_of(events) == ""
        assert RuntimeEventType.DONE not in types_of(events)

    @pytest.mark.asyncio
    async def test_a_rejected_codex_login_is_one_auth_error_and_its_retry_notices_are_not_errors(
        self, fake_cli: FakeCli
    ) -> None:
        fake_cli.set_scenario({"fail": "auth"})

        events = await run_turn(make_runtime(fake_cli, "codex"))

        errors = errors_of(events)
        assert [e.data["error"].code for e in errors] == [AcpErrorCode.AUTH_FAILED]
        assert errors[0].data["error"].message.startswith("unexpected status 401 Unauthorized")
        assert types_of(events)[-1] is RuntimeEventType.ERROR
        assert RuntimeEventType.DONE not in types_of(events)


class TestErrorLines:
    @pytest.mark.asyncio
    async def test_a_turn_that_recovers_from_retries_is_not_a_failed_turn(self, fake_cli: FakeCli) -> None:
        fake_cli.set_scenario({"retry_notices": 3, "text": "all good"})

        events = await run_turn(make_runtime(fake_cli, "codex"))

        assert not errors_of(events)
        assert text_of(events) == "all good"
        assert types_of(events)[-1] is RuntimeEventType.DONE

    @pytest.mark.asyncio
    async def test_an_error_line_followed_by_a_failing_exit_names_the_cause_of_the_crash(
        self, fake_cli: FakeCli
    ) -> None:
        fake_cli.set_scenario({"fail": "error_line_only", "stderr": "Reading additional input from stdin..."})

        events = await run_turn(make_runtime(fake_cli, "codex"))

        errors = errors_of(events)
        assert [e.data["error"].code for e in errors] == [AcpErrorCode.PROCESS_CRASHED]
        assert errors[0].data["error"].message == "CLI process exited with code 1: model not supported"


class TestLaunch:
    @pytest.mark.asyncio
    async def test_a_cli_that_is_not_installed_is_one_backend_not_found_error(self, tmp_path: Path) -> None:
        command = str(tmp_path / "not-installed")
        runtime = CliRuntime("t", RuntimeConfig(backend_type="cli", command=command, cwd=str(tmp_path)))

        events = await run_turn(runtime)

        errors = errors_of(events)
        assert [e.data["error"].code for e in errors] == [AcpErrorCode.BACKEND_NOT_FOUND]
        assert errors[0].data["error"].message == f"CLI executable not found: {command}"
        assert types_of(events)[-1] is RuntimeEventType.ERROR

    @pytest.mark.asyncio
    async def test_a_missing_working_directory_is_not_taken_for_a_missing_cli(
        self, fake_cli: FakeCli, tmp_path: Path
    ) -> None:
        runtime = make_runtime(fake_cli, cwd=str(tmp_path / "gone"))

        events = await run_turn(runtime)

        errors = errors_of(events)
        assert [e.data["error"].code for e in errors] == [AcpErrorCode.UNKNOWN]
        assert "FileNotFoundError" in errors[0].data["error"].message

    @pytest.mark.asyncio
    async def test_a_cli_removed_between_turns_fails_once_and_is_not_retried_as_a_new_session(
        self, fake_cli: FakeCli
    ) -> None:
        runtime = make_runtime(fake_cli, store=RecordingStore())
        await run_turn(runtime)
        fake_cli.command().unlink()

        events = await run_turn(runtime)

        assert [e.data["error"].code for e in errors_of(events)] == [AcpErrorCode.BACKEND_NOT_FOUND]
        assert statuses_of(events) == ["starting"]
