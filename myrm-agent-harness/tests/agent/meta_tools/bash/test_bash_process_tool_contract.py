"""The result and schema contract of ``bash_process_tool``: the fields it has, the limits it states."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import cast

import pytest

from myrm_agent_harness.agent.meta_tools.bash._background.registry import get_background_registry
from myrm_agent_harness.agent.meta_tools.bash.bash_process_tools import create_bash_process_tool
from myrm_agent_harness.toolkits.code_execution.executors.models import AsyncProcessProtocol
from tests.agent.meta_tools.bash.test_background_registry import _FakeProc

_SESSION = "contract-session"
_CONFIG = {"configurable": {"context": {"session_id": _SESSION}}}


@pytest.fixture(autouse=True)
def _clean_registry() -> Iterator[None]:
    registry = get_background_registry()
    registry._entries.clear()  # type: ignore[attr-defined]
    yield
    registry._entries.clear()  # type: ignore[attr-defined]


async def _running_job(pid: int, *, stdout: list[bytes]) -> _FakeProc:
    proc = _FakeProc(pid=pid, stdout=stdout, stderr=[])
    await get_background_registry().register(cast(AsyncProcessProtocol, proc), command="generate", session_id=_SESSION)
    await asyncio.sleep(0.05)
    return proc


def test_schema_has_no_incremental_polling_or_filter_fields() -> None:
    schema = create_bash_process_tool().args_schema.model_json_schema()  # type: ignore[union-attr]

    assert set(schema["properties"]) == {"action", "pid", "max_lines", "timeout_seconds", "force", "data"}


@pytest.mark.asyncio
async def test_output_result_carries_no_cursor_or_poll_hint() -> None:
    await _running_job(71001, stdout=[b"line\n"])

    result = await create_bash_process_tool().ainvoke({"action": "output", "pid": 71001}, config=_CONFIG)

    content = result["content"]
    assert content["stdout"] == ["line"]
    assert content["dropped"] is False
    assert "next_cursor" not in content
    assert "poll_hint" not in content
    assert "poll_hint" not in result["metadata"]
    assert "filter" not in result["metadata"]
