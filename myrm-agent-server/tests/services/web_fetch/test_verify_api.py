"""Tests for web fetch escalation verify API handler."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.integrations.web_fetch import verify_web_fetch_escalation, WebFetchEscalationVerifyRequest
from myrm_agent_harness.toolkits.web_fetch.escalation.protocols import EscalationFetchResult


@pytest.mark.asyncio
async def test_verify_jina_success() -> None:
    mock_result = EscalationFetchResult(
        url="https://example.com",
        content="hello world",
        title="Example",
        provider_id="jina",
    )
    request = WebFetchEscalationVerifyRequest(provider="jina", api_key=None)
    with patch(
        "app.api.integrations.web_fetch.JinaEscalationProvider.fetch_url",
        new=AsyncMock(return_value=mock_result),
    ):
        response = await verify_web_fetch_escalation(request)

    body = response.body.decode()
    assert "hello world" in body or "content_length" in body


@pytest.mark.asyncio
async def test_verify_firecrawl_inherit_resolves_key() -> None:
    request = WebFetchEscalationVerifyRequest(provider="firecrawl", inherit_from_search=True)
    with patch(
        "app.api.integrations.web_fetch._resolve_firecrawl_verify_key",
        new=AsyncMock(return_value="resolved-fc-key"),
    ):
        with patch(
            "app.api.integrations.web_fetch.FirecrawlEscalationProvider.fetch_url",
            new=AsyncMock(
                return_value=EscalationFetchResult(
                    url="https://example.com",
                    content="fc body",
                    provider_id="firecrawl",
                )
            ),
        ):
            response = await verify_web_fetch_escalation(request)

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_verify_empty_content_raises() -> None:
    request = WebFetchEscalationVerifyRequest(provider="jina")
    with patch(
        "app.api.integrations.web_fetch.JinaEscalationProvider.fetch_url",
        new=AsyncMock(return_value=None),
    ):
        with pytest.raises(HTTPException):
            await verify_web_fetch_escalation(request)


@pytest.mark.asyncio
async def test_resolve_firecrawl_verify_key_from_search_services() -> None:
    from app.api.integrations.web_fetch import _resolve_firecrawl_verify_key

    escalation_record = MagicMock()
    escalation_record.value = {"enabled": True, "firecrawl": {"inheritFromSearch": True}}
    search_record = MagicMock()
    search_record.value = {
        "searchServiceConfigs": [
            {
                "id": "1",
                "enabled": True,
                "role": "primary",
                "search_service": "firecrawl",
                "api_key": "from-search",
                "createdAt": 1,
            }
        ]
    }

    with patch("app.services.config.service.config_service.get", new=AsyncMock(side_effect=[escalation_record, search_record])):
        key = await _resolve_firecrawl_verify_key(None, True)

    assert key == "from-search"


@pytest.mark.asyncio
async def test_resolve_firecrawl_verify_key_missing_raises() -> None:
    from app.api.integrations.web_fetch import _resolve_firecrawl_verify_key

    with pytest.raises(HTTPException):
        await _resolve_firecrawl_verify_key(None, False)
