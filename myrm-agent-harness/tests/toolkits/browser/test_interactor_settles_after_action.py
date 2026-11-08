"""Which interactions end with the post-action settle, where it is asked, and what the answer says when it hit its cap.

An action that can make the page call its backend ends by waiting for the requests it started, in the document its
element lives in; only the ones that move the pointer, the focus or the viewport do not. The settle itself is proven
against a real page in ``test_post_action_settle_integration`` and ``test_post_action_settle_scope_integration``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from patchright.async_api import Frame, Page

from myrm_agent_harness.toolkits.browser.session.interactor import Interactor
from myrm_agent_harness.toolkits.browser.snapshot import RefInfo
from myrm_agent_harness.toolkits.browser.wait import capped_note

pytestmark = pytest.mark.asyncio

_REF_SETTLE = "myrm_agent_harness.toolkits.browser.session.interactor.settle_after_action"
_COORDINATE_SETTLE = "myrm_agent_harness.toolkits.browser.session.interactor_coord_mixin.settle_after_action"

_WAITING_ON_AN_ELEMENT = [
    "click",
    "dblclick",
    "type",
    "fill",
    "fill_credential",
    "press",
    "check",
    "uncheck",
    "select",
    "upload_file",
    "drag",
]
_NOT_WAITING_ON_AN_ELEMENT = ["hover", "focus", "scroll", "scroll_to_bottom"]
_WAITING_AT_COORDINATES = [
    ("click", "", None),
    ("dblclick", "", None),
    ("type", "hi", None),
    ("press", "Enter", None),
    ("drag", "", (500.0, 400.0)),
]


async def _act_on_ref(
    action: str, *, ref: str = "e0", page: AsyncMock | None = None, outcome: str = "settled"
) -> tuple[str, AsyncMock]:
    """Run one action on a ref of a mocked page; returns its answer and the settle it asked for."""
    page = page or AsyncMock(spec=Page)
    interactor = Interactor(page, {ref: RefInfo(role="textbox", name="field", nth=0)})

    with (
        patch("myrm_agent_harness.toolkits.browser.session.interactor.resolve_locator", return_value=AsyncMock()),
        patch.object(Interactor, "_perform_ref_action", new=AsyncMock(return_value="Done")),
        patch(_REF_SETTLE, new=AsyncMock(return_value=outcome)) as settle,
    ):
        answer = await interactor.interact(action, ref)

    return answer, settle


@pytest.mark.parametrize("action", _WAITING_ON_AN_ELEMENT)
async def test_an_action_that_can_change_the_page_waits_for_the_requests_it_started(action: str) -> None:
    page = AsyncMock(spec=Page)

    _, settle = await _act_on_ref(action, page=page)

    settle.assert_awaited_once_with(page)


@pytest.mark.parametrize("action", _NOT_WAITING_ON_AN_ELEMENT)
async def test_an_action_that_only_moves_the_pointer_the_focus_or_the_viewport_does_not_wait(action: str) -> None:
    _, settle = await _act_on_ref(action)

    settle.assert_not_awaited()


async def test_an_action_in_an_iframe_waits_in_that_frame() -> None:
    page = AsyncMock(spec=Page)
    iframe = AsyncMock(spec=Frame)
    page.frames = [AsyncMock(spec=Frame), iframe]

    _, settle = await _act_on_ref("click", ref="f1_e0", page=page)

    settle.assert_awaited_once_with(iframe)


async def test_an_answer_says_so_when_the_wait_hit_its_cap() -> None:
    answer, _ = await _act_on_ref("click", outcome="capped")

    assert answer == "Done" + capped_note("capped")


@pytest.mark.parametrize("outcome", ["settled", "no_request", "untracked", "failed"])
async def test_an_answer_is_left_as_it_was_when_the_wait_did_not_hit_its_cap(outcome: str) -> None:
    answer, _ = await _act_on_ref("click", outcome=outcome)

    assert answer == "Done"


def _coordinate_page() -> MagicMock:
    page = MagicMock()
    page.viewport_size = {"width": 1280, "height": 720}
    page.mouse = MagicMock(move=AsyncMock(), click=AsyncMock(), dblclick=AsyncMock(), down=AsyncMock(), up=AsyncMock())
    page.keyboard = MagicMock(type=AsyncMock(), press=AsyncMock())
    return page


async def _act_at_coordinates(
    action: str, text: str, drag_target: tuple[float, float] | None, outcome: str = "settled"
) -> tuple[str, AsyncMock, MagicMock]:
    """Run one action at coordinates on a mocked page; returns its answer, the settle it asked for and the page."""
    page = _coordinate_page()
    interactor = Interactor(page, {})
    target_x, target_y = drag_target if drag_target else (None, None)

    with (
        patch("asyncio.sleep", new=AsyncMock()),
        patch(_COORDINATE_SETTLE, new=AsyncMock(return_value=outcome)) as settle,
    ):
        answer = await interactor.interact_at(action, 400, 300, text, target_x, target_y)

    return answer, settle, page


@pytest.mark.parametrize(("action", "text", "drag_target"), _WAITING_AT_COORDINATES)
async def test_an_action_at_coordinates_waits_for_the_requests_it_started(
    action: str, text: str, drag_target: tuple[float, float] | None
) -> None:
    _, settle, page = await _act_at_coordinates(action, text, drag_target)

    settle.assert_awaited_once_with(page)


async def test_hovering_at_coordinates_does_not_wait() -> None:
    _, settle, _ = await _act_at_coordinates("hover", "", None)

    settle.assert_not_awaited()


@pytest.mark.parametrize(("action", "text", "drag_target"), _WAITING_AT_COORDINATES)
async def test_a_coordinate_answer_says_so_when_the_wait_hit_its_cap(
    action: str, text: str, drag_target: tuple[float, float] | None
) -> None:
    answer, _, _ = await _act_at_coordinates(action, text, drag_target, outcome="capped")

    assert answer.endswith(capped_note("capped"))


@pytest.mark.parametrize(("action", "text", "drag_target"), _WAITING_AT_COORDINATES)
async def test_a_coordinate_answer_is_left_as_it_was_when_the_wait_did_not_hit_its_cap(
    action: str, text: str, drag_target: tuple[float, float] | None
) -> None:
    answer, _, _ = await _act_at_coordinates(action, text, drag_target, outcome="settled")

    assert capped_note("capped") not in answer
