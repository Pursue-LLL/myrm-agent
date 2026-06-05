"""Tests for feishu SDK documents — FeishuDocumentsMixin methods."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.channels.providers.feishu.sdk import FeishuClient


def _mock_response(
    status_code: int = 200,
    json_data: dict | None = None,
) -> httpx.Response:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.is_success = 200 <= status_code < 300
    resp.json.return_value = json_data or {}
    return resp


@pytest.fixture
def client() -> FeishuClient:
    c = FeishuClient("app", "secret")
    c._token = "tok"
    c._token_expires_at = time.monotonic() + 3600
    mock_http = AsyncMock()
    mock_http.is_closed = False
    c._http = mock_http
    return c


class TestQueryDocumentMeta:
    @pytest.mark.asyncio
    async def test_success(self, client: FeishuClient) -> None:
        resp = _mock_response(
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
        resp = _mock_response(200, {"code": 99, "msg": "not found"})
        client._http.post = AsyncMock(return_value=resp)
        meta = await client.query_document_meta("tok_001", "docx")
        assert meta == {}

    @pytest.mark.asyncio
    async def test_data_not_dict(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 0, "data": "not_a_dict"})
        client._http.post = AsyncMock(return_value=resp)
        meta = await client.query_document_meta("tok_001", "docx")
        assert meta == {}

    @pytest.mark.asyncio
    async def test_metas_as_dict(self, client: FeishuClient) -> None:
        resp = _mock_response(
            200,
            {
                "code": 0,
                "data": {"metas": {"tok_001": {"title": "Dict Meta", "url": "u", "doc_type": "docx"}}},
            },
        )
        client._http.post = AsyncMock(return_value=resp)
        meta = await client.query_document_meta("tok_001", "docx")
        assert meta["title"] == "Dict Meta"

    @pytest.mark.asyncio
    async def test_metas_dict_value_not_dict(self, client: FeishuClient) -> None:
        resp = _mock_response(
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
        resp = _mock_response(200, {"code": 0, "data": {"metas": 42}})
        client._http.post = AsyncMock(return_value=resp)
        meta = await client.query_document_meta("tok_001", "docx")
        assert meta == {}


class TestListComments:
    @pytest.mark.asyncio
    async def test_single_page(self, client: FeishuClient) -> None:
        resp = _mock_response(
            200,
            {
                "code": 0,
                "data": {
                    "items": [{"comment_id": "c1"}, {"comment_id": "c2"}],
                    "has_more": False,
                },
            },
        )
        client._http.get = AsyncMock(return_value=resp)
        comments = await client.list_comments("tok_001", "docx")
        assert len(comments) == 2

    @pytest.mark.asyncio
    async def test_multi_page(self, client: FeishuClient) -> None:
        page1 = _mock_response(
            200,
            {
                "code": 0,
                "data": {"items": [{"comment_id": "c1"}], "has_more": True, "page_token": "pt2"},
            },
        )
        page2 = _mock_response(
            200,
            {
                "code": 0,
                "data": {"items": [{"comment_id": "c2"}], "has_more": False},
            },
        )
        client._http.get = AsyncMock(side_effect=[page1, page2])
        comments = await client.list_comments("tok_001", "docx")
        assert len(comments) == 2

    @pytest.mark.asyncio
    async def test_api_error_breaks(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 99, "msg": "fail"})
        client._http.get = AsyncMock(return_value=resp)
        comments = await client.list_comments("tok_001", "docx")
        assert comments == []

    @pytest.mark.asyncio
    async def test_data_not_dict_breaks(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 0, "data": "bad"})
        client._http.get = AsyncMock(return_value=resp)
        comments = await client.list_comments("tok_001", "docx")
        assert comments == []

    @pytest.mark.asyncio
    async def test_empty_page_token_breaks(self, client: FeishuClient) -> None:
        resp = _mock_response(
            200,
            {
                "code": 0,
                "data": {"items": [{"comment_id": "c1"}], "has_more": True, "page_token": ""},
            },
        )
        client._http.get = AsyncMock(return_value=resp)
        comments = await client.list_comments("tok_001", "docx")
        assert len(comments) == 1


class TestListCommentReplies:
    @pytest.mark.asyncio
    async def test_success_no_expect(self, client: FeishuClient) -> None:
        resp = _mock_response(
            200,
            {
                "code": 0,
                "data": {"items": [{"reply_id": "r1"}], "has_more": False},
            },
        )
        client._http.get = AsyncMock(return_value=resp)
        replies = await client.list_comment_replies("tok", "docx", "c1")
        assert len(replies) == 1

    @pytest.mark.asyncio
    async def test_expect_reply_found_immediately(self, client: FeishuClient) -> None:
        resp = _mock_response(
            200,
            {
                "code": 0,
                "data": {"items": [{"reply_id": "r1"}], "has_more": False},
            },
        )
        client._http.get = AsyncMock(return_value=resp)
        replies = await client.list_comment_replies(
            "tok",
            "docx",
            "c1",
            expect_reply_id="r1",
            retry_delay=0.01,
        )
        assert any(r["reply_id"] == "r1" for r in replies)

    @pytest.mark.asyncio
    async def test_expect_reply_not_found_retries(self, client: FeishuClient) -> None:
        empty = _mock_response(
            200,
            {
                "code": 0,
                "data": {"items": [], "has_more": False},
            },
        )
        client._http.get = AsyncMock(return_value=empty)
        replies = await client.list_comment_replies(
            "tok",
            "docx",
            "c1",
            expect_reply_id="r_missing",
            max_retries=2,
            retry_delay=0.01,
        )
        assert replies == []
        assert client._http.get.call_count == 2

    @pytest.mark.asyncio
    async def test_api_error_breaks_early(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 99, "msg": "fail"})
        client._http.get = AsyncMock(return_value=resp)
        replies = await client.list_comment_replies("tok", "docx", "c1")
        assert replies == []

    @pytest.mark.asyncio
    async def test_data_not_dict_breaks(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 0, "data": "bad"})
        client._http.get = AsyncMock(return_value=resp)
        replies = await client.list_comment_replies("tok", "docx", "c1")
        assert replies == []


class TestBatchQueryComment:
    @pytest.mark.asyncio
    async def test_success(self, client: FeishuClient) -> None:
        resp = _mock_response(
            200,
            {
                "code": 0,
                "data": {"items": [{"comment_id": "c1", "content": "test"}]},
            },
        )
        client._http.post = AsyncMock(return_value=resp)
        comment = await client.batch_query_comment("tok_001", "docx", "c1", max_retries=1)
        assert comment["comment_id"] == "c1"

    @pytest.mark.asyncio
    async def test_retry_and_fail(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 99, "msg": "eventual consistency"})
        client._http.post = AsyncMock(return_value=resp)
        comment = await client.batch_query_comment(
            "tok_001",
            "docx",
            "c1",
            max_retries=2,
            retry_delay=0.01,
        )
        assert comment == {}


class TestReplyToComment:
    @pytest.mark.asyncio
    async def test_success(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 0})
        client._http.post = AsyncMock(return_value=resp)
        ok, code = await client.reply_to_comment("tok_001", "docx", "c1", "hello")
        assert ok is True
        assert code == 0

    @pytest.mark.asyncio
    async def test_failure(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 99, "msg": "fail"})
        client._http.post = AsyncMock(return_value=resp)
        ok, code = await client.reply_to_comment("tok_001", "docx", "c1", "hello")
        assert ok is False
        assert code == 99

    @pytest.mark.asyncio
    async def test_html_sanitization(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 0})
        client._http.post = AsyncMock(return_value=resp)
        await client.reply_to_comment("tok_001", "docx", "c1", "a < b & c > d")
        call_args = client._http.post.call_args
        body = call_args.kwargs.get("json", call_args[1].get("json", {}))
        text = body["content"]["elements"][0]["text_run"]["text"]
        assert "&amp;" in text
        assert "&lt;" in text
        assert "&gt;" in text


class TestAddWholeComment:
    @pytest.mark.asyncio
    async def test_success(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 0})
        client._http.post = AsyncMock(return_value=resp)
        result = await client.add_whole_comment("tok", "docx", "nice doc")
        assert result is True

    @pytest.mark.asyncio
    async def test_failure(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 99, "msg": "fail"})
        client._http.post = AsyncMock(return_value=resp)
        result = await client.add_whole_comment("tok", "docx", "text")
        assert result is False

    @pytest.mark.asyncio
    async def test_html_sanitization(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 0})
        client._http.post = AsyncMock(return_value=resp)
        await client.add_whole_comment("tok", "docx", "a & b < c > d")
        call_args = client._http.post.call_args
        body = call_args.kwargs.get("json", call_args[1].get("json", {}))
        text_elem = body["reply_elements"][0]["text"]
        assert "&amp;" in text_elem


class TestCommentReactions:
    @pytest.mark.asyncio
    async def test_add_reaction_success(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 0})
        client._http.post = AsyncMock(return_value=resp)
        result = await client.add_comment_reaction("tok", "docx", "r1")
        assert result is True

    @pytest.mark.asyncio
    async def test_add_reaction_failure(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 99})
        client._http.post = AsyncMock(return_value=resp)
        result = await client.add_comment_reaction("tok", "docx", "r1")
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_reaction_success(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 0})
        client._http.post = AsyncMock(return_value=resp)
        result = await client.delete_comment_reaction("tok", "docx", "r1")
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_reaction_failure(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 99})
        client._http.post = AsyncMock(return_value=resp)
        result = await client.delete_comment_reaction("tok", "docx", "r1")
        assert result is False


class TestWiki:
    @pytest.mark.asyncio
    async def test_get_wiki_node(self, client: FeishuClient) -> None:
        resp = _mock_response(
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
        resp = _mock_response(200, {"code": 99, "msg": "not found"})
        client._http.get = AsyncMock(return_value=resp)
        token = await client.get_wiki_node("nonexist")
        assert token is None

    @pytest.mark.asyncio
    async def test_data_not_dict(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 0, "data": "bad"})
        client._http.get = AsyncMock(return_value=resp)
        token = await client.get_wiki_node("obj")
        assert token is None

    @pytest.mark.asyncio
    async def test_empty_wiki_token(self, client: FeishuClient) -> None:
        resp = _mock_response(
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
        resp = _mock_response(200, {"code": 0, "data": {"node": "not_dict"}})
        client._http.get = AsyncMock(return_value=resp)
        token = await client.get_wiki_node("obj")
        assert token is None


class TestCardKit:
    @pytest.mark.asyncio
    async def test_streaming_create_success(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 0})
        client._http.post = AsyncMock(return_value=resp)
        result = await client.streaming_card_create("card_001")
        assert result is True

    @pytest.mark.asyncio
    async def test_streaming_create_failure(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 99, "msg": "fail"})
        client._http.post = AsyncMock(return_value=resp)
        result = await client.streaming_card_create("card_001")
        assert result is False

    @pytest.mark.asyncio
    async def test_streaming_update_success(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 0})
        client._http.patch = AsyncMock(return_value=resp)
        result = await client.streaming_card_update("card_001", "content", seq=2)
        assert result is True

    @pytest.mark.asyncio
    async def test_streaming_update_failure(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 99, "msg": "fail"})
        client._http.patch = AsyncMock(return_value=resp)
        result = await client.streaming_card_update("card_001", "content", seq=2)
        assert result is False

    @pytest.mark.asyncio
    async def test_streaming_update_final(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 0})
        client._http.patch = AsyncMock(return_value=resp)
        result = await client.streaming_card_update("card_001", "final", seq=3, is_final=True)
        assert result is True
        call_args = client._http.patch.call_args
        body = call_args.kwargs.get("json", call_args[1].get("json", {}))
        assert body.get("is_final") is True


class TestBitable:
    @pytest.mark.asyncio
    async def test_get_records(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 0, "data": {"items": []}})
        client._http.get = AsyncMock(return_value=resp)
        result = await client.get_bitable_records("app_tok", "tbl_001")
        assert result["code"] == 0

    @pytest.mark.asyncio
    async def test_add_records_success(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 0})
        client._http.post = AsyncMock(return_value=resp)
        result = await client.add_bitable_records("app_tok", "tbl_001", [{"fields": {}}])
        assert result is True

    @pytest.mark.asyncio
    async def test_add_records_failure(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 99, "msg": "fail"})
        client._http.post = AsyncMock(return_value=resp)
        result = await client.add_bitable_records("app_tok", "tbl_001", [{"fields": {}}])
        assert result is False


class TestDocx:
    @pytest.mark.asyncio
    async def test_get_blocks(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 0, "data": {"items": []}})
        client._http.get = AsyncMock(return_value=resp)
        result = await client.get_docx_blocks("doc_001")
        assert result["code"] == 0

    @pytest.mark.asyncio
    async def test_append_blocks_success(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 0})
        client._http.post = AsyncMock(return_value=resp)
        result = await client.append_docx_blocks("doc_001", "blk_001", [{"type": "text"}])
        assert result is True

    @pytest.mark.asyncio
    async def test_append_blocks_failure(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 99, "msg": "fail"})
        client._http.post = AsyncMock(return_value=resp)
        result = await client.append_docx_blocks("doc_001", "blk_001", [{"type": "text"}])
        assert result is False
