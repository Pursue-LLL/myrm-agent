"""Autouse mock of the artifact upsert, shared by the artifact processor and artifact API tests.

Registered globally through ``pytest_plugins`` in ``tests/conftest.py``; it is inert for tests that never reach the
artifact pipeline. A plugin module, not a conftest: a conftest that is also a plugin is registered twice, and pytest
then aborts any run that targets its directory.
"""

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
