"""Interaction humanization configuration.

[INPUT]
- dataclasses::dataclass (POS: Python dataclass)
- enum::StrEnum (POS: Python string enum)

[OUTPUT]
- HumanizeMode: humanization level enum (fast/default/careful)
- HumanizeConfig: interaction humanization config (click/type delay distribution, bezier mouse, wheel-burst scroll)

[POS]
Humanization parameters of the interaction layer. `HumanizeConfig.from_mode` provides three levels: FAST (no-op),
DEFAULT (Gaussian delays), CAREFUL (Gaussian + Bézier mouse + accel/cruise/decel scroll rhythm). Which level a
`BrowserMode` selects is decided in `config.py`, so this module stays free of the pool's mode types.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class HumanizeMode(StrEnum):
    """Interaction humanization level.

    - FAST: no humanization — raw Playwright delays (for local/testing)
    - DEFAULT: Gaussian delay distribution (more natural than uniform)
    - CAREFUL: Gaussian delays + Bézier mouse trajectory (anti-detection, for cloud sandbox)
    """

    FAST = "fast"
    DEFAULT = "default"
    CAREFUL = "careful"


@dataclass(frozen=True)
class HumanizeConfig:
    """Interaction humanization parameters.

    Controls click/type delay distributions, optional Bézier mouse movement, and
    wheel-burst scroll humanization. Three presets via ``from_mode()``: FAST
    (single wheel event per scroll, no bursts), DEFAULT (Gaussian delays + wheel
    bursts), CAREFUL (Gaussian + Bézier trajectory + accel/cruise/decel scroll
    rhythm + overshoot correction for reCAPTCHA v3 stealth).
    """

    mode: HumanizeMode = HumanizeMode.FAST

    click_delay_min: int = 50
    click_delay_max: int = 150
    click_delay_mean: float = 100.0
    click_delay_sigma: float = 25.0

    type_delay_min: int = 30
    type_delay_max: int = 100
    type_delay_mean: float = 65.0
    type_delay_sigma: float = 20.0

    enable_bezier_mouse: bool = False
    bezier_min_steps: int = 25
    bezier_max_steps: int = 80
    bezier_wobble_max: float = 1.5
    overshoot_chance: float = 0.15
    overshoot_px_min: float = 3.0
    overshoot_px_max: float = 6.0

    # Wheel-burst scroll humanization (FAST sends a single wheel event; DEFAULT/CAREFUL burst).
    scroll_step_min: int = 20
    scroll_step_max: int = 40
    scroll_gap_min: int = 8
    scroll_gap_max: int = 20
    scroll_delta_base: tuple[int, int] = (80, 130)
    scroll_delta_variance: float = 0.2
    scroll_accel_delta: tuple[int, int] = (80, 100)
    scroll_decel_delta: tuple[int, int] = (60, 90)
    scroll_pause_fast: tuple[int, int] = (30, 80)
    scroll_pause_slow: tuple[int, int] = (80, 200)
    scroll_accel_steps: tuple[int, int] = (2, 3)
    scroll_decel_steps: tuple[int, int] = (2, 3)
    scroll_overshoot_chance: float = 0.1
    scroll_overshoot_px: tuple[int, int] = (50, 150)
    scroll_settle_delay: tuple[int, int] = (300, 600)
    scroll_pre_move_delay: tuple[int, int] = (100, 300)
    scroll_reading_pause_chance: float = 0.15
    # A ref target must sit inside this viewport band (fractions of viewport
    # height) before a CAREFUL interaction proceeds; otherwise the target is
    # humanized-wheel scrolled into the band first, replacing Playwright's
    # implicit one-shot scrollIntoViewIfNeeded (instant JS jump).
    scroll_target_zone: tuple[float, float] = (0.3, 0.7)

    def __post_init__(self) -> None:
        if self.click_delay_min > self.click_delay_max:
            msg = f"click_delay_min ({self.click_delay_min}) > click_delay_max ({self.click_delay_max})"
            raise ValueError(msg)
        if self.type_delay_min > self.type_delay_max:
            msg = f"type_delay_min ({self.type_delay_min}) > type_delay_max ({self.type_delay_max})"
            raise ValueError(msg)
        if self.click_delay_sigma < 0 or self.type_delay_sigma < 0:
            msg = "sigma values must be non-negative"
            raise ValueError(msg)
        if self.bezier_min_steps > self.bezier_max_steps:
            msg = f"bezier_min_steps ({self.bezier_min_steps}) > bezier_max_steps ({self.bezier_max_steps})"
            raise ValueError(msg)
        if self.scroll_step_min > self.scroll_step_max:
            msg = f"scroll_step_min ({self.scroll_step_min}) > scroll_step_max ({self.scroll_step_max})"
            raise ValueError(msg)
        if self.scroll_gap_min > self.scroll_gap_max:
            msg = f"scroll_gap_min ({self.scroll_gap_min}) > scroll_gap_max ({self.scroll_gap_max})"
            raise ValueError(msg)
        if not 0.0 <= self.scroll_delta_variance <= 1.0:
            msg = f"scroll_delta_variance must be in [0, 1], got {self.scroll_delta_variance}"
            raise ValueError(msg)
        if not 0.0 <= self.scroll_overshoot_chance <= 1.0:
            msg = f"scroll_overshoot_chance must be in [0, 1], got {self.scroll_overshoot_chance}"
            raise ValueError(msg)
        if not 0.0 <= self.scroll_reading_pause_chance <= 1.0:
            msg = f"scroll_reading_pause_chance must be in [0, 1], got {self.scroll_reading_pause_chance}"
            raise ValueError(msg)
        zone_lo, zone_hi = self.scroll_target_zone
        if not 0.0 <= zone_lo < zone_hi <= 1.0:
            msg = f"scroll_target_zone ({zone_lo}, {zone_hi}) is invalid: require 0.0 <= lo < hi <= 1.0"
            raise ValueError(msg)
        for name in (
            "scroll_delta_base",
            "scroll_accel_delta",
            "scroll_decel_delta",
            "scroll_pause_fast",
            "scroll_pause_slow",
            "scroll_accel_steps",
            "scroll_decel_steps",
            "scroll_overshoot_px",
            "scroll_settle_delay",
            "scroll_pre_move_delay",
        ):
            lo, hi = getattr(self, name)
            if lo > hi:
                msg = f"{name} range ({lo}, {hi}) is invalid: min > max"
                raise ValueError(msg)

    @classmethod
    def from_mode(cls, mode: HumanizeMode) -> HumanizeConfig:
        """Create preset config for the given humanization level."""
        if mode == HumanizeMode.FAST:
            return cls(mode=HumanizeMode.FAST)
        elif mode == HumanizeMode.DEFAULT:
            return cls(mode=HumanizeMode.DEFAULT)
        else:
            return cls(
                mode=HumanizeMode.CAREFUL,
                click_delay_mean=120.0,
                click_delay_sigma=30.0,
                type_delay_mean=80.0,
                type_delay_sigma=25.0,
                enable_bezier_mouse=True,
                scroll_pause_fast=(100, 200),
                scroll_pause_slow=(250, 600),
                scroll_settle_delay=(400, 800),
                scroll_pre_move_delay=(150, 400),
            )
