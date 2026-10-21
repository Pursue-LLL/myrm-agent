"""Shared fixtures for the memory backup tests."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from myrm_agent_harness.toolkits.vector.qdrant.factory import clear_embedded_stores


@pytest.fixture(autouse=True)
async def _reset_embedded_stores() -> AsyncIterator[None]:
    """Release the embedded Qdrant singletons that real managers create between cases."""
    await clear_embedded_stores()
    yield
    await clear_embedded_stores()
