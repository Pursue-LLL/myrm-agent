"""Tests for x-live-search skill auto-enable on xAI provider save."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.skills.oauth_availability import X_LIVE_SEARCH_SKILL_ID
from app.core.skills.x_live_search_skill_enable import maybe_enable_x_live_search_skill


@pytest.mark.asyncio
async def test_maybe_enable_skips_without_xai_provider() -> None:
    enabled, disabled = await maybe_enable_x_live_search_skill({"providers": []})
    assert enabled is False
    assert disabled is False


@pytest.mark.asyncio
async def test_maybe_enable_respects_user_disabled() -> None:
    providers = {"providers": [{"id": "xai", "apiKey": "key", "apiUrl": "https://api.x.ai/v1"}]}
    mock_config = MagicMock()
    mock_config.disabled_prebuilt_ids = [X_LIVE_SEARCH_SKILL_ID]
    mock_config.enabled_prebuilt_ids = []

    mock_user_config = MagicMock()
    mock_user_config.get_config = AsyncMock(return_value=mock_config)

    mock_service = MagicMock()
    mock_service.user_config = mock_user_config

    with patch("app.core.skills.store.service.skills_service", mock_service):
        enabled, disabled = await maybe_enable_x_live_search_skill(providers)

    assert enabled is False
    assert disabled is True


@pytest.mark.asyncio
async def test_maybe_enable_enables_skill_when_xai_present() -> None:
    providers = {"providers": [{"id": "xai", "apiKey": "key", "apiUrl": "https://api.x.ai/v1"}]}
    mock_config = MagicMock()
    mock_config.disabled_prebuilt_ids = []
    mock_config.enabled_prebuilt_ids = []

    mock_user_config = MagicMock()
    mock_user_config.get_config = AsyncMock(return_value=mock_config)
    mock_user_config.enable_prebuilt_skill = AsyncMock()

    mock_service = MagicMock()
    mock_service.user_config = mock_user_config

    with patch("app.core.skills.store.service.skills_service", mock_service):
        enabled, disabled = await maybe_enable_x_live_search_skill(providers)

    assert enabled is True
    assert disabled is False
    mock_user_config.enable_prebuilt_skill.assert_awaited_once_with(X_LIVE_SEARCH_SKILL_ID)
