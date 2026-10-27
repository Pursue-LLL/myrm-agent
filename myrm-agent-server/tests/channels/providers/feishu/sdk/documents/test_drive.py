"""Tests for the Drive and wiki lookups of FeishuClient (documents/_drive.py)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.channels.providers.feishu.sdk import FeishuClient

from .support import mock_response


class TestQueryDocumentMeta:
    @pytest.mark.asyncio
    async def test_success(self, client: FeishuClient) -> None:
        resp = mock_response(
            200,
            {
                "code": 0,
                "data": {"metas": [{"title": "My Doc", "url": "https://...", "doc_type": "docx"}]},
            },
        )
        client._http.post = AsyncMock(return_value=resp)
        meta = await client.query_document_meta("tok_001", "docx")
        assert meta["title"] == "My Doc"

    @pytest.mark.asyncio
    async def test_failure(self, client: FeishuClient) -> None:
        resp = mock_response(200, {"code": 99, "msg": "not found"})
        client._http.post = AsyncMock(return_value=resp)
        meta = await client.query_document_meta("tok_001", "docx")
        assert meta == {}

    @pytest.mark.asyncio
    async def test_data_not_dict(self, client: FeishuClient) -> None:
        resp = mock_response(200, {"code": 0, "data": "not_a_dict"})
        client._http.post = AsyncMock(return_value=resp)
        meta = await client.query_document_meta("tok_001", "docx")
        assert meta == {}

    @pytest.mark.asyncio
    async def test_metas_as_dict(self, client: FeishuClient) -> None:
        resp = mock_response(
            200,
            {
                "code": 0,
                "data": {
                    "metas": {
                        "tok_001": {
                            "title": "Dict Meta",
                            "url": "u",
                            "doc_type": "docx",
                        }
                    }
                },
            },
        )
        client._http.post = AsyncMock(return_value=resp)
        meta = await client.query_document_meta("tok_001", "docx")
        assert meta["title"] == "Dict Meta"

    @pytest.mark.asyncio
    async def test_metas_dict_value_not_dict(self, client: FeishuClient) -> None:
        resp = mock_response(
            200,
            {
                "code": 0,
                "data": {"metas": {"tok_001": "bad_value"}},
            },
        )
        client._http.post = AsyncMock(return_value=resp)
        meta = await client.query_document_meta("tok_001", "docx")
        assert meta == {"title": "", "url": "", "doc_type": "docx"}

    @pytest.mark.asyncio
    async def test_metas_empty_or_other(self, client: FeishuClient) -> None:
        resp = mock_response(200, {"code": 0, "data": {"metas": 42}})
        client._http.post = AsyncMock(return_value=resp)
        meta = await client.query_document_meta("tok_001", "docx")
        assert meta == {}


class TestWiki:
    @pytest.mark.asyncio
    async def test_get_wiki_node(self, client: FeishuClient) -> None:
        resp = mock_response(
            200,
            {
                "code": 0,
                "data": {"node": {"node_token": "wiki_node_001"}},
            },
        )
        client._http.get = AsyncMock(return_value=resp)
        token = await client.get_wiki_node("obj_tok_001")
        assert token == "wiki_node_001"

    @pytest.mark.asyncio
    async def test_not_found(self, client: FeishuClient) -> None:
        resp = mock_response(200, {"code": 99, "msg": "not found"})
        client._http.get = AsyncMock(return_value=resp)
        token = await client.get_wiki_node("nonexist")
        assert token is None

    @pytest.mark.asyncio
    async def test_data_not_dict(self, client: FeishuClient) -> None:
        resp = mock_response(200, {"code": 0, "data": "bad"})
        client._http.get = AsyncMock(return_value=resp)
        token = await client.get_wiki_node("obj")
        assert token is None

    @pytest.mark.asyncio
    async def test_empty_wiki_token(self, client: FeishuClient) -> None:
        resp = mock_response(
            200,
            {
                "code": 0,
                "data": {"node": {"node_token": ""}},
            },
        )
        client._http.get = AsyncMock(return_value=resp)
        token = await client.get_wiki_node("obj")
        assert token is None

    @pytest.mark.asyncio
    async def test_node_not_dict(self, client: FeishuClient) -> None:
        resp = mock_response(200, {"code": 0, "data": {"node": "not_dict"}})
        client._http.get = AsyncMock(return_value=resp)
        token = await client.get_wiki_node("obj")
        assert token is None


class TestDownloadMedia:
    @pytest.mark.asyncio
    async def test_download_media_success(self, client: FeishuClient) -> None:
        resp = mock_response(200, {"code": 0})
        resp.content = b"\x89PNG\r\n\x1a\nfake-image"
        client._http.get = AsyncMock(return_value=resp)
        data = await client.download_media("img_v2_abc")
        assert data == b"\x89PNG\r\n\x1a\nfake-image"

    @pytest.mark.asyncio
    async def test_download_media_failure_returns_none(self, client: FeishuClient) -> None:
        resp = mock_response(403, {"code": 99991663, "msg": "no permission"})
        client._http.get = AsyncMock(return_value=resp)
        assert await client.download_media("img_v2_abc") is None
        assert await client.download_media("  ") is None
