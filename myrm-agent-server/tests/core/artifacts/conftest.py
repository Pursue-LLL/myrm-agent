"""Shared fixtures for artifact processor tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture(autouse=True)
def _mock_upsert_processor_artifact() -> AsyncMock:
    import app.core.artifacts.listener  # noqa: F401 - Ensure submodule is loaded before patch

    with patch(
        "app.core.artifacts.listener.upsert_processor_artifact",
        new_callable=AsyncMock,
        return_value="test-version-id",
    ) as mock_upsert:
        yield mock_upsert
