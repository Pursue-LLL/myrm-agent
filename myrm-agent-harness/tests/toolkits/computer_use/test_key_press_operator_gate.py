"""ComputerSession.key_press rejects a lone printable operator before the backend sees it.

The predicate is_operator_as_key_name is covered in test_computer_safety.py; this module covers the session gate built on it.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


class TestKeyPressOperatorGate:
    """ComputerSession.key_press must reject lone operators before backend.key."""

    @pytest.mark.asyncio
    async def test_key_press_rejects_star_without_backend(self) -> None:
        from myrm_agent_harness.toolkits.computer_use.session import ComputerSession
        from myrm_agent_harness.toolkits.computer_use.types import ComputerUseConfig

        backend = MagicMock()
        backend.key = AsyncMock()
        session = ComputerSession(backend=backend, config=ComputerUseConfig())
        result = await session.key_press("*")
        assert result.success is False
        assert result.error is not None
        assert "Rejected printable operator" in result.error
        backend.key.assert_not_called()

    @pytest.mark.asyncio
    async def test_key_press_allows_modifier_combo(self) -> None:
        from myrm_agent_harness.toolkits.computer_use.session import ComputerSession
        from myrm_agent_harness.toolkits.computer_use.types import (
            ActionResult,
            ComputerUseConfig,
        )

        backend = MagicMock()
        backend.key = AsyncMock(return_value=ActionResult(success=True))
        session = ComputerSession(backend=backend, config=ComputerUseConfig())
        session.take_screenshot = AsyncMock(
            return_value=ActionResult(success=True, screenshot_base64="x", screenshot_size=(1, 1))
        )
        result = await session.key_press("ctrl+/")
        assert result.success is True
        backend.key.assert_called_once_with("ctrl+/")
