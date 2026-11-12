"""The area an interaction may point at: the emulated viewport, else what the page measures, else a safe default."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.toolkits.browser.session.viewport import page_viewport_size


def _page(*, emulated: dict[str, int] | None = None, measured: object = None, fails: bool = False) -> MagicMock:
    page = MagicMock()
    page.viewport_size = emulated
    page.evaluate = AsyncMock(side_effect=RuntimeError("page is gone") if fails else None, return_value=measured)
    return page


async def test_an_emulated_viewport_is_used_without_asking_the_page() -> None:
    page = _page(emulated={"width": 390, "height": 844})

    assert await page_viewport_size(page) == (390, 844)
    page.evaluate.assert_not_awaited()


async def test_a_context_without_emulation_shows_the_area_the_page_measures() -> None:
    page = _page(measured=[1440.0, 812])

    assert await page_viewport_size(page) == (1440, 812)


@pytest.mark.parametrize("measured", [None, "1440x812", [1440], [0, 812], [1440, -1], ["1440", "812"]])
async def test_a_measurement_that_is_not_a_size_falls_back_to_the_default(measured: object) -> None:
    assert await page_viewport_size(_page(measured=measured)) == (1280, 720)


async def test_a_page_that_cannot_be_measured_falls_back_to_the_default() -> None:
    assert await page_viewport_size(_page(fails=True)) == (1280, 720)
