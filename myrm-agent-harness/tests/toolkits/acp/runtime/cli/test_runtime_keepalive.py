"""A turn says it is still working while its CLI is silent, so a host watching for activity does not give up."""

from __future__ import annotations

import re
import sys

import pytest

from myrm_agent_harness.toolkits.acp.runtime.cli import runtime as runtime_module
from myrm_agent_harness.toolkits.acp.types import RuntimeEventType

from ._fakes import FakeCli, errors_of, make_runtime, run_turn, statuses_of, text_of, types_of

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the CLI stand-ins are POSIX shebang scripts")


@pytest.mark.asyncio
async def test_a_silent_cli_keeps_reporting_how_long_it_has_been_working(
    fake_cli: FakeCli, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runtime_module, "_KEEPALIVE_SECONDS", 0.1)
    fake_cli.set_scenario({"silent_seconds": 0.6, "text": "done"})

    events = await run_turn(make_runtime(fake_cli))

    working = [e for e in events if e.type is RuntimeEventType.STATUS_UPDATE and e.data["status"] == "working"]
    assert len(working) >= 3
    assert all(re.fullmatch(r"\d+s", str(e.data["message"])) for e in working)
    assert not errors_of(events)
    assert text_of(events) == "done"
    assert types_of(events)[-1] is RuntimeEventType.DONE


@pytest.mark.asyncio
async def test_a_cli_that_keeps_talking_is_never_reported_as_waiting(fake_cli: FakeCli) -> None:
    fake_cli.set_scenario({"text": "quick"})

    events = await run_turn(make_runtime(fake_cli))

    assert "working" not in statuses_of(events)


@pytest.mark.parametrize(
    ("seconds", "label"), [(0, "0s"), (5.9, "5s"), (60, "1m 00s"), (125, "2m 05s"), (3600, "60m 00s")]
)
def test_the_running_time_is_told_in_minutes_once_it_is_long(seconds: float, label: str) -> None:
    assert runtime_module._elapsed(seconds) == label
