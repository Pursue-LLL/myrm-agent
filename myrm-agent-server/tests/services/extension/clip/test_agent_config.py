"""Tests for extension clip agent UserConfig persistence."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.extension.clip import (
    ExtensionClipAgentConfig,
    set_extension_clip_agent_config,
)


@pytest.mark.asyncio
async def test_set_clip_agent_config_passes_device_id_to_config_service() -> None:
    service = MagicMock()
    service.set = AsyncMock(
        return_value=MagicMock(
            value={"agent_id": "agent-1", "web_ui_origin": "http://127.0.0.1:3000"}
        )
    )

    with patch(
        "app.services.extension.clip.agent_config.ConfigService",
        return_value=service,
    ):
        result = await set_extension_clip_agent_config(
            agent_id="agent-1",
            web_ui_origin="http://127.0.0.1:3000/",
        )

    assert result == ExtensionClipAgentConfig(
        agent_id="agent-1",
        web_ui_origin="http://127.0.0.1:3000",
    )
    service.set.assert_awaited_once_with(
        "extensionClipAgent",
        {"agent_id": "agent-1", "web_ui_origin": "http://127.0.0.1:3000"},
        "webui",
    )
