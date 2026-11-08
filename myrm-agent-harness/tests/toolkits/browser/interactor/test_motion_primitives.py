"""Interactor motion primitives: wheel delivery, scroll parameters and bezier mouse movement."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.browser.pool.config import HumanizeConfig, HumanizeMode
from myrm_agent_harness.toolkits.browser.session.interactor import Interactor
from myrm_agent_harness.toolkits.browser.session.interactor_scroll_mixin import (
    _SCROLL_MEASURE_JS,
    _parse_scroll_params,
)
from myrm_agent_harness.toolkits.browser.snapshot import RefInfo
from tests.toolkits.browser.interactor._support import careful_interactor

# =============================================================================
# _scroll_deliver: mode-specific wheel delivery
# =============================================================================


def _wheel_deltas(mock_page: MagicMock) -> list[int]:
    """Signed wheel deltas delivered via mouse.wheel, in call order."""
    return [call.args[1] for call in mock_page.mouse.wheel.call_args_list]


@pytest.mark.asyncio
async def test_scroll_deliver_fast_single_wheel(mock_page: MagicMock) -> None:
    """FAST delivers the whole delta as one wheel event (zero humanization cost)."""
    interactor = Interactor(mock_page, {}, humanize=HumanizeConfig.from_mode(HumanizeMode.FAST))

    await interactor._scroll_deliver(300)

    assert _wheel_deltas(mock_page) == [300]


@pytest.mark.asyncio
async def test_scroll_deliver_default_wheel_burst(mock_page: MagicMock) -> None:
    """DEFAULT splits the delta into a burst of small wheel notches."""
    interactor = Interactor(mock_page, {}, humanize=HumanizeConfig.from_mode(HumanizeMode.DEFAULT))

    await interactor._scroll_deliver(300)

    deltas = _wheel_deltas(mock_page)
    assert len(deltas) > 1, "expected a multi-event burst"
    assert sum(deltas) == 300


@pytest.mark.asyncio
async def test_scroll_deliver_careful_notch_rhythm(mock_page: MagicMock) -> None:
    """CAREFUL delivers notches summing to the delta and settles without overshoot."""
    interactor = Interactor(mock_page, {}, humanize=HumanizeConfig.from_mode(HumanizeMode.CAREFUL))

    with patch("random.random", return_value=0.5):  # no overshoot branch
        await interactor._scroll_deliver(300)

    deltas = _wheel_deltas(mock_page)
    assert len(deltas) > 1, "expected accel/cruise/decel notches"
    assert sum(deltas) == 300


@pytest.mark.asyncio
async def test_scroll_deliver_zero_delta_noop(mock_page: MagicMock) -> None:
    """Zero delta emits no wheel events in any mode."""
    for mode in (HumanizeMode.FAST, HumanizeMode.DEFAULT, HumanizeMode.CAREFUL):
        interactor = Interactor(mock_page, {}, humanize=HumanizeConfig.from_mode(mode))
        mock_page.mouse.wheel = AsyncMock()
        await interactor._scroll_deliver(0)
        mock_page.mouse.wheel.assert_not_called()


@pytest.mark.asyncio
async def test_wheel_burst_zero_delta_noop(mock_page: MagicMock) -> None:
    """wheel_burst with a zero delta emits no wheel events."""
    from myrm_agent_harness.toolkits.browser.session.humanize import wheel_burst

    mock_page.mouse.wheel = AsyncMock()
    await wheel_burst(mock_page, 0, HumanizeConfig())
    mock_page.mouse.wheel.assert_not_called()


def test_scroll_burst_break_ms_fast_returns_zero() -> None:
    """FAST mode never pauses between scroll notches."""
    from myrm_agent_harness.toolkits.browser.session.humanize import (
        scroll_burst_break_ms,
    )

    cfg = HumanizeConfig.from_mode(HumanizeMode.FAST)
    assert scroll_burst_break_ms(cfg, in_burst=True, phase_changed=True) == 0


@pytest.mark.asyncio
async def test_scroll_noop_reason_smooth_scroll_settles(mock_page: MagicMock) -> None:
    """Smooth scroll: the container moves after the settle delay, no reason given."""
    interactor = Interactor(mock_page, {})
    state_a = {"top": 0.0, "height": 2000.0, "client": 720.0}
    state_b = {"top": 100.0, "height": 2000.0, "client": 720.0}
    states = iter([state_a, state_b])

    async def mock_evaluate(expr: str, arg: object = None) -> object:
        if "innerHeight" in expr:
            return 800
        if "elementFromPoint" in expr:
            return next(states)
        return 0

    mock_page.evaluate = AsyncMock(side_effect=mock_evaluate)
    mock_page.mouse.wheel = AsyncMock()

    reason = await interactor._scroll_noop_reason(400, 300, state_a, 300)

    assert reason == ""


# =============================================================================
# Scroll cursor target and overshoot (CAREFUL)
# =============================================================================


@pytest.mark.asyncio
async def test_scroll_overshoot_correct_branch(mock_page: MagicMock) -> None:
    """CAREFUL overshoot-and-correct fires when the chance check hits."""
    interactor = careful_interactor(mock_page, {})
    mock_page.mouse.wheel = AsyncMock()

    with patch("random.random", return_value=0.05):  # < scroll_overshoot_chance=0.1
        await interactor._scroll_overshoot_correct(1)

    # overshoot burst + 1-2 correction bursts each emit wheel events
    assert mock_page.mouse.wheel.call_count >= 2


@pytest.mark.asyncio
async def test_scroll_cursor_target_unmeasurable_uses_viewport_center(
    mock_page: MagicMock, refs_map: dict[str, RefInfo]
) -> None:
    """A hidden target makes the wheel cursor fall back to the viewport center."""
    interactor = careful_interactor(mock_page, refs_map)
    locator = AsyncMock()
    locator.bounding_box.return_value = None

    x, y = await interactor._scroll_cursor_target(locator)

    assert (x, y) == (640.0, 360.0)


@pytest.mark.asyncio
async def test_scroll_cursor_target_measure_error_uses_viewport_center(
    mock_page: MagicMock, refs_map: dict[str, RefInfo]
) -> None:
    """A bounding-box error degrades to the viewport center."""
    interactor = careful_interactor(mock_page, refs_map)
    locator = AsyncMock()
    locator.bounding_box.side_effect = Exception("Target closed")

    x, y = await interactor._scroll_cursor_target(locator)

    assert (x, y) == (640.0, 360.0)


# =============================================================================
# _parse_scroll_params
# =============================================================================


def test_parse_scroll_params_defaults() -> None:
    """Empty/None text returns all defaults."""
    result = _parse_scroll_params("")
    assert result["max_steps"] == 15
    assert result["delay_ms"] == 500
    assert result["stable_count"] == 3

    result_none = _parse_scroll_params(None)  # type: ignore[arg-type]
    assert result_none == result


def test_parse_scroll_params_custom_values() -> None:
    """Custom key=value pairs override defaults."""
    result = _parse_scroll_params("max_steps=30,delay_ms=200,stable_count=5")
    assert result["max_steps"] == 30
    assert result["delay_ms"] == 200
    assert result["stable_count"] == 5


def test_parse_scroll_params_partial() -> None:
    """Only specified keys are overridden."""
    result = _parse_scroll_params("delay_ms=100")
    assert result["max_steps"] == 15
    assert result["delay_ms"] == 100
    assert result["stable_count"] == 3


def test_parse_scroll_params_clamping() -> None:
    """Values are clamped to safe ranges."""
    result = _parse_scroll_params("max_steps=9999,delay_ms=10,stable_count=1")
    assert result["max_steps"] == 1000  # CAP
    assert result["delay_ms"] == 100  # min 100
    assert result["stable_count"] == 2  # min 2


def test_parse_scroll_params_invalid_values_ignored() -> None:
    """Non-numeric values and unknown keys are silently ignored."""
    result = _parse_scroll_params("max_steps=abc,unknown_key=42")
    assert result["max_steps"] == 15  # unchanged
    assert result["delay_ms"] == 500
    assert result["stable_count"] == 3


def test_parse_scroll_params_whitespace() -> None:
    """Whitespace around keys and values is trimmed."""
    result = _parse_scroll_params("  max_steps = 25 , delay_ms = 300 ")
    assert result["max_steps"] == 25
    assert result["delay_ms"] == 300


def test_parse_scroll_params_no_equals() -> None:
    """Plain text without = signs is ignored, returns defaults."""
    result = _parse_scroll_params("hello world")
    assert result["max_steps"] == 15
    assert result["delay_ms"] == 500
    assert result["stable_count"] == 3


def test_parse_scroll_params_negative_values() -> None:
    """Negative values are clamped to minimums."""
    result = _parse_scroll_params("max_steps=-5,delay_ms=-100,stable_count=-1")
    assert result["max_steps"] == 1  # min 1
    assert result["delay_ms"] == 100  # min 100
    assert result["stable_count"] == 2  # min 2


def test_parse_scroll_params_zero_max_steps() -> None:
    """max_steps=0 is clamped to 1."""
    result = _parse_scroll_params("max_steps=0")
    assert result["max_steps"] == 1


def test_scroll_measure_js_targets_wheel_scrollable_containers() -> None:
    """The measurement JS only treats real wheel-scrollable boxes as targets.

    Regression canary: a bare scrollHeight check would mis-measure overflow:visible
    boxes (their scrollTop is always 0), causing every wheel scroll over them to be
    falsely reported as stuck/no-op even though the document scrolls. Verified
    against a real browser (overflow:visible box skipped, document measured).
    """
    assert "isScrollable" in _SCROLL_MEASURE_JS
    assert "overflowY" in _SCROLL_MEASURE_JS
    assert "contentDocument" in _SCROLL_MEASURE_JS
    assert "HTMLIFrameElement" in _SCROLL_MEASURE_JS
    assert "elementFromPoint" in _SCROLL_MEASURE_JS


# =============================================================================
# Humanize primitives: bezier mouse movement
# =============================================================================


@pytest.mark.asyncio
async def test_bezier_move_overshoot_correction(mock_page: MagicMock) -> None:
    """bezier_move shoots past the target then corrects back when the chance hits."""
    from myrm_agent_harness.toolkits.browser.session.humanize import bezier_move

    cfg = HumanizeConfig()  # overshoot_chance=0.15 default
    with patch("random.random", return_value=0.05):  # < 0.15 → overshoot branch
        await bezier_move(mock_page, 0, 0, 200, 100, cfg)

    # steps = max(25, min(80, round(hypot(200,100)/8))) = 28 → 29 bezier moves
    # + 1 overshoot + 1 correction return = 31 total
    assert mock_page.mouse.move.call_count == 31
    last_x, last_y = mock_page.mouse.move.call_args_list[-1].args[:2]
    assert abs(last_x - 200) <= 5 and abs(last_y - 100) <= 5  # corrected back


@pytest.mark.asyncio
async def test_bezier_move_no_overshoot_when_chance_misses(mock_page: MagicMock) -> None:
    """bezier_move without the overshoot hit ends exactly on the target."""
    from myrm_agent_harness.toolkits.browser.session.humanize import bezier_move

    cfg = HumanizeConfig()
    with patch("random.random", return_value=0.5):  # >= 0.15 → no overshoot
        await bezier_move(mock_page, 0, 0, 200, 100, cfg)

    assert mock_page.mouse.move.call_count == 29  # pure bezier path
    last_x, last_y = mock_page.mouse.move.call_args_list[-1].args[:2]
    assert last_x == 200 and last_y == 100  # lands exactly on target


@pytest.mark.asyncio
async def test_bezier_move_identical_points_noop(mock_page: MagicMock) -> None:
    """bezier_move with start == end emits no mouse events."""
    from myrm_agent_harness.toolkits.browser.session.humanize import bezier_move

    mock_page.mouse.move = AsyncMock()
    await bezier_move(mock_page, 100, 100, 100, 100, HumanizeConfig())
    mock_page.mouse.move.assert_not_called()


@pytest.mark.asyncio
async def test_bezier_move_to_initializes_mouse_position(mock_page: MagicMock, refs_map: dict[str, RefInfo]) -> None:
    """A first Bézier move seeds the mouse from the viewport center."""
    interactor = careful_interactor(mock_page, refs_map)
    interactor._mouse_x = 0.0
    interactor._mouse_y = 0.0
    locator = AsyncMock()
    locator.bounding_box.return_value = {"x": 400, "y": 300, "width": 100, "height": 60}

    with patch(
        "myrm_agent_harness.toolkits.browser.session.interactor_click_mixin.bezier_move",
        new_callable=AsyncMock,
    ) as mock_bezier:
        assert await interactor._bezier_move_to(locator) is True

    start_x, start_y = mock_bezier.await_args.args[1], mock_bezier.await_args.args[2]
    assert (start_x, start_y) == (640.0, 360.0)  # seeded from the viewport center
