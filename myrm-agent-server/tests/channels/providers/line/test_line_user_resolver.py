"""LINEUserResolver tests — profile resolution, caching, negative caching, batch."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.channels.providers.line.api import LineClient
from app.channels.providers.line.user_resolver import LINEUserResolver


def _make_resolver() -> tuple[LINEUserResolver, AsyncMock]:
    mock_api = AsyncMock(spec=LineClient)
    resolver = LINEUserResolver(mock_api)
    return resolver, mock_api


class TestResolveUser:
    @pytest.mark.asyncio
    async def test_resolve_success(self) -> None:
        resolver, mock_api = _make_resolver()
        mock_api.get_user_profile.return_value = {"userId": "U1", "displayName": "Alice"}
        assert await resolver.resolve_user("U1") == "Alice"
        mock_api.get_user_profile.assert_awaited_once_with("U1")

    @pytest.mark.asyncio
    async def test_resolve_blank_name_returns_none(self) -> None:
        resolver, mock_api = _make_resolver()
        mock_api.get_user_profile.return_value = {"userId": "U1", "displayName": "   "}
        assert await resolver.resolve_user("U1") is None

    @pytest.mark.asyncio
    async def test_resolve_non_string_name_returns_none(self) -> None:
        resolver, mock_api = _make_resolver()
        mock_api.get_user_profile.return_value = {"userId": "U1", "displayName": 123}
        assert await resolver.resolve_user("U1") is None

    @pytest.mark.asyncio
    async def test_resolve_empty_profile_returns_none(self) -> None:
        resolver, mock_api = _make_resolver()
        mock_api.get_user_profile.return_value = {}
        assert await resolver.resolve_user("U1") is None

    @pytest.mark.asyncio
    async def test_resolve_empty_id_returns_none(self) -> None:
        resolver, _mock_api = _make_resolver()
        assert await resolver.resolve_user("") is None

    @pytest.mark.asyncio
    async def test_resolve_api_failure_returns_none(self) -> None:
        resolver, mock_api = _make_resolver()
        mock_api.get_user_profile.side_effect = RuntimeError("network error")
        assert await resolver.resolve_user("U1") is None


class TestCaching:
    @pytest.mark.asyncio
    async def test_positive_result_cached(self) -> None:
        resolver, mock_api = _make_resolver()
        mock_api.get_user_profile.return_value = {"userId": "U1", "displayName": "Alice"}
        assert await resolver.resolve_user("U1") == "Alice"
        assert await resolver.resolve_user("U1") == "Alice"
        mock_api.get_user_profile.assert_awaited_once_with("U1")

    @pytest.mark.asyncio
    async def test_negative_result_cached(self) -> None:
        resolver, mock_api = _make_resolver()
        mock_api.get_user_profile.return_value = {}
        assert await resolver.resolve_user("U1") is None
        assert await resolver.resolve_user("U1") is None
        mock_api.get_user_profile.assert_awaited_once_with("U1")

    @pytest.mark.asyncio
    async def test_api_failure_cached_negative(self) -> None:
        resolver, mock_api = _make_resolver()
        mock_api.get_user_profile.side_effect = RuntimeError("boom")
        assert await resolver.resolve_user("U1") is None
        assert await resolver.resolve_user("U1") is None
        mock_api.get_user_profile.assert_awaited_once_with("U1")


class TestResolveBatch:
    @pytest.mark.asyncio
    async def test_batch_deduplicates_and_resolves(self) -> None:
        resolver, mock_api = _make_resolver()

        async def _profile(user_id: str) -> dict[str, str]:
            return {"userId": user_id, "displayName": f"Name-{user_id}"}

        mock_api.get_user_profile.side_effect = _profile
        result = await resolver.resolve_batch(["U1", "U1", "U2"])
        assert result == {"U1": "Name-U1", "U2": "Name-U2"}

    @pytest.mark.asyncio
    async def test_batch_empty(self) -> None:
        resolver, _mock_api = _make_resolver()
        assert await resolver.resolve_batch([]) == {}
