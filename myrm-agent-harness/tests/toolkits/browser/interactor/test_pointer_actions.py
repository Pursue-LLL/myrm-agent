"""Interactor pointer actions: click, dblclick, hover and drag."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.browser.session.interactor import Interactor
from myrm_agent_harness.toolkits.browser.snapshot import RefInfo

# =============================================================================
# Action: click
# =============================================================================


@pytest.mark.asyncio
async def test_interact_click(interactor: Interactor) -> None:
    """Test click action."""
    mock_locator = AsyncMock()

    with patch(
        "myrm_agent_harness.toolkits.browser.session.interactor.resolve_locator",
        return_value=mock_locator,
    ):
        result = await interactor.interact("click", "e0")

        assert result == "Clicked e0"
        mock_locator.click.assert_called_once()
        _, kwargs = mock_locator.click.call_args
        assert kwargs["timeout"] == 10_000
        assert "delay" in kwargs


# =============================================================================
# Action: dblclick
# =============================================================================


@pytest.mark.asyncio
async def test_interact_dblclick(interactor: Interactor) -> None:
    """Test double-click action."""
    mock_locator = AsyncMock()

    with patch(
        "myrm_agent_harness.toolkits.browser.session.interactor.resolve_locator",
        return_value=mock_locator,
    ):
        result = await interactor.interact("dblclick", "e0")

        assert result == "Double-clicked e0"
        mock_locator.dblclick.assert_called_once()
        _, kwargs = mock_locator.dblclick.call_args
        assert kwargs["timeout"] == 10_000
        assert "delay" in kwargs


# =============================================================================
# Action: hover
# =============================================================================


@pytest.mark.asyncio
async def test_interact_hover(interactor: Interactor) -> None:
    """Test hover action."""
    mock_locator = AsyncMock()

    with patch(
        "myrm_agent_harness.toolkits.browser.session.interactor.resolve_locator",
        return_value=mock_locator,
    ):
        result = await interactor.interact("hover", "e0")

        assert result == "Hovered over e0"
        mock_locator.hover.assert_called_once_with(timeout=10_000)


@pytest.mark.asyncio
async def test_interact_hover_bezier_success(mock_page: MagicMock, refs_map: dict[str, RefInfo]) -> None:
    """Test hover in CAREFUL mode uses Bézier trajectory when bounding_box succeeds."""
    from myrm_agent_harness.toolkits.browser.pool.config import (
        HumanizeConfig,
        HumanizeMode,
    )

    cfg = HumanizeConfig.from_mode(HumanizeMode.CAREFUL)
    interactor = Interactor(mock_page, refs_map, humanize=cfg)

    # evaluate feeds _ensure_target_in_view's rendered-state probe: an AsyncMock
    # default would return an un-awaited coroutine from probe.get(...) and leak a
    # RuntimeWarning. A real dict makes the probe resolve to "visible, top frame,
    # inside the center band" so the pre-interaction scroll exits on the first loop.
    mock_locator = AsyncMock()
    mock_locator.bounding_box = AsyncMock(return_value={"x": 100, "y": 300, "width": 80, "height": 30})
    mock_locator.evaluate = AsyncMock(
        return_value={
            "x": 100.0,
            "y": 300.0,
            "width": 80.0,
            "height": 30.0,
            "visible": True,
            "is_top": True,
            "container": None,
        }
    )
    mock_page.mouse = MagicMock()
    mock_page.mouse.move = AsyncMock()
    mock_page.mouse.wheel = AsyncMock()
    mock_page.wait_for_timeout = AsyncMock()
    mock_page.viewport_size = {"width": 800, "height": 600}

    with patch(
        "myrm_agent_harness.toolkits.browser.session.interactor.resolve_locator",
        return_value=mock_locator,
    ):
        result = await interactor.interact("hover", "e0")

    assert result == "Hovered over e0"
    mock_locator.hover.assert_not_called()
    assert mock_page.mouse.move.call_count >= 1


@pytest.mark.asyncio
async def test_interact_hover_bezier_fallback(mock_page: MagicMock, refs_map: dict[str, RefInfo]) -> None:
    """Test hover in CAREFUL mode falls back to locator.hover() when bounding_box returns None."""
    from myrm_agent_harness.toolkits.browser.pool.config import (
        HumanizeConfig,
        HumanizeMode,
    )

    cfg = HumanizeConfig.from_mode(HumanizeMode.CAREFUL)
    interactor = Interactor(mock_page, refs_map, humanize=cfg)

    mock_locator = AsyncMock()
    mock_locator.bounding_box = AsyncMock(return_value=None)

    with patch(
        "myrm_agent_harness.toolkits.browser.session.interactor.resolve_locator",
        return_value=mock_locator,
    ):
        result = await interactor.interact("hover", "e0")

    assert result == "Hovered over e0"
    mock_locator.hover.assert_called_once_with(timeout=10_000)


# =============================================================================
# Action: drag
# =============================================================================


@pytest.mark.asyncio
async def test_interact_drag_success(interactor: Interactor, mock_page: MagicMock) -> None:
    """Test drag action with valid coordinates."""
    mock_locator = AsyncMock()
    body_locator = MagicMock()
    mock_page.locator.return_value = body_locator

    with patch(
        "myrm_agent_harness.toolkits.browser.session.interactor.resolve_locator",
        return_value=mock_locator,
    ):
        result = await interactor.interact("drag", "e0", "200,150")

        assert result == "Dragged e0 to (200, 150)"
        mock_locator.drag_to.assert_called_once_with(body_locator, target_position={"x": 200, "y": 150})


@pytest.mark.asyncio
async def test_interact_drag_invalid_format(interactor: Interactor) -> None:
    """Test drag with invalid text format."""
    mock_locator = AsyncMock()

    with (
        patch(
            "myrm_agent_harness.toolkits.browser.session.interactor.resolve_locator",
            return_value=mock_locator,
        ),
        pytest.raises(ValueError, match="Drag requires 'x,y' text"),
    ):
        await interactor.interact("drag", "e0", "invalid")


@pytest.mark.asyncio
async def test_interact_drag_non_numeric(interactor: Interactor) -> None:
    """Test drag with non-numeric coordinates."""
    mock_locator = AsyncMock()

    with (
        patch(
            "myrm_agent_harness.toolkits.browser.session.interactor.resolve_locator",
            return_value=mock_locator,
        ),
        pytest.raises(ValueError, match="Drag requires numeric 'x,y'"),
    ):
        await interactor.interact("drag", "e0", "abc,def")
