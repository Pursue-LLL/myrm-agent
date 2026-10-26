"""Browser tools behind the user control: the real tool set is classified, and a held control stops all but one."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain.tools import tool
from langchain_core.tools import BaseTool

from myrm_agent_harness.toolkits.browser.exceptions import UserTakeoverTimeoutError
from myrm_agent_harness.toolkits.browser.session.restricted_ax_session import create_restricted_ax_browser_tools
from myrm_agent_harness.toolkits.browser.tools import create_browser_tools
from myrm_agent_harness.toolkits.browser.tools.cancel_boundary import CANCELLED_RESULT, apply_cancel_boundary
from myrm_agent_harness.toolkits.browser.tools.user_control_gate import (
    _EXEMPT,
    _ROLES,
    REOBSERVE_NOTICE,
    apply_browser_user_control_gate,
)
from myrm_agent_harness.utils.runtime import cancellation
from myrm_agent_harness.utils.runtime.cancellation import CancellationToken, set_cancel_token
from myrm_agent_harness.utils.runtime.user_control import UserControl

# They only wait for the person: navigating needs no earlier look, and manage is a bag of unrelated actions.
_WAIT_ONLY = {"browser_navigate_tool", "browser_manage_tool"}


@pytest.fixture(autouse=True)
def _fast_poll(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(cancellation, "_POLL_INTERVAL_S", 0.02)
    monkeypatch.setattr(cancellation, "_ABORT_GRACE_S", 0.2)
    yield
    set_cancel_token(None)


def _session() -> MagicMock:
    session = MagicMock()
    session.active_tab_crashed = MagicMock(return_value=False)
    session.recover_active_tab = AsyncMock(return_value=None)
    session.take_tab_reset_notice = MagicMock(return_value=None)
    session.user_control = UserControl()
    session.observed_generation = session.user_control.generation
    return session


def _named_tools(calls: list[str]) -> list[BaseTool]:
    """Tools carrying the real names, so the classification is exercised without a browser."""

    def make(name: str) -> BaseTool:
        @tool(name)
        async def run() -> str:
            """Stand-in."""
            calls.append(name)
            return name

        return run

    return [make(name) for name in (*_ROLES, *_EXEMPT, *_WAIT_ONLY)]


class TestClassification:
    def test_every_tool_the_factories_build_is_classified_or_wait_only(self) -> None:
        classified = set(_ROLES) | _EXEMPT | _WAIT_ONLY
        full = {t.name for t in create_browser_tools(_session())}
        restricted = {t.name for t in create_restricted_ax_browser_tools(_session())}

        assert full == classified, "a new or renamed browser tool must be classified here"
        assert restricted == classified - {"browser_execute_script_tool"}

    def test_the_gated_set_still_runs_when_nobody_holds_control(self) -> None:
        calls: list[str] = []
        tools = {t.name: t for t in apply_browser_user_control_gate(_named_tools(calls), _session())}

        assert set(tools) == set(_ROLES) | _EXEMPT | _WAIT_ONLY


class TestWhileAPersonDrives:
    @pytest.mark.asyncio
    async def test_only_the_ask_human_tool_runs(self) -> None:
        calls: list[str] = []
        session = _session()
        tools = {t.name: t for t in apply_browser_user_control_gate(_named_tools(calls), session)}
        session.user_control.acquire()

        assert await tools["browser_ask_human_tool"].ainvoke({}) == "browser_ask_human_tool"
        others = [name for name in tools if name != "browser_ask_human_tool"]
        pending = [asyncio.create_task(tools[name].ainvoke({})) for name in others]
        await asyncio.sleep(0.05)

        assert not any(task.done() for task in pending)
        assert calls == ["browser_ask_human_tool"]
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

    @pytest.mark.asyncio
    async def test_waiting_past_the_budget_raises_the_browsers_takeover_error(self) -> None:
        session = _session()
        (tool_,) = apply_browser_user_control_gate(_named_tools([])[:1], session)
        session.user_control.acquire()

        # The real wait is minutes; shrink it by wrapping the control rather than the gate.
        real_wait = session.user_control.wait_released
        session.user_control.wait_released = lambda _timeout: real_wait(0.05)

        with pytest.raises(UserTakeoverTimeoutError):
            await tool_.ainvoke({})

    @pytest.mark.asyncio
    async def test_stopping_the_run_ends_a_tool_that_is_waiting_for_the_person(self) -> None:
        session = _session()
        tools = apply_cancel_boundary(apply_browser_user_control_gate(_named_tools([]), session), session)
        waiting = next(t for t in tools if t.name == "browser_snapshot_tool")
        session.user_control.acquire()
        token = CancellationToken("req")
        set_cancel_token(token)

        began = time.monotonic()
        stopper = asyncio.get_running_loop().call_later(0.05, token.cancel)
        result = await asyncio.wait_for(waiting.ainvoke({}), timeout=3.0)

        assert result == CANCELLED_RESULT
        assert time.monotonic() - began < 3.0
        stopper.cancel()
        assert session.user_control.held is True


class TestAfterTheHandOver:
    @pytest.mark.asyncio
    async def test_actions_refuse_until_the_model_has_looked_again(self) -> None:
        calls: list[str] = []
        session = _session()
        tools = {t.name: t for t in apply_browser_user_control_gate(_named_tools(calls), session)}
        session.user_control.acquire()
        session.user_control.release()

        for acting in ("browser_interact_tool", "browser_execute_script_tool"):
            assert await tools[acting].ainvoke({}) == REOBSERVE_NOTICE
        assert await tools["browser_navigate_tool"].ainvoke({}) == "browser_navigate_tool"
        assert await tools["browser_manage_tool"].ainvoke({}) == "browser_manage_tool"
        assert calls == ["browser_navigate_tool", "browser_manage_tool"]

        await tools["browser_snapshot_tool"].ainvoke({})

        assert await tools["browser_interact_tool"].ainvoke({}) == "browser_interact_tool"
        assert await tools["browser_execute_script_tool"].ainvoke({}) == "browser_execute_script_tool"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("looking", ["browser_inspect_tool", "browser_extract_tool"])
    async def test_inspect_and_extract_also_count_as_looking(self, looking: str) -> None:
        session = _session()
        tools = {t.name: t for t in apply_browser_user_control_gate(_named_tools([]), session)}
        session.user_control.acquire()
        session.user_control.release()

        await tools[looking].ainvoke({})

        assert await tools["browser_interact_tool"].ainvoke({}) == "browser_interact_tool"

    @pytest.mark.asyncio
    async def test_the_ask_human_tool_does_not_count_as_looking(self) -> None:
        session = _session()
        tools = {t.name: t for t in apply_browser_user_control_gate(_named_tools([]), session)}
        session.user_control.acquire()
        session.user_control.release()

        await tools["browser_ask_human_tool"].ainvoke({})

        assert await tools["browser_interact_tool"].ainvoke({}) == REOBSERVE_NOTICE
