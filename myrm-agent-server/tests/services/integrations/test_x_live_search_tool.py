"""Tests for x_live_search deferred tool credential resolution."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.agent.security import EphemeralUserCredential, user_credentials_ctx

from app.services.agent.session_credential_assembler import XAI_ISSUER
from app.services.integrations.tools.x_live_search import create_x_live_search_tool


@pytest.mark.asyncio
async def test_x_live_search_tool_returns_error_without_session_credentials() -> None:
    tool = create_x_live_search_tool()
    token = user_credentials_ctx.set(())
    try:
        result = await tool.ainvoke({"query": "latest AI news"})
    finally:
        user_credentials_ctx.reset(token)

    assert result["metadata"]["error"] is True


@pytest.mark.asyncio
async def test_x_live_search_tool_uses_xai_credentials_from_context() -> None:
    tool = create_x_live_search_tool()
    cred = EphemeralUserCredential(
        issuer=XAI_ISSUER,
        token="test-key",
        scope="https://api.x.ai/v1",
    )
    token = user_credentials_ctx.set((cred,))
    try:
        with patch(
            "app.services.integrations.tools.x_live_search.XSearchProvider.search",
            new_callable=AsyncMock,
        ) as mock_search:
            from myrm_agent_harness.toolkits.web_search.common import SearchResult

            mock_search.return_value = SearchResult(
                title="ok",
                link="https://x.com",
                snippet="result text",
            )
            result = await tool.ainvoke({"query": "hello"})
    finally:
        user_credentials_ctx.reset(token)

    assert result["metadata"].get("error") is not True
    assert "result text" in str(result["content"])
