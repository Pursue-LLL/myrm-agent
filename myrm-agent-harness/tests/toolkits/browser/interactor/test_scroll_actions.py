"""Interactor scroll and scroll_to_bottom actions."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.browser.session.interactor import Interactor


def _scroll_locator() -> AsyncMock:
    """Locator that resolves to a visible on-page element."""
    locator = AsyncMock()
    locator.bounding_box.return_value = {
        "x": 100,
        "y": 100,
        "width": 200,
        "height": 100,
    }
    return locator


def _scroll_feed(
    mock_page: MagicMock,
    heights: list[int],
    inner_height: int = 800,
    client: int = 800,
    advance: bool = True,
    top: float = 0.0,
) -> None:
    """Wire mock_page to simulate a page whose scrollHeight follows `heights`.

    Each wheel event advances scrollTop by the wheel delta until it reaches the
    container bottom (like a real browser clamps overscroll). When ``advance`` is
    False the wheel never moves scrollTop, simulating a stuck container.
    """
    state = {"top": float(top), "height": float(heights[0]), "client": float(client)}
    idx = {"i": 1}

    async def mock_evaluate(expr: str, arg: object = None) -> object:
        if "innerHeight" in expr:
            return inner_height
        if "elementFromPoint" in expr:
            if idx["i"] < len(heights):
                state["height"] = float(heights[idx["i"]])
                idx["i"] += 1
            return dict(state)
        return 0

    async def mock_wheel(_dx: int, dy: int) -> None:
        if advance:
            state["top"] = min(state["top"] + dy, max(0.0, state["height"] - state["client"]))

    mock_page.evaluate = AsyncMock(side_effect=mock_evaluate)
    mock_page.mouse.wheel = AsyncMock(side_effect=mock_wheel)


# =============================================================================
# Action: scroll
# =============================================================================


@pytest.mark.asyncio
async def test_interact_scroll_positive(interactor: Interactor, mock_page: MagicMock) -> None:
    """Test scroll action with positive delta (FAST: single wheel event, moved)."""
    mock_locator = _scroll_locator()
    _scroll_feed(mock_page, [2000, 2000])

    with patch(
        "myrm_agent_harness.toolkits.browser.session.interactor.resolve_locator",
        return_value=mock_locator,
    ):
        result = await interactor.interact("scroll", "e0", "100")

    assert result == "Scrolled 100px"
    mock_locator.bounding_box.assert_called_once()
    mock_page.mouse.move.assert_called_once()
    mock_page.mouse.wheel.assert_called_once_with(0, 100)


@pytest.mark.asyncio
async def test_interact_scroll_negative(interactor: Interactor, mock_page: MagicMock) -> None:
    """Test scroll action with negative delta (FAST: single wheel event, moved)."""
    mock_locator = _scroll_locator()
    _scroll_feed(mock_page, [2000, 2000], top=500)

    with patch(
        "myrm_agent_harness.toolkits.browser.session.interactor.resolve_locator",
        return_value=mock_locator,
    ):
        result = await interactor.interact("scroll", "e0", "-50")

    assert result == "Scrolled -50px"
    mock_page.mouse.wheel.assert_called_once_with(0, -50)


@pytest.mark.asyncio
async def test_interact_scroll_at_bottom_reports_edge(interactor: Interactor, mock_page: MagicMock) -> None:
    """Scroll past the bottom edge reports the no-op honestly."""
    mock_locator = _scroll_locator()
    _scroll_feed(mock_page, [2000, 2000], client=720, top=1280)  # max scrollTop

    with patch(
        "myrm_agent_harness.toolkits.browser.session.interactor.resolve_locator",
        return_value=mock_locator,
    ):
        result = await interactor.interact("scroll", "e0", "200")

    assert "(already at the bottom)" in result


@pytest.mark.asyncio
async def test_interact_scroll_no_overflow_reports(interactor: Interactor, mock_page: MagicMock) -> None:
    """Scroll on a non-scrollable container reports no overflow."""
    mock_locator = _scroll_locator()
    _scroll_feed(mock_page, [720, 720], client=720)

    with patch(
        "myrm_agent_harness.toolkits.browser.session.interactor.resolve_locator",
        return_value=mock_locator,
    ):
        result = await interactor.interact("scroll", "e0", "100")

    assert "(no scrollable overflow)" in result


@pytest.mark.asyncio
async def test_interact_scroll_blocked_reports(interactor: Interactor, mock_page: MagicMock) -> None:
    """A scrollable container that ignores wheel input is reported honestly."""
    mock_locator = _scroll_locator()
    _scroll_feed(mock_page, [2000, 2000], advance=False, top=100)

    with patch(
        "myrm_agent_harness.toolkits.browser.session.interactor.resolve_locator",
        return_value=mock_locator,
    ):
        result = await interactor.interact("scroll", "e0", "100")

    assert "(no visible movement" in result


@pytest.mark.asyncio
async def test_interact_scroll_invalid_text(interactor: Interactor) -> None:
    """Test scroll with invalid text raises ValueError."""
    mock_locator = AsyncMock()

    with (
        patch(
            "myrm_agent_harness.toolkits.browser.session.interactor.resolve_locator",
            return_value=mock_locator,
        ),
        pytest.raises(ValueError, match="Scroll requires numeric text"),
    ):
        await interactor.interact("scroll", "e0", "not_a_number")


# =============================================================================
# Action: scroll_to_bottom
# =============================================================================


@pytest.mark.asyncio
async def test_scroll_to_bottom_reaches_bottom(interactor: Interactor, mock_page: MagicMock) -> None:
    """scroll_to_bottom stops when scrollHeight stabilizes."""
    mock_locator = _scroll_locator()
    _scroll_feed(mock_page, [1000, 1500, 2000, 2000, 2000, 2000])

    with patch(
        "myrm_agent_harness.toolkits.browser.session.interactor.resolve_locator",
        return_value=mock_locator,
    ):
        result = await interactor.interact("scroll_to_bottom", "e0", "")

    assert "completed" in result
    assert "steps" in result.lower() or "Scrolled" in result
    assert mock_page.mouse.wheel.call_count >= 1


@pytest.mark.asyncio
async def test_scroll_to_bottom_max_steps_reached(interactor: Interactor, mock_page: MagicMock) -> None:
    """scroll_to_bottom respects max_steps when page keeps growing."""
    mock_locator = _scroll_locator()
    _scroll_feed(mock_page, [1000, 1500, 2000, 2500, 3000])

    with patch(
        "myrm_agent_harness.toolkits.browser.session.interactor.resolve_locator",
        return_value=mock_locator,
    ):
        result = await interactor.interact("scroll_to_bottom", "e0", "max_steps=3")

    assert "max_reached" in result
    assert "3 steps" in result


@pytest.mark.asyncio
async def test_scroll_to_bottom_with_custom_params(interactor: Interactor, mock_page: MagicMock) -> None:
    """scroll_to_bottom accepts custom delay_ms and stable_count."""
    mock_locator = _scroll_locator()
    _scroll_feed(mock_page, [1000, 1000, 1000])

    with patch(
        "myrm_agent_harness.toolkits.browser.session.interactor.resolve_locator",
        return_value=mock_locator,
    ):
        result = await interactor.interact("scroll_to_bottom", "e0", "delay_ms=200,stable_count=2")

    assert "completed" in result


@pytest.mark.asyncio
async def test_scroll_to_bottom_single_step_already_at_bottom(interactor: Interactor, mock_page: MagicMock) -> None:
    """Page already at bottom returns completed after stable_count checks."""
    mock_locator = _scroll_locator()
    _scroll_feed(mock_page, [500, 500, 500, 500])

    with patch(
        "myrm_agent_harness.toolkits.browser.session.interactor.resolve_locator",
        return_value=mock_locator,
    ):
        result = await interactor.interact("scroll_to_bottom", "e0", "")

    assert "completed" in result


@pytest.mark.asyncio
async def test_scroll_to_bottom_no_overflow_early_exit(interactor: Interactor, mock_page: MagicMock) -> None:
    """A non-scrollable container exits immediately without wheel events."""
    mock_locator = _scroll_locator()
    _scroll_feed(mock_page, [720, 720], client=720)

    with patch(
        "myrm_agent_harness.toolkits.browser.session.interactor.resolve_locator",
        return_value=mock_locator,
    ):
        result = await interactor.interact("scroll_to_bottom", "e0", "")

    assert "0 steps" in result
    assert "completed" in result
    assert "no scrollable overflow" in result
    mock_page.mouse.wheel.assert_not_called()


@pytest.mark.asyncio
async def test_scroll_to_bottom_viewport_zero_fallback(interactor: Interactor, mock_page: MagicMock) -> None:
    """viewport_h <= 0 falls back to 800."""
    mock_locator = _scroll_locator()
    _scroll_feed(mock_page, [1000, 1000, 1000, 1000], inner_height=0)

    with patch(
        "myrm_agent_harness.toolkits.browser.session.interactor.resolve_locator",
        return_value=mock_locator,
    ):
        result = await interactor.interact("scroll_to_bottom", "e0", "stable_count=2")

    assert "completed" in result


@pytest.mark.asyncio
async def test_scroll_to_bottom_height_output_format(interactor: Interactor, mock_page: MagicMock) -> None:
    """Return string contains steps, elapsed, height range, and status."""
    mock_locator = _scroll_locator()
    _scroll_feed(mock_page, [1000, 2000, 2000, 2000, 2000])

    with patch(
        "myrm_agent_harness.toolkits.browser.session.interactor.resolve_locator",
        return_value=mock_locator,
    ):
        result = await interactor.interact("scroll_to_bottom", "e0", "")

    assert "Scrolled" in result
    assert "steps" in result
    assert "Height:" in result
    assert "Status:" in result
    assert "completed" in result


@pytest.mark.asyncio
async def test_scroll_to_bottom_stuck_repositions_once(interactor: Interactor, mock_page: MagicMock) -> None:
    """A scrollable container that ignores wheel input is retargeted once, then reported stuck."""
    mock_locator = _scroll_locator()
    _scroll_feed(mock_page, [1000, 1500, 2000, 2500, 2500], advance=False)

    with patch(
        "myrm_agent_harness.toolkits.browser.session.interactor.resolve_locator",
        return_value=mock_locator,
    ):
        result = await interactor.interact("scroll_to_bottom", "e0", "")

    assert "stuck" in result
    assert mock_locator.bounding_box.call_count >= 2
