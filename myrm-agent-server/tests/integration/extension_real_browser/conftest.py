"""Fixture shared by the real-browser extension e2e tests.

[INPUT]
- tests.support.extension_real_browser::real_extension_stack (POS: the connected extension, bridge and fixture site)

[OUTPUT]
- stack: a fresh browser profile with the extension connected to the production bridge, torn down after each test

[POS]
Every test in this directory starts from the same state a user reaches after pressing Connect in the popup.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from tests.support.extension_real_browser import RealExtensionStack, real_extension_stack


@pytest.fixture
async def stack(tmp_path: Path) -> AsyncIterator[RealExtensionStack]:
    async with real_extension_stack(tmp_path / "profile") as running:
        yield running
