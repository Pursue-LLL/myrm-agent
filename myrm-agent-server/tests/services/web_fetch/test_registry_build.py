"""Extended registry tests for build_escalation_providers and env deny."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.config import WebFetchEscalationConfigValue, WebFetchFirecrawlConfig
from app.services.web_fetch.escalation.registry import (
    build_escalation_providers,
    load_web_fetch_escalation_config,
    resolve_firecrawl_api_key,
)


@pytest.mark.asyncio
async def test_load_web_fetch_escalation_config_denied_by_env() -> None:
    with patch.dict(os.environ, {"MYRM_WEB_FETCH_ESCALATION": "denied"}):
        assert await load_web_fetch_escalation_config() is None


@pytest.mark.asyncio
async def test_load_web_fetch_escalation_config_disabled() -> None:
    mock_record = MagicMock()
    mock_record.value = {"enabled": False}
    with patch.dict(os.environ, {"MYRM_WEB_FETCH_ESCALATION": ""}, clear=False):
        with patch("app.services.config.service.config_service.get", new=AsyncMock(return_value=mock_record)):
            cfg = await load_web_fetch_escalation_config()
    assert cfg is None


@pytest.mark.asyncio
async def test_build_escalation_providers_builds_jina_and_firecrawl() -> None:
    cfg = WebFetchEscalationConfigValue(enabled=True, jina_api_key=None, session_cap=3)
    cfg.firecrawl.api_key = "fc-direct"

    search_record = MagicMock()
    search_record.value = {"searchServiceConfigs": []}

    with patch(
        "app.services.web_fetch.escalation.registry.load_web_fetch_escalation_config",
        new=AsyncMock(return_value=cfg),
    ):
        with patch("app.services.config.service.config_service.get", new=AsyncMock(return_value=search_record)):
            providers = await build_escalation_providers("chat-99")

    assert providers is not None
    assert len(providers) == 2
    assert providers[0].provider_id == "jina"
    assert providers[1].provider_id == "firecrawl"


def test_resolve_firecrawl_api_key_no_inherit_returns_none() -> None:
    cfg = WebFetchEscalationConfigValue(
        enabled=True,
        firecrawl=WebFetchFirecrawlConfig(inherit_from_search=False, api_key=None),
    )
    assert resolve_firecrawl_api_key(cfg, None) is None


@pytest.mark.asyncio
async def test_load_web_fetch_escalation_config_load_error() -> None:
    with patch.dict(os.environ, {"MYRM_WEB_FETCH_ESCALATION": ""}, clear=False):
        with patch(
            "app.services.config.service.config_service.get",
            new=AsyncMock(side_effect=RuntimeError("db down")),
        ):
            assert await load_web_fetch_escalation_config() is None


@pytest.mark.asyncio
async def test_build_escalation_providers_jina_only_without_firecrawl_key() -> None:
    cfg = WebFetchEscalationConfigValue(enabled=True, session_cap=2)

    with patch(
        "app.services.web_fetch.escalation.registry.load_web_fetch_escalation_config",
        new=AsyncMock(return_value=cfg),
    ):
        with patch("app.services.config.service.config_service.get", new=AsyncMock(return_value=None)):
            providers = await build_escalation_providers("chat-1")

    assert providers is not None
    assert len(providers) == 1
    assert providers[0].provider_id == "jina"
