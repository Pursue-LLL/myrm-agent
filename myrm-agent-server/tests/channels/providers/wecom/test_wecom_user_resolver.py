"""Unit tests for WeCom user resolver."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.providers.wecom.user_resolver import WeComUserResolver


@pytest.fixture
def mock_wecom_channel():
    """Mock WeComChannel for testing."""
    channel = MagicMock()
    channel.api_get_user = AsyncMock()
    return channel


@pytest.fixture
def resolver(mock_wecom_channel):
    """WeComUserResolver with mocked channel."""
    return WeComUserResolver(mock_wecom_channel, cache_ttl=60, cache_max_size=100)


class TestWeComUserResolver:
    @pytest.mark.asyncio
    async def test_resolve_user_cache_hit(self, resolver, mock_wecom_channel):
        """Test resolve_user with cache hit."""
        await resolver._cache.set("zhangsan", "张三")

        result = await resolver.resolve_user("zhangsan")

        assert result == "张三"
        mock_wecom_channel.api_get_user.assert_not_called()

    @pytest.mark.asyncio
    async def test_resolve_user_api_call(self, resolver, mock_wecom_channel):
        """Test resolve_user with API call."""
        mock_wecom_channel.api_get_user.return_value = {"name": "张三", "alias": "zs"}

        result = await resolver.resolve_user("zhangsan")

        assert result == "张三"
        mock_wecom_channel.api_get_user.assert_called_once_with("zhangsan")

        cached = await resolver._cache.get("zhangsan")
        assert cached == "张三"

    @pytest.mark.asyncio
    async def test_resolve_user_fallback_alias(self, resolver, mock_wecom_channel):
        """Test fallback to alias when name is missing."""
        mock_wecom_channel.api_get_user.return_value = {"alias": "zs"}

        result = await resolver.resolve_user("zhangsan")

        assert result == "zs"

    @pytest.mark.asyncio
    async def test_resolve_user_empty_user_id(self, resolver, mock_wecom_channel):
        """Test resolve_user with empty user_id."""
        result = await resolver.resolve_user("")
        assert result is None
        mock_wecom_channel.api_get_user.assert_not_called()

    @pytest.mark.asyncio
    async def test_resolve_user_api_failure(self, resolver, mock_wecom_channel):
        """Test resolve_user with API failure (negative caching)."""
        mock_wecom_channel.api_get_user.side_effect = Exception("API error")

        result = await resolver.resolve_user("zhangsan")

        assert result is None
        mock_wecom_channel.api_get_user.assert_called_once_with("zhangsan")

        cached = await resolver._cache.get("zhangsan")
        assert cached is None

        result2 = await resolver.resolve_user("zhangsan")
        assert result2 is None
        assert mock_wecom_channel.api_get_user.call_count == 1

    @pytest.mark.asyncio
    async def test_resolve_user_not_found(self, resolver, mock_wecom_channel):
        """Test resolve_user when API returns no user."""
        mock_wecom_channel.api_get_user.return_value = None

        result = await resolver.resolve_user("zhangsan")

        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_batch(self, resolver, mock_wecom_channel):
        """Test batch resolution."""
        mock_wecom_channel.api_get_user.side_effect = [
            {"name": "张三"},
            {"name": "李四"},
        ]

        result = await resolver.resolve_batch(["zhangsan", "lisi"], max_concurrent=2)

        assert result == {"zhangsan": "张三", "lisi": "李四"}
        assert mock_wecom_channel.api_get_user.call_count == 2

    @pytest.mark.asyncio
    async def test_resolve_batch_deduplication(self, resolver, mock_wecom_channel):
        """Test batch deduplication."""
        mock_wecom_channel.api_get_user.return_value = {"name": "张三"}

        result = await resolver.resolve_batch(["zhangsan", "zhangsan", "zhangsan"])

        assert result == {"zhangsan": "张三"}
        mock_wecom_channel.api_get_user.assert_called_once()

    @pytest.mark.asyncio
    async def test_resolve_batch_empty_list(self, resolver, mock_wecom_channel):
        """Test batch resolution with empty list."""
        result = await resolver.resolve_batch([])
        assert result == {}
        mock_wecom_channel.api_get_user.assert_not_called()
