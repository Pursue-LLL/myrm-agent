"""A tool call that dies because the Playwright driver exited heals the tab it died on, and still fails loudly.

The exit takes the browser down without a crash report, so no check before the call can see it: the failed call is
the first sign. The tab is swapped out then, so the model's next call finds a live one, and the failure itself still
reaches the model instead of being swallowed into a plain result.
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain.tools import tool
from langchain_core.tools import BaseTool

from myrm_agent_harness.toolkits.browser.tools.cancel_boundary import apply_cancel_boundary
from myrm_agent_harness.utils.runtime.cancellation import CancellationToken, set_cancel_token

_DRIVER_GONE = "Page.goto: Connection closed while reading from the driver"


@pytest.fixture(autouse=True)
def _live_token() -> Iterator[None]:
    set_cancel_token(CancellationToken("req"))  # alive: this is not a user stop
    yield
    set_cancel_token(None)


def _session() -> MagicMock:
    session = MagicMock()
    session.active_tab_crashed = MagicMock(return_value=False)
    session.recover_active_tab = AsyncMock(return_value=None)
    session.take_tab_reset_notice = MagicMock(return_value=None)
    return session


def _failing_tool(error: Exception) -> BaseTool:
    @tool("driver_tool")
    async def driver_tool(value: str) -> str:
        """Fails like a call on a driver that exited."""
        raise error

    return driver_tool


async def test_a_call_on_an_exited_driver_heals_the_tab_and_the_failure_still_reaches_the_model() -> None:
    session = _session()
    (guarded,) = apply_cancel_boundary([_failing_tool(Exception(_DRIVER_GONE))], session)

    with pytest.raises(Exception, match=_DRIVER_GONE):
        await guarded.ainvoke({"value": "x"})

    session.recover_active_tab.assert_awaited_once()


async def test_a_driver_exit_wrapped_by_the_tool_heals_too() -> None:
    """The ARIA snapshot reports it as its own error; the driver's message sits on the cause."""
    wrapped = RuntimeError("ARIA acquisition failed")
    wrapped.__cause__ = Exception(_DRIVER_GONE)
    session = _session()
    (guarded,) = apply_cancel_boundary([_failing_tool(wrapped)], session)

    with pytest.raises(RuntimeError, match="ARIA acquisition failed"):
        await guarded.ainvoke({"value": "x"})

    session.recover_active_tab.assert_awaited_once()


async def test_a_failure_that_is_not_a_driver_exit_leaves_the_tab_alone() -> None:
    session = _session()
    (guarded,) = apply_cancel_boundary([_failing_tool(TimeoutError("Page.goto: Timeout 30000ms exceeded"))], session)

    with pytest.raises(TimeoutError):
        await guarded.ainvoke({"value": "x"})

    session.recover_active_tab.assert_not_awaited()
