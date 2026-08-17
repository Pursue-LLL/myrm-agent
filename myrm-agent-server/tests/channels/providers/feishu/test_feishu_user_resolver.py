"""Unit tests for Feishu user resolver."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.providers.feishu.user_resolver import FeishuUserResolver


@pytest.fixture
def mock_feishu_client():
    """Mock FeishuClient for testing."""
    client = MagicMock()
    client.get_user = AsyncMock()
    return client


@pytest.fixture
def resolver(mock_feishu_client):
    """FeishuUserResolver with mocked API client."""
    return FeishuUserResolver(mock_feishu_client, cache_ttl=60, cache_max_size=100)


class TestFeishuUserResolver:
    @pytest.mark.asyncio
    async def test_resolve_user_cache_hit(self, resolver, mock_feishu_client):
        """Test resolve_user with cache hit."""
        await resolver._cache.set("ou_abc", "Alice")

        result = await resolver.resolve_user("ou_abc")

        assert result == "Alice"
        mock_feishu_client.get_user.assert_not_called()

    @pytest.mark.asyncio
    async def test_resolve_user_api_call(self, resolver, mock_feishu_client):
        """Test resolve_user with API call."""
        mock_feishu_client.get_user.return_value = {"name": "Alice", "en_name": "Alice"}

        result = await resolver.resolve_user("ou_abc")

        assert result == "Alice"
        mock_feishu_client.get_user.assert_called_once_with("ou_abc")

        cached = await resolver._cache.get("ou_abc")
        assert cached == "Alice"

    @pytest.mark.asyncio
    async def test_resolve_user_fallback_en_name(self, resolver, mock_feishu_client):
        """Test fallback to en_name when name is missing."""
        mock_feishu_client.get_user.return_value = {"en_name": "Alice"}

        result = await resolver.resolve_user("ou_abc")

        assert result == "Alice"

    @pytest.mark.asyncio
    async def test_resolve_user_empty_user_id(self, resolver, mock_feishu_client):
        """Test resolve_user with empty user_id."""
        result = await resolver.resolve_user("")
        assert result is None
        mock_feishu_client.get_user.assert_not_called()

    @pytest.mark.asyncio
    async def test_resolve_user_api_failure(self, resolver, mock_feishu_client):
        """Test resolve_user with API failure (negative caching)."""
        mock_feishu_client.get_user.side_effect = Exception("API error")

        result = await resolver.resolve_user("ou_abc")

        assert result is None
        mock_feishu_client.get_user.assert_called_once_with("ou_abc")

        cached = await resolver._cache.get("ou_abc")
        assert cached is None

        result2 = await resolver.resolve_user("ou_abc")
        assert result2 is None
        assert mock_feishu_client.get_user.call_count == 1

    @pytest.mark.asyncio
    async def test_resolve_user_not_found(self, resolver, mock_feishu_client):
        """Test resolve_user when API returns no user."""
        mock_feishu_client.get_user.return_value = None

        result = await resolver.resolve_user("ou_abc")

        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_batch(self, resolver, mock_feishu_client):
        """Test batch resolution."""
        mock_feishu_client.get_user.side_effect = [
            {"name": "Alice"},
            {"name": "Bob"},
        ]

        result = await resolver.resolve_batch(["ou_1", "ou_2"], max_concurrent=2)

        assert result == {"ou_1": "Alice", "ou_2": "Bob"}
        assert mock_feishu_client.get_user.call_count == 2

    @pytest.mark.asyncio
    async def test_resolve_batch_deduplication(self, resolver, mock_feishu_client):
        """Test batch deduplication."""
        mock_feishu_client.get_user.return_value = {"name": "Alice"}

        result = await resolver.resolve_batch(["ou_1", "ou_1", "ou_1"])

        assert result == {"ou_1": "Alice"}
        mock_feishu_client.get_user.assert_called_once()

    @pytest.mark.asyncio
    async def test_resolve_batch_empty_list(self, resolver, mock_feishu_client):
        """Test batch resolution with empty list."""
        result = await resolver.resolve_batch([])
        assert result == {}
        mock_feishu_client.get_user.assert_not_called()
