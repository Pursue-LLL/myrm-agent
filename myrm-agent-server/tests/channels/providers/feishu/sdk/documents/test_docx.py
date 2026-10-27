"""Tests for the Docx operations of FeishuClient (documents/_docx.py)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from app.channels.providers.feishu.sdk import DocumentContent, FeishuClient

from .support import mock_response

_TABLE_MARKDOWN = "# Q3 plan\n\n| owner | due |\n| --- | --- |\n| Ana | 10-31 |\n"


class TestDocxBlocks:
    @pytest.mark.asyncio
    async def test_get_blocks(self, client: FeishuClient) -> None:
        resp = mock_response(200, {"code": 0, "data": {"items": []}})
        client._http.get = AsyncMock(return_value=resp)
        result = await client.get_docx_blocks("doc_001")
        assert result["code"] == 0

    @pytest.mark.asyncio
    async def test_get_blocks_paginates_until_exhausted(self, client: FeishuClient) -> None:
        page1 = mock_response(
            200,
            {
                "code": 0,
                "data": {
                    "items": [{"block_id": "b1"}],
                    "has_more": True,
                    "page_token": "tok-2",
                },
            },
        )
        page2 = mock_response(
            200,
            {
                "code": 0,
                "data": {
                    "items": [{"block_id": "b2"}],
                    "has_more": False,
                },
            },
        )
        client._http.get = AsyncMock(side_effect=[page1, page2])
        result = await client.get_docx_blocks("doc_001")
        assert result["code"] == 0
        items = result["data"]["items"]
        assert [item["block_id"] for item in items] == ["b1", "b2"]
        assert client._http.get.await_args_list[1].kwargs["params"]["page_token"] == "tok-2"

    @pytest.mark.asyncio
    async def test_get_blocks_stops_on_api_error(self, client: FeishuClient) -> None:
        resp = mock_response(200, {"code": 99, "msg": "fail"})
        client._http.get = AsyncMock(return_value=resp)
        result = await client.get_docx_blocks("doc_001")
        assert result["code"] == 99


class TestGetDocumentContent:
    @pytest.mark.asyncio
    async def test_returns_the_markdown_with_tables_intact(self, client: FeishuClient) -> None:
        client._http.get = AsyncMock(return_value=mock_response(200, {"code": 0, "data": {"content": _TABLE_MARKDOWN}}))

        result = await client.get_document_content("doc_001")

        assert result == DocumentContent(code=0, markdown=_TABLE_MARKDOWN)
        assert result.ok

    @pytest.mark.asyncio
    async def test_asks_for_markdown_with_the_tenant_token(self, client: FeishuClient) -> None:
        client._http.get = AsyncMock(return_value=mock_response(200, {"code": 0, "data": {"content": "x"}}))

        await client.get_document_content("doc_001")

        call = client._http.get.await_args
        assert call.args[0].endswith("/docs/v1/content")
        assert call.kwargs["params"] == {"doc_token": "doc_001", "doc_type": "docx", "content_type": "markdown"}
        assert call.kwargs["headers"] == {"Authorization": "Bearer tok"}

    @pytest.mark.asyncio
    async def test_an_empty_document_is_still_a_success(self, client: FeishuClient) -> None:
        client._http.get = AsyncMock(return_value=mock_response(200, {"code": 0, "data": {"content": ""}}))

        result = await client.get_document_content("doc_001")

        assert result.ok
        assert result.markdown == ""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("status", "body", "code"),
        [
            (403, {"code": 2889902, "msg": "no permission"}, 2889902),
            (403, {"code": 2889906, "msg": "document deleted"}, 2889906),
            (400, {"code": 2889914, "msg": "token not found"}, 2889914),
            (500, {"code": 2889925, "msg": "document too large"}, 2889925),
            (200, {"code": 99991400, "msg": "rate limited"}, 99991400),
            (429, {"code": 99991400, "msg": "rate limited"}, 99991400),
        ],
    )
    async def test_reports_the_feishu_code_the_body_carries(
        self, client: FeishuClient, status: int, body: dict, code: int
    ) -> None:
        client._http.get = AsyncMock(return_value=mock_response(status, body))

        result = await client.get_document_content("doc_001")

        assert result.code == code
        assert result.message == body["msg"]
        assert not result.ok
        assert result.markdown == ""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("status", "body", "code"),
        [
            (502, {"msg": "bad gateway"}, 502),
            (500, {"code": 0, "msg": "odd"}, 500),
            (200, {"code": "oops", "msg": "wrong type"}, -1),
            (200, {"code": True, "msg": "a bool is not a code"}, -1),
            (200, {"code": 0, "data": {}}, -1),
            (200, {"code": 0, "data": {"content": 7}}, -1),
            (200, {"code": 0}, -1),
        ],
    )
    async def test_never_counts_a_malformed_or_failed_reply_as_success(
        self, client: FeishuClient, status: int, body: dict, code: int
    ) -> None:
        client._http.get = AsyncMock(return_value=mock_response(status, body))

        result = await client.get_document_content("doc_001")

        assert result.code == code
        assert not result.ok

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("status", "code"), [(502, 502), (200, -1)])
    async def test_a_reply_that_is_not_json_reports_the_status(self, client: FeishuClient, status: int, code: int) -> None:
        resp = mock_response(status)
        resp.json.side_effect = ValueError("not json")
        client._http.get = AsyncMock(return_value=resp)

        result = await client.get_document_content("doc_001")

        assert result.code == code
        assert f"HTTP {status}" in result.message

    @pytest.mark.asyncio
    async def test_a_reply_that_is_not_an_object_is_unreadable(self, client: FeishuClient) -> None:
        client._http.get = AsyncMock(return_value=mock_response(200, ["not", "an", "object"]))

        result = await client.get_document_content("doc_001")

        assert result.code == -1

    @pytest.mark.asyncio
    async def test_a_network_failure_propagates_to_the_caller(self, client: FeishuClient) -> None:
        client._http.get = AsyncMock(side_effect=httpx.ConnectTimeout("timed out"))

        with pytest.raises(httpx.ConnectTimeout):
            await client.get_document_content("doc_001")


class TestAppendDocxBlocks:
    @pytest.mark.asyncio
    async def test_append_blocks_success(self, client: FeishuClient) -> None:
        client._http.post = AsyncMock(return_value=mock_response(200, {"code": 0}))
        assert await client.append_docx_blocks("doc_001", "blk_001", [{"type": "text"}]) is True
        call = client._http.post.await_args
        assert call.args[0].endswith("/docx/v1/documents/doc_001/blocks/blk_001/children/batch_create")
        assert call.kwargs["json"] == {"children": [{"type": "text"}]}

    @pytest.mark.asyncio
    async def test_append_blocks_failure(self, client: FeishuClient) -> None:
        client._http.post = AsyncMock(return_value=mock_response(200, {"code": 99, "msg": "fail"}))
        assert await client.append_docx_blocks("doc_001", "blk_001", [{"type": "text"}]) is False
