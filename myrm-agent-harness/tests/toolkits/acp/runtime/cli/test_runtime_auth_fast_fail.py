"""A login the API keeps rejecting fails the turn within seconds, not after the minutes the CLI itself retries.

Both CLIs answer a 401 by retrying the same request for minutes (measured: claude 183 s, codex 30-58 s) before they
report the failure. The runtime stops the process once the retries show it is hopeless and reports the login problem
with the CLI's own words; a turn that only hit a passing 401 goes on.
"""

from __future__ import annotations

import asyncio
import sys
import time

import pytest

from myrm_agent_harness.toolkits.acp.types import AcpErrorCode, RuntimeEventType

from ._fakes import FakeCli, errors_of, make_runtime, run_turn, text_of, types_of

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the CLI stand-ins are POSIX shebang scripts")

# The fake CLIs hang for two minutes after printing their retries; a runtime that does not stop them fails the bound.
_FAST = 15.0


class TestRejectedLogin:
    @pytest.mark.asyncio
    async def test_claude_that_retries_a_401_three_times_is_stopped_with_an_auth_error(self, fake_cli: FakeCli) -> None:
        fake_cli.set_scenario({"retry_statuses": [401, 401, 401], "hang_after_retries": True})
        runtime = make_runtime(fake_cli)
        started = time.monotonic()

        events = await asyncio.wait_for(run_turn(runtime), timeout=_FAST)

        assert time.monotonic() - started < _FAST
        errors = errors_of(events)
        assert [e.data["error"].code for e in errors] == [AcpErrorCode.AUTH_FAILED]
        assert errors[0].data["error"].message == "API request rejected with HTTP 401 (authentication_failed)"
        assert errors[0].data["error"].retryable is False
        assert types_of(events)[-1] is RuntimeEventType.ERROR
        assert RuntimeEventType.DONE not in types_of(events)
        assert not runtime.is_alive

    @pytest.mark.asyncio
    async def test_codex_that_reconnects_after_a_401_three_times_is_stopped_with_an_auth_error(
        self, fake_cli: FakeCli
    ) -> None:
        fake_cli.set_scenario({"unauthorized_notices": 3, "hang_after_retries": True})
        runtime = make_runtime(fake_cli, "codex")

        events = await asyncio.wait_for(run_turn(runtime), timeout=_FAST)

        errors = errors_of(events)
        assert [e.data["error"].code for e in errors] == [AcpErrorCode.AUTH_FAILED]
        assert errors[0].data["error"].message.startswith("Reconnecting... 4/5 (unexpected status 401 Unauthorized")
        assert RuntimeEventType.DONE not in types_of(events)
        assert not runtime.is_alive

    @pytest.mark.asyncio
    async def test_a_rejected_login_is_not_retried_as_a_fresh_session(self, fake_cli: FakeCli) -> None:
        fake_cli.set_scenario({"retry_statuses": [401, 401, 401], "hang_after_retries": True})
        runtime = make_runtime(fake_cli)

        await asyncio.wait_for(run_turn(runtime), timeout=_FAST)

        assert len(fake_cli.calls("claude")) == 1

    @pytest.mark.asyncio
    async def test_the_runtime_is_usable_for_the_next_turn(self, fake_cli: FakeCli) -> None:
        fake_cli.set_scenario([{"retry_statuses": [401, 401, 401], "hang_after_retries": True}, {"text": "back"}])
        runtime = make_runtime(fake_cli)

        await asyncio.wait_for(run_turn(runtime), timeout=_FAST)
        events = await run_turn(runtime)

        assert not errors_of(events)
        assert text_of(events) == "back"


class TestPassingRejection:
    @pytest.mark.asyncio
    async def test_claude_that_gets_through_after_two_401_retries_finishes_the_turn(self, fake_cli: FakeCli) -> None:
        fake_cli.set_scenario({"retry_statuses": [401, 401], "text": "recovered"})

        events = await run_turn(make_runtime(fake_cli))

        assert not errors_of(events)
        assert text_of(events) == "recovered"
        assert types_of(events)[-1] is RuntimeEventType.DONE

    @pytest.mark.asyncio
    async def test_retries_for_other_statuses_are_left_to_the_cli(self, fake_cli: FakeCli) -> None:
        fake_cli.set_scenario({"retry_statuses": [401, 401, 529, 401, 401], "text": "recovered"})

        events = await run_turn(make_runtime(fake_cli))

        assert not errors_of(events)
        assert text_of(events) == "recovered"

    @pytest.mark.asyncio
    async def test_codex_that_gets_through_after_two_401_reconnects_finishes_the_turn(self, fake_cli: FakeCli) -> None:
        fake_cli.set_scenario({"unauthorized_notices": 2, "text": "recovered"})

        events = await run_turn(make_runtime(fake_cli, "codex"))

        assert not errors_of(events)
        assert text_of(events) == "recovered"
        assert types_of(events)[-1] is RuntimeEventType.DONE
