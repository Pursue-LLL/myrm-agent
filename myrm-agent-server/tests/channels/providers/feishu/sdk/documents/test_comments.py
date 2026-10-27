"""Tests for the comment operations of FeishuClient (documents/_comments.py)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.channels.providers.feishu.sdk import FeishuClient

from .support import mock_response


class TestListComments:
    @pytest.mark.asyncio
    async def test_single_page(self, client: FeishuClient) -> None:
        resp = mock_response(
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
        page1 = mock_response(
            200,
            {
                "code": 0,
                "data": {
                    "items": [{"comment_id": "c1"}],
                    "has_more": True,
                    "page_token": "pt2",
                },
            },
        )
        page2 = mock_response(
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
        resp = mock_response(200, {"code": 99, "msg": "fail"})
        client._http.get = AsyncMock(return_value=resp)
        comments = await client.list_comments("tok_001", "docx")
        assert comments == []

    @pytest.mark.asyncio
    async def test_data_not_dict_breaks(self, client: FeishuClient) -> None:
        resp = mock_response(200, {"code": 0, "data": "bad"})
        client._http.get = AsyncMock(return_value=resp)
        comments = await client.list_comments("tok_001", "docx")
        assert comments == []

    @pytest.mark.asyncio
    async def test_empty_page_token_breaks(self, client: FeishuClient) -> None:
        resp = mock_response(
            200,
            {
                "code": 0,
                "data": {
                    "items": [{"comment_id": "c1"}],
                    "has_more": True,
                    "page_token": "",
                },
            },
        )
        client._http.get = AsyncMock(return_value=resp)
        comments = await client.list_comments("tok_001", "docx")
        assert len(comments) == 1


class TestListCommentReplies:
    @pytest.mark.asyncio
    async def test_success_no_expect(self, client: FeishuClient) -> None:
        resp = mock_response(
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
        resp = mock_response(
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
        empty = mock_response(
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
        resp = mock_response(200, {"code": 99, "msg": "fail"})
        client._http.get = AsyncMock(return_value=resp)
        replies = await client.list_comment_replies("tok", "docx", "c1")
        assert replies == []

    @pytest.mark.asyncio
    async def test_data_not_dict_breaks(self, client: FeishuClient) -> None:
        resp = mock_response(200, {"code": 0, "data": "bad"})
        client._http.get = AsyncMock(return_value=resp)
        replies = await client.list_comment_replies("tok", "docx", "c1")
        assert replies == []


class TestBatchQueryComment:
    @pytest.mark.asyncio
    async def test_success(self, client: FeishuClient) -> None:
        resp = mock_response(
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
        resp = mock_response(200, {"code": 99, "msg": "eventual consistency"})
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
        resp = mock_response(200, {"code": 0})
        client._http.post = AsyncMock(return_value=resp)
        ok, code = await client.reply_to_comment("tok_001", "docx", "c1", "hello")
        assert ok is True
        assert code == 0

    @pytest.mark.asyncio
    async def test_failure(self, client: FeishuClient) -> None:
        resp = mock_response(200, {"code": 99, "msg": "fail"})
        client._http.post = AsyncMock(return_value=resp)
        ok, code = await client.reply_to_comment("tok_001", "docx", "c1", "hello")
        assert ok is False
        assert code == 99

    @pytest.mark.asyncio
    async def test_html_sanitization(self, client: FeishuClient) -> None:
        resp = mock_response(200, {"code": 0})
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
        resp = mock_response(200, {"code": 0})
        client._http.post = AsyncMock(return_value=resp)
        result = await client.add_whole_comment("tok", "docx", "nice doc")
        assert result is True

    @pytest.mark.asyncio
    async def test_failure(self, client: FeishuClient) -> None:
        resp = mock_response(200, {"code": 99, "msg": "fail"})
        client._http.post = AsyncMock(return_value=resp)
        result = await client.add_whole_comment("tok", "docx", "text")
        assert result is False

    @pytest.mark.asyncio
    async def test_html_sanitization(self, client: FeishuClient) -> None:
        resp = mock_response(200, {"code": 0})
        client._http.post = AsyncMock(return_value=resp)
        await client.add_whole_comment("tok", "docx", "a & b < c > d")
        call_args = client._http.post.call_args
        body = call_args.kwargs.get("json", call_args[1].get("json", {}))
        text_elem = body["reply_elements"][0]["text"]
        assert "&amp;" in text_elem


class TestCommentReactions:
    @pytest.mark.asyncio
    async def test_add_reaction_success(self, client: FeishuClient) -> None:
        resp = mock_response(200, {"code": 0})
        client._http.post = AsyncMock(return_value=resp)
        result = await client.add_comment_reaction("tok", "docx", "r1")
        assert result is True

    @pytest.mark.asyncio
    async def test_add_reaction_failure(self, client: FeishuClient) -> None:
        resp = mock_response(200, {"code": 99})
        client._http.post = AsyncMock(return_value=resp)
        result = await client.add_comment_reaction("tok", "docx", "r1")
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_reaction_success(self, client: FeishuClient) -> None:
        resp = mock_response(200, {"code": 0})
        client._http.post = AsyncMock(return_value=resp)
        result = await client.delete_comment_reaction("tok", "docx", "r1")
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_reaction_failure(self, client: FeishuClient) -> None:
        resp = mock_response(200, {"code": 99})
        client._http.post = AsyncMock(return_value=resp)
        result = await client.delete_comment_reaction("tok", "docx", "r1")
        assert result is False
