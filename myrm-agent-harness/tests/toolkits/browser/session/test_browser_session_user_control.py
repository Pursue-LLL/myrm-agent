"""BrowserSession consults the user control: a held control stops its actions and forces a full snapshot after."""

from __future__ import annotations

import asyncio
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.browser.session.browser_session import BrowserSession
from myrm_agent_harness.toolkits.browser.takeover_errors import UserTakeoverDuringScriptError, UserTakeoverTimeoutError
from myrm_agent_harness.utils.runtime.user_control import UserControl, planned_against


@pytest.fixture
def session() -> BrowserSession:
    """A BrowserSession with mocked components and its own UserControl, so no test leaks a hold."""
    with (
        patch("myrm_agent_harness.toolkits.browser.session.browser_session.TabController"),
        patch("myrm_agent_harness.toolkits.browser.session.browser_session.Navigator"),
        patch("myrm_agent_harness.toolkits.browser.session.browser_session.SnapshotManager"),
        patch("myrm_agent_harness.toolkits.browser.session.browser_session.Interactor"),
    ):
        session = BrowserSession(browser_pool=MagicMock(), context_type=MagicMock())
    session.user_control = UserControl()
    session.observed_generation = session.user_control.generation
    session._tab_controller = MagicMock()
    session._tab_controller.get_active_page.return_value = MagicMock()
    session._interactor = MagicMock()
    session._interactor.interact = AsyncMock(return_value="interaction_done")
    session._snapshot_manager = MagicMock()
    session._snapshot_manager.get_snapshot = AsyncMock(return_value=MagicMock(refs={}))
    session._publish_inspector_view = AsyncMock()  # type: ignore[method-assign]
    session._ensure_components = AsyncMock()  # type: ignore[method-assign]
    return session


def _diff_requested(session: BrowserSession) -> bool:
    return bool(cast(MagicMock, session._snapshot_manager).get_snapshot.await_args.kwargs["diff"])


@pytest.mark.asyncio
async def test_nothing_waits_while_nobody_holds_control(session: BrowserSession) -> None:
    await session._ensure_not_user_takeover(timeout=0.05)


@pytest.mark.asyncio
async def test_holding_past_the_timeout_refuses_and_stays_locked(session: BrowserSession) -> None:
    session.user_control.acquire()

    with pytest.raises(UserTakeoverTimeoutError) as raised:
        await session._ensure_not_user_takeover(timeout=0.05)

    assert raised.value.context["timeout_seconds"] == 0.05
    assert session.user_control.held is True


@pytest.mark.asyncio
async def test_interact_waits_for_the_person_and_runs_once_control_returns(session: BrowserSession) -> None:
    session.user_control.acquire()
    interact = asyncio.create_task(session.interact(action="click", ref="ref_123"))

    await asyncio.sleep(0.05)
    assert not interact.done()
    cast(MagicMock, session._interactor).interact.assert_not_called()

    session.user_control.release()
    assert await asyncio.wait_for(interact, timeout=2.0) == "interaction_done"


@pytest.mark.asyncio
async def test_navigate_waits_for_the_person(session: BrowserSession) -> None:
    navigator = MagicMock()
    navigator.goto = AsyncMock(return_value=("Example", "https://example.com", 200))
    session._require_navigator = MagicMock(return_value=navigator)  # type: ignore[method-assign]
    session._require_snapshot_manager = MagicMock(return_value=MagicMock())  # type: ignore[method-assign]
    session.user_control.acquire()

    navigation = asyncio.create_task(session.navigate("https://example.com"))
    await asyncio.sleep(0.05)
    assert not navigation.done()

    session.user_control.release()
    assert "example.com" in await asyncio.wait_for(navigation, timeout=2.0)


@pytest.mark.asyncio
async def test_snapshot_keeps_its_diff_while_the_model_is_up_to_date(session: BrowserSession) -> None:
    await session.snapshot(diff=True)

    assert _diff_requested(session) is True


@pytest.mark.asyncio
async def test_snapshot_is_full_after_a_person_used_the_page_until_it_was_observed(session: BrowserSession) -> None:
    session.user_control.acquire()
    session.user_control.release()

    await session.snapshot(diff=True)
    assert _diff_requested(session) is False, "a diff against the old tree would hide what the person changed"

    session.observed_generation = session.user_control.generation
    await session.snapshot(diff=True)
    assert _diff_requested(session) is True


@pytest.mark.asyncio
async def test_a_new_session_starts_up_to_date_with_earlier_hand_overs() -> None:
    control = UserControl()
    control.acquire()
    control.release()

    with patch("myrm_agent_harness.toolkits.browser.session.browser_session.get_user_control", return_value=control):
        session = BrowserSession(browser_pool=MagicMock(), context_type=MagicMock())

    assert session.observed_generation == control.generation


@pytest.mark.asyncio
async def test_a_step_of_a_plan_runs_while_nobody_took_over(session: BrowserSession) -> None:
    with planned_against(session.observed_generation):
        assert await session.interact(action="click", ref="ref_123") == "interaction_done"


@pytest.mark.asyncio
async def test_a_step_of_a_plan_stops_once_a_person_used_the_page(session: BrowserSession) -> None:
    with planned_against(session.observed_generation):
        session.user_control.acquire()
        session.user_control.release()

        with pytest.raises(UserTakeoverDuringScriptError):
            await session.interact(action="click", ref="ref_123")

    cast(MagicMock, session._interactor).interact.assert_not_called()


@pytest.mark.asyncio
async def test_a_step_that_waited_for_the_person_stops_instead_of_acting_on_what_they_left(
    session: BrowserSession,
) -> None:
    with planned_against(session.observed_generation):
        session.user_control.acquire()
        step = asyncio.create_task(session.interact(action="click", ref="ref_123"))
        await asyncio.sleep(0.05)
        assert not step.done()

        session.user_control.release()
        with pytest.raises(UserTakeoverDuringScriptError):
            await asyncio.wait_for(step, timeout=2.0)

    cast(MagicMock, session._interactor).interact.assert_not_called()


@pytest.mark.asyncio
async def test_calls_outside_a_plan_still_run_after_a_hand_over(session: BrowserSession) -> None:
    session.user_control.acquire()
    session.user_control.release()

    assert await session.interact(action="click", ref="ref_123") == "interaction_done"
