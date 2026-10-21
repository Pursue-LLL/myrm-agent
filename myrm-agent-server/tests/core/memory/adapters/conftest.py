"""Local conftest for the memory-adapter unit tests.

[INPUT]
- tests.api.agent.conftest::_build_mock_user_configs (POS: canned user-config factory)

[OUTPUT]
- configured_user_configs: autouse fixture serving canned user configs to this suite

[POS]
``create_memory_manager`` resolves the platform dedup LLM through ``load_user_configs``; without a
canned config these unit tests read the workspace's empty database and fail before the adapter runs.
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest

from tests.api.agent.conftest import _build_mock_user_configs


@pytest.fixture(autouse=True)
def configured_user_configs() -> Iterator[None]:
    with patch(
        "app.core.channel_bridge.config_loader.load_user_configs",
        new=AsyncMock(return_value=_build_mock_user_configs()),
    ):
        yield
