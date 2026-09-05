"""Local conftest for stream_session unit tests.

[INPUT]
- None (pure unit test fixtures)

[OUTPUT]
- Light-weight overrides for global autouse fixtures (bypasses DB init, qdrant, and model loading)

[POS]
Isolates pure-logic stream_session tests from full-stack server integration fixtures.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest


@pytest.fixture(scope="session", autouse=True)
def init_test_database() -> Iterator[None]:
    """Bypass full SQLite schema migration for pure stream_session unit tests."""
    yield


@pytest.fixture(autouse=True)
def mock_load_user_configs() -> Iterator[None]:
    """Bypass loading user configs and secrets for pure stream_session unit tests."""
    yield


@pytest.fixture(autouse=True)
def _reset_agent_test_singletons() -> Iterator[None]:
    """Bypass qdrant memory cache eviction for pure stream_session unit tests."""
    yield


@pytest.fixture(autouse=True)
def _mock_upsert_processor_artifact() -> Iterator[None]:
    """Bypass artifact listener patch for pure stream_session unit tests."""
    yield
