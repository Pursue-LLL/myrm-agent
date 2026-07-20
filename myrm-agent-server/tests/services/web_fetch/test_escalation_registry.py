"""Tests for web fetch escalation registry and session cap."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

import pytest

from app.schemas.config import (
    SearchServiceConfigItem,
    SearchServicesConfigValue,
    WebFetchEscalationConfigValue,
    WebFetchFirecrawlConfig,
)
from app.services.web_fetch.escalation.registry import (
    build_escalation_providers,
    is_web_fetch_escalation_denied,
    resolve_firecrawl_api_key,
)


def test_is_web_fetch_escalation_denied() -> None:
    with patch.dict(os.environ, {"MYRM_WEB_FETCH_ESCALATION": "denied"}):
        assert is_web_fetch_escalation_denied() is True
    with patch.dict(os.environ, {"MYRM_WEB_FETCH_ESCALATION": ""}, clear=False):
        assert is_web_fetch_escalation_denied() is False


def test_resolve_firecrawl_api_key_inherits_from_search() -> None:
    cfg = WebFetchEscalationConfigValue(enabled=True)
    search = SearchServicesConfigValue(
        searchServiceConfigs=[
            SearchServiceConfigItem(
                id="fc1",
                enabled=True,
                role="primary",
                search_service="firecrawl",
                api_key="fc-test-key",
                createdAt=1,
            )
        ]
    )
    assert resolve_firecrawl_api_key(cfg, search) == "fc-test-key"


def test_resolve_firecrawl_api_key_prefers_explicit() -> None:
    cfg = WebFetchEscalationConfigValue(
        enabled=True,
        firecrawl=WebFetchFirecrawlConfig(inherit_from_search=True, api_key="explicit-key"),
    )
    assert resolve_firecrawl_api_key(cfg, None) == "explicit-key"


@pytest.mark.asyncio
async def test_build_escalation_providers_returns_none_when_disabled() -> None:
    with patch(
        "app.services.web_fetch.escalation.registry.load_web_fetch_escalation_config",
        new=AsyncMock(return_value=None),
    ):
        assert await build_escalation_providers("session-1") is None


@pytest.mark.asyncio
async def test_session_cap_blocks_after_limit() -> None:
    from myrm_agent_harness.toolkits.web_fetch.escalation.protocols import EscalationFetchResult

    from app.services.web_fetch.escalation.registry import SessionCappedEscalationProvider
    from app.services.web_fetch.escalation.session_counter import session_escalation_counter

    class _Inner:
        provider_id = "inner"

        async def fetch_url(self, url: str, *, max_chars: int = 0) -> EscalationFetchResult:
            return EscalationFetchResult(url=url, content="ok", provider_id="inner")

    session_id = "cap-test-session"
    session_escalation_counter.reset_session(session_id)
    capped = SessionCappedEscalationProvider(_Inner(), session_id=session_id, session_cap=1)

    first = await capped.fetch_url("https://example.com")
    second = await capped.fetch_url("https://example.com")

    assert first is not None
    assert second is None
