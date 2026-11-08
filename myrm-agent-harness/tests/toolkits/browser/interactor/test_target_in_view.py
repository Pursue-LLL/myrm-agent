"""Interactor _ensure_target_in_view: humanized pre-interaction scroll (CAREFUL only)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.browser.pool.config import HumanizeConfig, HumanizeMode
from myrm_agent_harness.toolkits.browser.session.interactor import Interactor
from myrm_agent_harness.toolkits.browser.snapshot import RefInfo
from tests.toolkits.browser.interactor._support import careful_interactor, doc_container, target_probe


@pytest.mark.asyncio
async def test_ensure_target_in_view_disabled_outside_careful(
    mock_page: MagicMock, refs_map: dict[str, RefInfo]
) -> None:
    """FAST/DEFAULT never pre-scroll: the helper is a pure no-op."""
    for mode in (HumanizeMode.FAST, HumanizeMode.DEFAULT):
        interactor = Interactor(mock_page, refs_map, humanize=HumanizeConfig.from_mode(mode))
        locator = AsyncMock()
        locator.bounding_box.return_value = {
            "x": 100,
            "y": 1800,
            "width": 200,
            "height": 100,
        }
        mock_page.mouse.wheel.reset_mock()
        moved = await interactor._ensure_target_in_view(locator)
        assert moved is False
        mock_page.mouse.wheel.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_target_in_view_already_in_zone_no_scroll(
    mock_page: MagicMock, refs_map: dict[str, RefInfo]
) -> None:
    """A target already inside the center band costs zero wheel events."""
    interactor = careful_interactor(mock_page, refs_map)
    locator = AsyncMock()
    locator.bounding_box.return_value = {
        "x": 100,
        "y": 300,
        "width": 200,
        "height": 100,
    }  # cy = 350, zone (0.3, 0.7) * 720 = (216, 504)
    locator.evaluate.return_value = target_probe(y=300, container=doc_container(0))
    mock_page.mouse.wheel = AsyncMock()

    moved = await interactor._ensure_target_in_view(locator)

    assert moved is False
    mock_page.mouse.wheel.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_target_in_view_scrolls_below_target(mock_page: MagicMock, refs_map: dict[str, RefInfo]) -> None:
    """A target below the viewport is wheeled toward it (humanized notches)."""
    interactor = careful_interactor(mock_page, refs_map)
    locator = AsyncMock()
    locator.bounding_box.return_value = {
        "x": 100,
        "y": 1800,
        "width": 200,
        "height": 100,
    }  # off-viewport → probe reads invisible → main document container
    locator.evaluate.return_value = target_probe(visible=False, y=1800, container=doc_container(1490))
    mock_page.mouse.wheel = AsyncMock()

    with patch("random.random", return_value=0.5):  # no overshoot branch
        moved = await interactor._ensure_target_in_view(locator)

    assert moved is True
    assert mock_page.mouse.wheel.call_count >= 1


@pytest.mark.asyncio
async def test_ensure_target_in_view_scrolls_above_target(mock_page: MagicMock, refs_map: dict[str, RefInfo]) -> None:
    """A target above the viewport is wheeled up (negative delta)."""
    interactor = careful_interactor(mock_page, refs_map)
    locator = AsyncMock()
    locator.bounding_box.return_value = {
        "x": 100,
        "y": -800,
        "width": 200,
        "height": 100,
    }  # cy = -750 < zone_lo = 216
    locator.evaluate.return_value = target_probe(visible=False, y=-800, container=doc_container(-1110))
    mock_page.mouse.wheel = AsyncMock()

    with patch("random.random", return_value=0.5):
        moved = await interactor._ensure_target_in_view(locator)

    assert moved is True
    deltas = [c.args[1] for c in mock_page.mouse.wheel.call_args_list]
    assert all(d < 0 for d in deltas)


@pytest.mark.asyncio
async def test_ensure_target_in_view_measure_failure_no_scroll(
    mock_page: MagicMock, refs_map: dict[str, RefInfo]
) -> None:
    """Unmeasurable targets degrade silently (no scroll, no crash)."""
    interactor = careful_interactor(mock_page, refs_map)
    locator = AsyncMock()
    locator.bounding_box.return_value = None
    mock_page.mouse.wheel = AsyncMock()

    moved = await interactor._ensure_target_in_view(locator)

    assert moved is False
    mock_page.mouse.wheel.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_target_in_view_stops_when_target_enters_zone(
    mock_page: MagicMock, refs_map: dict[str, RefInfo]
) -> None:
    """Per-step re-probe breaks the loop as soon as the target enters the zone."""
    interactor = careful_interactor(mock_page, refs_map)
    locator = AsyncMock()
    # Read order: loop re-check box (below) + probe (invisible → container wheel),
    # then loop re-check box (inside zone) + probe (visible → break).
    locator.bounding_box.side_effect = [
        {"x": 100, "y": 1800, "width": 200, "height": 100},
        {"x": 100, "y": 300, "width": 200, "height": 100},
    ]
    locator.evaluate.side_effect = [
        target_probe(visible=False, y=1800, container=doc_container(1490)),
        target_probe(y=300, container=doc_container(0)),
    ]
    mock_page.mouse.wheel = AsyncMock()

    with (
        patch.object(interactor, "_scroll_deliver", new=AsyncMock()) as mock_deliver,
        patch("random.random", return_value=0.5),
    ):
        moved = await interactor._ensure_target_in_view(locator)

    assert moved is True
    mock_deliver.assert_awaited_once()  # re-probe breaks the loop right after


@pytest.mark.asyncio
async def test_ensure_target_in_view_degrades_on_wheel_error(
    mock_page: MagicMock, refs_map: dict[str, RefInfo]
) -> None:
    """Wheel errors during the best-effort pre-scroll degrade silently."""
    interactor = careful_interactor(mock_page, refs_map)
    locator = AsyncMock()
    locator.bounding_box.return_value = {
        "x": 100,
        "y": 1800,
        "width": 200,
        "height": 100,
    }
    locator.evaluate.return_value = target_probe(visible=False, y=1800, container=doc_container(1490))
    mock_page.mouse.wheel = AsyncMock(side_effect=Exception("Target closed"))

    moved = await interactor._ensure_target_in_view(locator)

    assert moved is False


# =============================================================================
# Defensive branches
# =============================================================================


@pytest.mark.asyncio
async def test_target_box_wait_failure_returns_none(mock_page: MagicMock, refs_map: dict[str, RefInfo]) -> None:
    """wait_for failure yields None so callers degrade gracefully."""
    interactor = careful_interactor(mock_page, refs_map)
    locator = AsyncMock()
    locator.wait_for.side_effect = Exception("timeout")

    assert await interactor._target_box(locator) is None


@pytest.mark.asyncio
async def test_ensure_target_in_view_box_disappears_mid_scroll(
    mock_page: MagicMock, refs_map: dict[str, RefInfo]
) -> None:
    """The target vanishes mid-scroll: report the scroll that already happened."""
    interactor = careful_interactor(mock_page, refs_map)
    locator = AsyncMock()
    off_zone = {"x": 100, "y": 1800, "width": 200, "height": 100}
    # first loop re-check box (below) + probe (invisible → container wheel),
    # then loop re-check box → None → break
    locator.bounding_box.side_effect = [off_zone, None]
    locator.evaluate.return_value = target_probe(visible=False, y=1800, container=doc_container(1490))
    mock_page.mouse.wheel = AsyncMock()

    with (
        patch.object(interactor, "_scroll_deliver", new=AsyncMock()),
        patch("random.random", return_value=0.5),
    ):
        moved = await interactor._ensure_target_in_view(locator)

    assert moved is True  # one wheel delivery already happened


@pytest.mark.asyncio
async def test_ensure_target_in_view_delta_zero_breaks(mock_page: MagicMock, refs_map: dict[str, RefInfo]) -> None:
    """A target within a fraction of the band: delta rounds to zero, loop stops."""
    interactor = careful_interactor(mock_page, refs_map)
    locator = AsyncMock()
    # vh=720 → zone_hi=504. cy = 454.4 + 50 = 504.4 → delta = round(0.4) = 0
    locator.bounding_box.return_value = {
        "x": 100,
        "y": 454.4,
        "width": 200,
        "height": 100,
    }
    locator.evaluate.return_value = target_probe(
        y=454.4,
        container={
            "left": 0,
            "top": 0,
            "width": 1280,
            "height": 720,
            "is_doc": True,
            "delta": 0,
        },
    )
    mock_page.mouse.wheel = AsyncMock()

    assert await interactor._ensure_target_in_view(locator) is False


@pytest.mark.asyncio
async def test_ensure_target_in_view_probe_measure_failure_breaks(
    mock_page: MagicMock, refs_map: dict[str, RefInfo]
) -> None:
    """A rendered-state probe failure yields None and stops the loop silently."""
    interactor = careful_interactor(mock_page, refs_map)
    locator = AsyncMock()
    locator.bounding_box.return_value = {"x": 100, "y": 600, "width": 200, "height": 100}
    locator.evaluate.side_effect = Exception("frame navigated")

    assert await interactor._ensure_target_in_view(locator) is False


@pytest.mark.asyncio
async def test_ensure_target_in_view_scrolls_visible_target_into_band(
    mock_page: MagicMock, refs_map: dict[str, RefInfo]
) -> None:
    """A top-frame target outside the center band is wheeled toward the band."""
    interactor = careful_interactor(mock_page, refs_map)
    locator = AsyncMock()
    # vh=720 → band [216, 504]. First pass: cy=600 (> 504) → wheel; second: cy=400 → stop.
    locator.bounding_box.side_effect = [
        {"x": 100, "y": 550, "width": 200, "height": 100},
        {"x": 100, "y": 350, "width": 200, "height": 100},
    ]
    locator.evaluate.side_effect = [
        target_probe(y=550),  # visible, is_top, container=None → band scroll
        target_probe(y=350),
    ]
    mock_page.mouse.wheel = AsyncMock()

    with (
        patch.object(interactor, "_scroll_move_cursor", new=AsyncMock()) as mock_move,
        patch.object(interactor, "_scroll_deliver", new=AsyncMock()) as mock_deliver,
    ):
        moved = await interactor._ensure_target_in_view(locator)

    assert moved is True
    mock_move.assert_awaited_once()
    mock_deliver.assert_awaited_once()
