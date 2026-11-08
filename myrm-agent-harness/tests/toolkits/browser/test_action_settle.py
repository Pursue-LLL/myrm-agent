"""The post-action settle asks the page in its main world, says why it ended, and never fails the action.

The wait itself runs in the page (see ``test_post_action_settle_integration``); what is pinned here is how it is asked
and that nothing a page does while it is asked, short of the run being stopped, comes back as an error.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock

import pytest
from patchright.async_api import Error as BrowserDriverError
from patchright.async_api import Page

from myrm_agent_harness.toolkits.browser.wait import _action_settle, settle_after_action

pytestmark = pytest.mark.asyncio


def _page_answering(answer: object) -> AsyncMock:
    page = AsyncMock(spec=Page)
    page.evaluate = AsyncMock(return_value=answer)
    return page


async def test_the_page_is_asked_in_its_main_world_where_the_tracker_lives() -> None:
    page = _page_answering("settled")

    await settle_after_action(page)

    assert page.evaluate.await_args.kwargs == {"isolated_context": False}


async def test_the_page_is_given_the_cap_it_must_end_the_wait_by() -> None:
    page = _page_answering("settled")

    await settle_after_action(page, cap_ms=1234)

    assert page.evaluate.await_args.args[1]["capMs"] == 1234


async def test_the_default_cap_is_the_three_seconds_an_answer_may_be_held_back() -> None:
    page = _page_answering("settled")

    await settle_after_action(page)

    assert page.evaluate.await_args.args[1]["capMs"] == 3000


@pytest.mark.parametrize("reason", ["settled", "no_request", "capped", "untracked"])
async def test_the_reason_the_page_gives_is_returned(reason: str) -> None:
    assert await settle_after_action(_page_answering(reason)) == reason


@pytest.mark.parametrize(
    "failure",
    [
        BrowserDriverError("Execution context was destroyed, most likely because of a navigation"),
        BrowserDriverError("Target page, context or browser has been closed"),
        RuntimeError("the driver went away"),
    ],
)
async def test_a_page_that_cannot_be_probed_ends_the_wait_without_an_error(failure: Exception) -> None:
    page = AsyncMock(spec=Page)
    page.evaluate = AsyncMock(side_effect=failure)

    assert await settle_after_action(page) == "failed"


async def test_a_page_that_never_answers_is_given_up_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_action_settle, "_ANSWER_SLACK_S", 0.05)

    async def never_answers(*_args: object, **_kwargs: object) -> str:
        await asyncio.Event().wait()
        return "unreachable"

    page = AsyncMock(spec=Page)
    page.evaluate = AsyncMock(side_effect=never_answers)
    started = time.perf_counter()

    assert await settle_after_action(page, cap_ms=50) == "failed"
    assert time.perf_counter() - started < 1.0


async def test_a_stopped_run_is_not_swallowed() -> None:
    async def never_answers(*_args: object, **_kwargs: object) -> str:
        await asyncio.Event().wait()
        return "unreachable"

    page = AsyncMock(spec=Page)
    page.evaluate = AsyncMock(side_effect=never_answers)
    settling = asyncio.create_task(settle_after_action(page))
    await asyncio.sleep(0.05)

    settling.cancel()

    with pytest.raises(asyncio.CancelledError):
        await settling
