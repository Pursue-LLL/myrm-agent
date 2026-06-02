"""Tests for MCPSecretAuthProvider."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.services.agent.backends.mcp_secret_auth import (
    _SECRET_REF_PATTERN,
    MCPSecretAuthProvider,
)


@pytest.fixture
def mock_secret_store() -> AsyncMock:
    store = AsyncMock()
    store.get_secret = AsyncMock(return_value=None)
    return store


def _make_provider(
    templates: dict[str, str],
    store: AsyncMock,
    agent_id: str = "agent-1",
) -> MCPSecretAuthProvider:
    return MCPSecretAuthProvider(
        header_templates=templates,
        secret_store=store,
        agent_id=agent_id,
    )


class TestSecretRefPattern:
    def test_simple_match(self) -> None:
        assert _SECRET_REF_PATTERN.findall("{{secret:MY_KEY}}") == ["MY_KEY"]

    def test_bearer_prefix(self) -> None:
        assert _SECRET_REF_PATTERN.findall("Bearer {{secret:TOKEN}}") == ["TOKEN"]

    def test_multiple_refs(self) -> None:
        refs = _SECRET_REF_PATTERN.findall("{{secret:A}} and {{secret:B}}")
        assert refs == ["A", "B"]

    def test_no_match(self) -> None:
        assert _SECRET_REF_PATTERN.findall("plain-value") == []


class TestGetAuthHeaders:
    @pytest.mark.asyncio
    async def test_empty_templates(self, mock_secret_store: AsyncMock) -> None:
        provider = _make_provider({}, mock_secret_store)
        result = await provider.get_auth_headers("srv", "http://example.com")
        assert result == {}

    @pytest.mark.asyncio
    async def test_plain_header_passthrough(self, mock_secret_store: AsyncMock) -> None:
        provider = _make_provider(
            {"X-Custom": "static-value"}, mock_secret_store
        )
        result = await provider.get_auth_headers("srv", "http://example.com")
        assert result == {"X-Custom": "static-value"}
        mock_secret_store.get_secret.assert_not_called()

    @pytest.mark.asyncio
    async def test_secret_resolved(self, mock_secret_store: AsyncMock) -> None:
        mock_secret_store.get_secret.return_value = "sk-live-abc123"
        provider = _make_provider(
            {"Authorization": "Bearer {{secret:OPENAI_KEY}}"},
            mock_secret_store,
            agent_id="agent-42",
        )
        result = await provider.get_auth_headers("my-mcp", "http://mcp.local")
        assert result == {"Authorization": "Bearer sk-live-abc123"}
        mock_secret_store.get_secret.assert_awaited_once_with("agent-42", "OPENAI_KEY")

    @pytest.mark.asyncio
    async def test_missing_secret_keeps_placeholder(
        self, mock_secret_store: AsyncMock
    ) -> None:
        mock_secret_store.get_secret.return_value = None
        provider = _make_provider(
            {"Authorization": "Bearer {{secret:MISSING}}"},
            mock_secret_store,
        )
        result = await provider.get_auth_headers("srv", "http://example.com")
        assert result == {"Authorization": "Bearer {{secret:MISSING}}"}

    @pytest.mark.asyncio
    async def test_multiple_secrets_in_one_value(
        self, mock_secret_store: AsyncMock
    ) -> None:
        async def side_effect(agent_id: str, key: str) -> str | None:
            return {"USER": "admin", "PASS": "s3cret"}.get(key)

        mock_secret_store.get_secret.side_effect = side_effect
        provider = _make_provider(
            {"X-Auth": "{{secret:USER}}:{{secret:PASS}}"},
            mock_secret_store,
        )
        result = await provider.get_auth_headers("srv", "http://example.com")
        assert result == {"X-Auth": "admin:s3cret"}

    @pytest.mark.asyncio
    async def test_mixed_plain_and_secret_headers(
        self, mock_secret_store: AsyncMock
    ) -> None:
        mock_secret_store.get_secret.return_value = "token-xyz"
        provider = _make_provider(
            {
                "Content-Type": "application/json",
                "Authorization": "Bearer {{secret:API_TOKEN}}",
            },
            mock_secret_store,
        )
        result = await provider.get_auth_headers("srv", "http://example.com")
        assert result == {
            "Content-Type": "application/json",
            "Authorization": "Bearer token-xyz",
        }
