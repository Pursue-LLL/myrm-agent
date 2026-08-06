"""Unit tests for extension wiki clip agent UserConfig SSOT."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.extension.clip_agent_config import (
    ExtensionClipAgentConfig,
    get_extension_clip_agent_config,
    set_extension_clip_agent_config,
)


class TestClipAgentConfigService:
    @pytest.mark.asyncio
    async def test_get_returns_empty_when_missing(self) -> None:
        mock_service = MagicMock()
        mock_service.get = AsyncMock(return_value=None)

        with patch(
            "app.services.extension.clip_agent_config.ConfigService",
            return_value=mock_service,
        ):
            cfg = await get_extension_clip_agent_config()

        assert cfg == ExtensionClipAgentConfig()

    @pytest.mark.asyncio
    async def test_get_parses_stored_payload(self) -> None:
        mock_service = MagicMock()
        mock_service.get = AsyncMock(
            return_value=MagicMock(
                value={
                    "agent_id": " agent-42 ",
                    "web_ui_origin": "http://localhost:3000/",
                }
            )
        )

        with patch(
            "app.services.extension.clip_agent_config.ConfigService",
            return_value=mock_service,
        ):
            cfg = await get_extension_clip_agent_config()

        assert cfg.agent_id == "agent-42"
        assert cfg.web_ui_origin == "http://localhost:3000"

    @pytest.mark.asyncio
    async def test_set_normalizes_and_persists(self) -> None:
        mock_service = MagicMock()
        mock_service.set = AsyncMock()

        with patch(
            "app.services.extension.clip_agent_config.ConfigService",
            return_value=mock_service,
        ):
            cfg = await set_extension_clip_agent_config(
                agent_id="  writer ",
                web_ui_origin="https://app.example.com/",
            )

        assert cfg.agent_id == "writer"
        assert cfg.web_ui_origin == "https://app.example.com"
        mock_service.set.assert_awaited_once_with(
            "extensionClipAgent",
            {"agent_id": "writer", "web_ui_origin": "https://app.example.com"},
        )
