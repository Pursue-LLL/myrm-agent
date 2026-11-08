"""Shared fixtures for web_search tests."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from myrm_agent_harness.toolkits.web_search.coalescing.search_coalescing import (
    reset_search_coalescing_state_for_tests,
)


@pytest.fixture(autouse=True)
def _clear_search_coalescing_state() -> Iterator[None]:
    """The search result cache and the in-flight registry are process-wide, so every test starts and ends with them empty."""
    reset_search_coalescing_state_for_tests()
    yield
    reset_search_coalescing_state_for_tests()
