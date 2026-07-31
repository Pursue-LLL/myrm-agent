"""Wiki asset caption provider uses ordered vision fallback chain."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_build_wiki_asset_caption_provider_uses_engine_chain() -> None:
    mock_engine = MagicMock()
    mock_engine.fallback_configs = [MagicMock(model="openai/gpt-4o-mini")]

    with (
        patch(
            "app.core.channel_bridge.config_loader._load_single_config",
            new_callable=AsyncMock,
            return_value={"defaultModelConfig": {"visionFallbackModel": {"providerId": "openai", "model": "gpt-4o-mini"}}},
        ),
        patch(
            "app.core.channel_bridge.config_parsers.build_vision_fallback_engine_from_providers",
            return_value=mock_engine,
        ) as mock_build,
    ):
        from app.services.wiki.asset_index_service import build_wiki_asset_caption_provider

        provider = await build_wiki_asset_caption_provider()

    assert provider is not None
    mock_build.assert_called_once()
