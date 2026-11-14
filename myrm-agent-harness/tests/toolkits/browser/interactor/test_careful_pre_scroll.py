"""CAREFUL pre-scroll through nested containers and iframes, and its effect on click."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.browser.exceptions import (
    ClickTargetUnreachableError,
)
from myrm_agent_harness.toolkits.browser.session.interactor import Interactor
from myrm_agent_harness.toolkits.browser.snapshot import RefInfo
from tests.toolkits.browser.interactor._support import careful_interactor, doc_container, target_probe


@pytest.mark.asyncio
async def test_ensure_target_in_view_scrolls_nested_container(
    mock_page: MagicMock, refs_map: dict[str, RefInfo]
) -> None:
    """A target clipped by an inner scroller wheels that scroller, not the page.

    The geometry lies inside the page viewport (y=601), so a zone check alone
    would wrongly treat it as in-view; the rendered probe reads it invisible and
    scrolls the nested overflow:auto ancestor instead.
    """
    interactor = careful_interactor(mock_page, refs_map)
    locator = AsyncMock()
    locator.bounding_box.return_value = {
        "x": 21,
        "y": 601,
        "width": 100,
        "height": 40,
    }
    locator.evaluate.side_effect = [
        target_probe(
            visible=False,
            x=21,
            y=601,
            width=100,
            height=40,
            container={
                "left": 21,
                "top": 0,
                "width": 300,
                "height": 120,
                "is_doc": False,
                "delta": 561,
            },
        ),
        target_probe(
            visible=True,
            x=21,
            y=601,
            width=100,
            height=40,
            container={
                "left": 21,
                "top": 0,
                "width": 300,
                "height": 120,
                "is_doc": False,
                "delta": 0,
            },
        ),
    ]
    mock_page.mouse.wheel = AsyncMock()

    with (
        patch.object(interactor, "_scroll_deliver", new=AsyncMock()) as mock_deliver,
        patch.object(interactor, "_scroll_move_cursor", new=AsyncMock()) as mock_move,
    ):
        moved = await interactor._ensure_target_in_view(locator)

    assert moved is True
    mock_deliver.assert_awaited_once_with(561)
    # wheel dispatch lands inside the scroller (its center), not on the target
    args, _kwargs = mock_move.await_args
    assert args[0] == 171.0  # cx 71 + (container cx 171 - probe cx 71) = 171
    assert args[1] == 60.0  # cy 621 + (container cy 60 - probe cy 621) = 60


@pytest.mark.asyncio
async def test_ensure_target_in_view_visible_in_nested_container_breaks(
    mock_page: MagicMock, refs_map: dict[str, RefInfo]
) -> None:
    """A nested-container target already visible needs no further scrolling."""
    interactor = careful_interactor(mock_page, refs_map)
    locator = AsyncMock()
    locator.bounding_box.return_value = {
        "x": 21,
        "y": 601,
        "width": 100,
        "height": 40,
    }
    locator.evaluate.return_value = target_probe(
        visible=True,
        y=601,
        width=100,
        height=40,
        container={
            "left": 21,
            "top": 0,
            "width": 300,
            "height": 120,
            "is_doc": False,
            "delta": 0,
        },
    )
    mock_page.mouse.wheel = AsyncMock()

    moved = await interactor._ensure_target_in_view(locator)

    assert moved is False
    mock_page.mouse.wheel.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_target_in_view_visible_in_iframe_breaks(
    mock_page: MagicMock, refs_map: dict[str, RefInfo]
) -> None:
    """An iframe target already visible stops — the page band is meaningless there."""
    interactor = careful_interactor(mock_page, refs_map)
    locator = AsyncMock()
    locator.bounding_box.return_value = {
        "x": 45,
        "y": 76,
        "width": 100,
        "height": 40,
    }
    locator.evaluate.return_value = target_probe(
        visible=True,
        is_top=False,
        y=55,
        width=100,
        height=40,
        container={
            "left": 0,
            "top": 0,
            "width": 400,
            "height": 150,
            "is_doc": True,
            "delta": 0,
        },
    )
    mock_page.mouse.wheel = AsyncMock()

    moved = await interactor._ensure_target_in_view(locator)

    assert moved is False
    mock_page.mouse.wheel.assert_not_called()


# =============================================================================
# click with CAREFUL pre-scroll
# =============================================================================


@pytest.mark.asyncio
async def test_interact_click_careful_pre_scrolls(mock_page: MagicMock) -> None:
    """CAREFUL click on an off-band target humanized-wheels it into view first."""
    refs = {
        "e0": RefInfo(
            role="button",
            name="Click Me",
            nth=None,
            bbox={"x": 100, "y": 50},
            position="center-center",
        )
    }
    interactor = careful_interactor(mock_page, refs)
    locator = AsyncMock()
    # Read order: initial target check (below) -> cursor-target clamp (below) ->
    # loop re-check (still below, one deliver) -> loop re-check (now in zone) ->
    # _bezier_move_to (in viewport, Bézier proceeds).
    locator.bounding_box.side_effect = [
        {"x": 100, "y": 1800, "width": 200, "height": 100},  # cy = 1850 > 504
        {"x": 100, "y": 1800, "width": 200, "height": 100},
        {"x": 100, "y": 1800, "width": 200, "height": 100},
        {"x": 100, "y": 400, "width": 200, "height": 100},  # cy = 450 in zone
        {"x": 100, "y": 400, "width": 200, "height": 100},  # inside viewport
    ]
    locator.evaluate.side_effect = [
        target_probe(visible=False, y=1800, container=doc_container(1490)),
        target_probe(visible=False, y=1800, container=doc_container(1490)),
        target_probe(visible=False, y=1800, container=doc_container(1490)),
        target_probe(y=400, container=doc_container(0)),
    ]
    mock_page.mouse = MagicMock()
    mock_page.mouse.move = AsyncMock()
    mock_page.mouse.wheel = AsyncMock()
    mock_page.mouse.down = AsyncMock()
    mock_page.mouse.up = AsyncMock()

    with (
        patch(
            "myrm_agent_harness.toolkits.browser.session.interactor.resolve_locator",
            return_value=locator,
        ),
        patch("random.random", return_value=0.5),
    ):
        result = await interactor.interact("click", "e0")

    assert "Clicked e0" in result
    assert mock_page.mouse.wheel.call_count >= 1
    locator.click.assert_not_called()  # CAREFUL uses Bézier + mouse.down/up
    mock_page.mouse.down.assert_awaited_once()
    mock_page.mouse.up.assert_awaited_once()


@pytest.mark.asyncio
async def test_interact_click_careful_locked_scroll_falls_back(mock_page: MagicMock) -> None:
    """Locked scroll: CAREFUL click falls back to native locator.click.

    When the pre-interaction wheel cannot move the target into the viewport (e.g.
    body {overflow: hidden}), the Bézier move is refused for an off-viewport target
    and the click goes through the native path — scrollIntoViewIfNeeded either
    scrolls it in or fails loudly, never a silent click at the viewport edge.
    """
    refs = {
        "e0": RefInfo(
            role="button",
            name="Click Me",
            nth=None,
            bbox={"x": 100, "y": 50},
            position="center-center",
        )
    }
    interactor = careful_interactor(mock_page, refs)
    locator = AsyncMock()
    locator.bounding_box.return_value = {
        "x": 100,
        "y": 1800,
        "width": 200,
        "height": 100,
    }  # cy = 1850 > zone_hi = 504; box never moves (scroll locked)
    locator.evaluate.return_value = target_probe(visible=False, y=1800, container=doc_container(1490))
    mock_page.mouse = MagicMock()
    mock_page.mouse.move = AsyncMock()
    mock_page.mouse.wheel = AsyncMock()
    mock_page.mouse.down = AsyncMock()
    mock_page.mouse.up = AsyncMock()

    with (
        patch(
            "myrm_agent_harness.toolkits.browser.session.interactor.resolve_locator",
            return_value=locator,
        ),
        patch("random.random", return_value=0.5),
    ):
        result = await interactor.interact("click", "e0")

    assert "Clicked e0" in result
    locator.click.assert_awaited_once()  # native fallback path
    mock_page.mouse.down.assert_not_called()
    mock_page.mouse.up.assert_not_called()


@pytest.mark.asyncio
async def test_interact_click_careful_unreachable_target_raises(
    mock_page: MagicMock,
) -> None:
    """A target with no scroll path fails loudly instead of clicking at the edge."""
    refs = {
        "e0": RefInfo(
            role="button",
            name="Click Me",
            nth=None,
            bbox={"x": 100, "y": 50},
            position="center-center",
        )
    }
    interactor = careful_interactor(mock_page, refs)
    locator = AsyncMock()
    locator.bounding_box.return_value = {
        "x": 100,
        "y": 1800,
        "width": 200,
        "height": 100,
    }  # off-viewport, never moves (scroll locked)
    locator.evaluate.return_value = target_probe(visible=False, y=1800, container=None)
    mock_page.mouse = MagicMock()
    mock_page.mouse.move = AsyncMock()
    mock_page.mouse.wheel = AsyncMock()
    mock_page.mouse.down = AsyncMock()
    mock_page.mouse.up = AsyncMock()

    with (
        patch(
            "myrm_agent_harness.toolkits.browser.session.interactor.resolve_locator",
            return_value=locator,
        ),
        patch("random.random", return_value=0.5),
        pytest.raises(ClickTargetUnreachableError),
    ):
        await interactor.interact("click", "e0")

    locator.click.assert_not_called()


@pytest.mark.asyncio
async def test_interact_click_default_no_pre_scroll(interactor: Interactor, mock_page: MagicMock) -> None:
    """DEFAULT/FAST click never emits pre-interaction wheel events."""
    locator = AsyncMock()

    with patch(
        "myrm_agent_harness.toolkits.browser.session.interactor.resolve_locator",
        return_value=locator,
    ):
        result = await interactor.interact("click", "e0")

    assert "Clicked e0" in result
    mock_page.mouse.wheel.assert_not_called()
