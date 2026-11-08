"""Fixtures for the Interactor unit tests.

The instant-sleep patch is scoped to this directory so the real-browser tests next door keep real timing.
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.browser.session.interactor import Interactor
from myrm_agent_harness.toolkits.browser.snapshot import RefInfo


@pytest.fixture
def ref_info() -> RefInfo:
    """Sample RefInfo."""
    return RefInfo(
        role="button",
        name="Click Me",
        nth=None,
        bbox={"x": 100, "y": 50, "width": 80, "height": 30},
        position="center-center",
    )


@pytest.fixture
def refs_map(ref_info: RefInfo) -> dict[str, RefInfo]:
    """Sample refs mapping."""
    return {"e0": ref_info}


@pytest.fixture
def mock_page() -> MagicMock:
    """Mock Playwright Page."""
    page = MagicMock()
    page.evaluate = AsyncMock()
    page.locator = MagicMock()
    page.viewport_size = {"width": 1280, "height": 720}
    page.mouse = MagicMock()
    page.mouse.move = AsyncMock()
    page.mouse.wheel = AsyncMock()
    return page


@pytest.fixture
def interactor(mock_page: MagicMock, refs_map: dict[str, RefInfo]) -> Interactor:
    """Create Interactor with mocked page and refs."""
    return Interactor(mock_page, refs_map)


@pytest.fixture(autouse=True)
def _instant_sleep() -> Iterator[None]:
    """Make every unit test instant — no real asyncio.sleep waits."""
    with patch("asyncio.sleep", new=AsyncMock()):
        yield
