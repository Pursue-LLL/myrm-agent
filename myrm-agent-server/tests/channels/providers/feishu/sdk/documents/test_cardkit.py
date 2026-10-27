"""Tests for the CardKit streaming operations of FeishuClient (documents/_cardkit.py)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.channels.providers.feishu.sdk import FeishuClient

from .support import mock_response


class TestCardKit:
    @pytest.mark.asyncio
    async def test_streaming_create_success(self, client: FeishuClient) -> None:
        resp = mock_response(200, {"code": 0})
        client._http.post = AsyncMock(return_value=resp)
        result = await client.streaming_card_create("card_001")
        assert result is True

    @pytest.mark.asyncio
    async def test_streaming_create_failure(self, client: FeishuClient) -> None:
        resp = mock_response(200, {"code": 99, "msg": "fail"})
        client._http.post = AsyncMock(return_value=resp)
        result = await client.streaming_card_create("card_001")
        assert result is False

    @pytest.mark.asyncio
    async def test_streaming_update_success(self, client: FeishuClient) -> None:
        resp = mock_response(200, {"code": 0})
        client._http.patch = AsyncMock(return_value=resp)
        result = await client.streaming_card_update("card_001", "content", seq=2)
        assert result is True

    @pytest.mark.asyncio
    async def test_streaming_update_failure(self, client: FeishuClient) -> None:
        resp = mock_response(200, {"code": 99, "msg": "fail"})
        client._http.patch = AsyncMock(return_value=resp)
        result = await client.streaming_card_update("card_001", "content", seq=2)
        assert result is False

    @pytest.mark.asyncio
    async def test_streaming_update_final(self, client: FeishuClient) -> None:
        resp = mock_response(200, {"code": 0})
        client._http.patch = AsyncMock(return_value=resp)
        result = await client.streaming_card_update("card_001", "final", seq=3, is_final=True)
        assert result is True
        call_args = client._http.patch.call_args
        body = call_args.kwargs.get("json", call_args[1].get("json", {}))
        assert body.get("is_final") is True
