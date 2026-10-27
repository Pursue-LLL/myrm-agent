"""Tests for Feishu document comment handler and routing."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import httpx
import pytest

from app.channels.core.exceptions import ChannelSendError
from app.channels.providers.feishu import FeishuChannel
from app.channels.providers.feishu.api import FeishuClient
from app.channels.providers.feishu.comment.handler import (
    CommentHandler,
    CommentRouteInfo,
    chunk_text,
    deliver_comment_reply,
    encode_comment_chat_id,
    parse_comment_recipient,
)
from app.channels.providers.feishu.models import (
    FeishuCommentEvent,
)
from app.channels.types import OutboundMessage


def _make_channel() -> FeishuChannel:
    return FeishuChannel(app_id="test_app_id", app_secret="test_app_secret")


def _mock_client(ch: FeishuChannel, bot_open_id: str = "bot_oid") -> AsyncMock:
    mock = AsyncMock(spec=FeishuClient)
    mock.bot_open_id = bot_open_id
    mock.is_configured = True
    mock._get_http.return_value = AsyncMock(spec=httpx.AsyncClient)
    ch._client = mock
    return mock


# ── encode / parse chat_id ─────────────────────────────────────


class TestChatIdEncoding:
    def test_encode_local(self) -> None:
        cid = encode_comment_chat_id("docx", "tok123", "cid456", False)
        assert cid == "comment-doc:docx:tok123:cid456:0"

    def test_encode_whole(self) -> None:
        cid = encode_comment_chat_id("doc", "abc", "xyz", True)
        assert cid == "comment-doc:doc:abc:xyz:1"

    def test_parse_local(self) -> None:
        route = parse_comment_recipient("comment-doc:docx:tok123:cid456:0")
        assert route is not None
        assert route.file_type == "docx"
        assert route.file_token == "tok123"
        assert route.comment_id == "cid456"
        assert route.is_whole is False

    def test_parse_whole(self) -> None:
        route = parse_comment_recipient("comment-doc:doc:abc:xyz:1")
        assert route is not None
        assert route.is_whole is True

    def test_parse_normal_chat_id(self) -> None:
        assert parse_comment_recipient("oc_abcdef123456") is None

    def test_parse_malformed(self) -> None:
        assert parse_comment_recipient("comment-doc:only_two:parts") is None

    def test_roundtrip(self) -> None:
        original = encode_comment_chat_id("sheet", "f_token", "c_id", True)
        route = parse_comment_recipient(original)
        assert route is not None
        assert route.file_type == "sheet"
        assert route.file_token == "f_token"
        assert route.comment_id == "c_id"
        assert route.is_whole is True


# ── chunk_text ─────────────────────────────────────────────────


class TestChunkText:
    def test_short_text_no_split(self) -> None:
        assert chunk_text("hello", 100) == ["hello"]

    def test_splits_at_newline(self) -> None:
        text = "line1\nline2\nline3"
        chunks = chunk_text(text, 10)
        assert len(chunks) >= 2
        assert "".join(chunks).replace("\n", "") == text.replace("\n", "")

    def test_hard_split_when_no_newline(self) -> None:
        text = "a" * 100
        chunks = chunk_text(text, 40)
        assert len(chunks) == 3
        assert "".join(chunks) == text

    def test_exact_limit(self) -> None:
        text = "a" * 4000
        assert chunk_text(text, 4000) == [text]


# ── deliver_comment_reply ──────────────────────────────────────


class TestDeliverCommentReply:
    @pytest.mark.asyncio
    async def test_local_reply_success(self) -> None:
        client = AsyncMock(spec=FeishuClient)
        client.reply_to_comment.return_value = (True, 0)
        route = CommentRouteInfo("docx", "tok", "cid", False)
        ok = await deliver_comment_reply(client, route, "Hello!")
        assert ok is True
        client.reply_to_comment.assert_called_once_with("tok", "docx", "cid", "Hello!")

    @pytest.mark.asyncio
    async def test_whole_reply_success(self) -> None:
        client = AsyncMock(spec=FeishuClient)
        client.add_whole_comment.return_value = True
        route = CommentRouteInfo("doc", "tok", "cid", True)
        ok = await deliver_comment_reply(client, route, "World")
        assert ok is True
        client.add_whole_comment.assert_called_once_with("tok", "doc", "World")

    @pytest.mark.asyncio
    async def test_fallback_on_1069302(self) -> None:
        client = AsyncMock(spec=FeishuClient)
        client.reply_to_comment.return_value = (False, 1069302)
        client.add_whole_comment.return_value = True
        route = CommentRouteInfo("docx", "tok", "cid", False)
        ok = await deliver_comment_reply(client, route, "Fallback")
        assert ok is True
        client.add_whole_comment.assert_called_once()

    @pytest.mark.asyncio
    async def test_chunked_delivery(self) -> None:
        client = AsyncMock(spec=FeishuClient)
        client.add_whole_comment.return_value = True
        route = CommentRouteInfo("doc", "tok", "cid", True)
        long_text = "a" * 8000
        ok = await deliver_comment_reply(client, route, long_text)
        assert ok is True
        assert client.add_whole_comment.call_count == 2

    @pytest.mark.asyncio
    async def test_failure_stops_chunking(self) -> None:
        client = AsyncMock(spec=FeishuClient)
        client.add_whole_comment.side_effect = [True, False]
        route = CommentRouteInfo("doc", "tok", "cid", True)
        long_text = "a\n" * 6000
        ok = await deliver_comment_reply(client, route, long_text)
        assert ok is False


# ── Pydantic models ────────────────────────────────────────────


class TestCommentModels:
    def test_comment_event_defaults(self) -> None:
        evt = FeishuCommentEvent()
        assert evt.comment_id == ""
        assert evt.notice_meta.file_token == ""
        assert evt.notice_meta.from_user_id.open_id == ""

    def test_comment_event_parsing(self) -> None:
        data = {
            "comment_id": "c123",
            "reply_id": "r456",
            "is_mentioned": True,
            "notice_meta": {
                "file_token": "ft_abc",
                "file_type": "docx",
                "notice_type": "add_reply",
                "from_user_id": {"open_id": "ou_sender"},
                "to_user_id": {"open_id": "ou_bot"},
            },
        }
        evt = FeishuCommentEvent.model_validate(data)
        assert evt.comment_id == "c123"
        assert evt.reply_id == "r456"
        assert evt.notice_meta.file_token == "ft_abc"
        assert evt.notice_meta.from_user_id.open_id == "ou_sender"


# ── Channel send routing ───────────────────────────────────────


class TestChannelCommentRouting:
    @pytest.mark.asyncio
    async def test_send_routes_to_comment_api(self) -> None:
        ch = _make_channel()
        client = _mock_client(ch)
        client.reply_to_comment.return_value = (True, 0)

        msg = OutboundMessage(
            channel="feishu",
            recipient_id="comment-doc:docx:ft_abc:c123:0",
            content="AI reply here",
            user_id="ou_user",
        )
        result = await ch.send(msg)
        assert result is not None
        client.reply_to_comment.assert_called_once()
        client.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_normal_message_unaffected(self) -> None:
        ch = _make_channel()
        client = _mock_client(ch)
        client.send_message.return_value = "msg_id_123"

        msg = OutboundMessage(
            channel="feishu",
            recipient_id="oc_chat123",
            content="Normal IM message",
            user_id="ou_user",
        )
        result = await ch.send(msg)
        assert result == "msg_id_123"
        client.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_no_reply_skips_delivery(self) -> None:
        ch = _make_channel()
        client = _mock_client(ch)

        msg = OutboundMessage(
            channel="feishu",
            recipient_id="comment-doc:docx:ft_abc:c123:0",
            content="NO_REPLY",
            user_id="ou_user",
        )
        result = await ch.send(msg)
        # A deliberate NO_REPLY is a handled outcome: it reports the locator, never None (a lost delivery).
        assert result == "comment-doc:docx:ft_abc:c123:0"
        client.reply_to_comment.assert_not_called()

    @pytest.mark.asyncio
    async def test_malformed_comment_recipient_is_a_permanent_failure(self) -> None:
        ch = _make_channel()
        _mock_client(ch)
        msg = OutboundMessage(channel="feishu", recipient_id="comment-doc:broken", content="reply", user_id="ou_user")

        with pytest.raises(ChannelSendError, match="malformed") as excinfo:
            await ch.send(msg)

        assert excinfo.value.retriable is False

    @pytest.mark.asyncio
    async def test_rejected_comment_reply_raises(self) -> None:
        ch = _make_channel()
        client = _mock_client(ch)
        client.reply_to_comment.return_value = (False, 99)
        msg = OutboundMessage(
            channel="feishu", recipient_id="comment-doc:docx:ft_abc:c123:0", content="AI reply here", user_id="ou_user"
        )

        with pytest.raises(ChannelSendError, match="comment reply failed"):
            await ch.send(msg)


# ── Webhook event routing ──────────────────────────────────────


class TestWebhookCommentRouting:
    @pytest.mark.asyncio
    async def test_comment_event_dispatched(self) -> None:
        ch = _make_channel()
        client = _mock_client(ch, bot_open_id="ou_bot")

        event_data = {
            "header": {
                "event_type": "drive.notice.comment_add_v1",
                "event_id": "ev_123",
                "create_time": "1700000000000",
            },
            "event": {
                "comment_id": "c100",
                "reply_id": "r200",
                "notice_meta": {
                    "file_token": "ft_doc1",
                    "file_type": "docx",
                    "notice_type": "add_reply",
                    "from_user_id": {"open_id": "ou_sender"},
                    "to_user_id": {"open_id": "ou_bot"},
                },
            },
        }

        captured: list[object] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: captured.append(msg))  # type: ignore[assignment]

        client.query_document_meta.return_value = {"title": "Test Doc", "url": "https://example.com"}
        client.batch_query_comment.return_value = {"is_whole": False, "quote": "quoted text"}
        client.list_comment_replies.return_value = [
            {
                "reply_id": "r200",
                "user_id": {"open_id": "ou_sender"},
                "content": {"elements": [{"type": "text_run", "text_run": {"text": "@bot what is this?"}}]},
            }
        ]
        client.add_comment_reaction.return_value = True
        client.delete_comment_reaction.return_value = True

        result = await ch.handle_webhook_event(event_data)
        assert result is None

        assert len(captured) == 1
        inbound = captured[0]
        assert inbound.chat_id.startswith("comment-doc:")
        assert inbound.sender_id == "ou_sender"
        assert "Test Doc" in inbound.content

    @pytest.mark.asyncio
    async def test_self_reply_filtered(self) -> None:
        ch = _make_channel()
        _mock_client(ch, bot_open_id="ou_bot")

        event_data = {
            "header": {
                "event_type": "drive.notice.comment_add_v1",
                "event_id": "ev_self",
            },
            "event": {
                "comment_id": "c100",
                "reply_id": "r200",
                "notice_meta": {
                    "file_token": "ft_doc1",
                    "file_type": "docx",
                    "notice_type": "add_reply",
                    "from_user_id": {"open_id": "ou_bot"},
                    "to_user_id": {"open_id": "ou_bot"},
                },
            },
        }

        ch._emit_inbound = AsyncMock()  # type: ignore[assignment]
        await ch.handle_webhook_event(event_data)
        ch._emit_inbound.assert_not_called()

    @pytest.mark.asyncio
    async def test_normal_message_event_unaffected(self) -> None:
        ch = _make_channel()
        _mock_client(ch)

        event_data = {
            "header": {
                "event_type": "im.message.receive_v1",
                "event_id": "ev_msg",
                "create_time": "1700000000000",
            },
            "event": {
                "sender": {
                    "sender_id": {"open_id": "ou_sender"},
                    "sender_type": "user",
                },
                "message": {
                    "message_id": "msg_123",
                    "chat_id": "oc_chat",
                    "chat_type": "p2p",
                    "message_type": "text",
                    "content": json.dumps({"text": "hello"}),
                },
            },
        }

        captured: list[object] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: captured.append(msg))  # type: ignore[assignment]
        await ch.handle_webhook_event(event_data)

        assert len(captured) == 1
        inbound = captured[0]
        assert not inbound.chat_id.startswith("comment-doc:")


# ── CommentHandler edge cases ──────────────────────────────────


class TestCommentHandlerEdgeCases:
    @pytest.mark.asyncio
    async def test_validation_failure_skips(self) -> None:
        ch = _make_channel()
        client = _mock_client(ch, bot_open_id="ou_bot")
        handler = CommentHandler(client, "ou_bot")
        ch._emit_inbound = AsyncMock()  # type: ignore[assignment]
        await handler.handle_comment_event({"bad": "data"}, ch)
        ch._emit_inbound.assert_not_called()

    @pytest.mark.asyncio
    async def test_notice_type_filter(self) -> None:
        ch = _make_channel()
        client = _mock_client(ch, bot_open_id="ou_bot")
        handler = CommentHandler(client, "ou_bot")
        ch._emit_inbound = AsyncMock()  # type: ignore[assignment]
        event_data: dict[str, object] = {
            "comment_id": "c1",
            "notice_meta": {
                "file_token": "ft",
                "file_type": "docx",
                "notice_type": "delete_comment",
                "from_user_id": {"open_id": "ou_sender"},
                "to_user_id": {"open_id": "ou_bot"},
            },
        }
        await handler.handle_comment_event(event_data, ch)
        ch._emit_inbound.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_fields_skips(self) -> None:
        ch = _make_channel()
        client = _mock_client(ch, bot_open_id="ou_bot")
        handler = CommentHandler(client, "ou_bot")
        ch._emit_inbound = AsyncMock()  # type: ignore[assignment]
        event_data: dict[str, object] = {
            "comment_id": "",
            "notice_meta": {
                "file_token": "",
                "file_type": "docx",
                "notice_type": "add_comment",
                "from_user_id": {"open_id": "ou_sender"},
                "to_user_id": {"open_id": "ou_bot"},
            },
        }
        await handler.handle_comment_event(event_data, ch)
        ch._emit_inbound.assert_not_called()

    @pytest.mark.asyncio
    async def test_wrong_receiver_skips(self) -> None:
        ch = _make_channel()
        client = _mock_client(ch, bot_open_id="ou_bot")
        handler = CommentHandler(client, "ou_bot")
        ch._emit_inbound = AsyncMock()  # type: ignore[assignment]
        event_data: dict[str, object] = {
            "comment_id": "c1",
            "notice_meta": {
                "file_token": "ft",
                "file_type": "docx",
                "notice_type": "add_comment",
                "from_user_id": {"open_id": "ou_sender"},
                "to_user_id": {"open_id": "ou_other"},
            },
        }
        await handler.handle_comment_event(event_data, ch)
        ch._emit_inbound.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_base_channel_skips(self) -> None:
        client = AsyncMock(spec=FeishuClient)
        client.bot_open_id = "ou_bot"
        handler = CommentHandler(client, "ou_bot")
        client.query_document_meta.return_value = {"title": "T", "url": ""}
        client.batch_query_comment.return_value = {"is_whole": False}
        client.list_comment_replies.return_value = []
        event_data: dict[str, object] = {
            "comment_id": "c1",
            "notice_meta": {
                "file_token": "ft",
                "file_type": "docx",
                "notice_type": "add_comment",
                "from_user_id": {"open_id": "ou_sender"},
                "to_user_id": {"open_id": "ou_bot"},
            },
        }
        await handler.handle_comment_event(event_data, "not_a_channel")

    @pytest.mark.asyncio
    async def test_whole_comment_prompt_built(self) -> None:
        ch = _make_channel()
        client = _mock_client(ch, bot_open_id="ou_bot")

        event_data: dict[str, object] = {
            "comment_id": "c1",
            "notice_meta": {
                "file_token": "ft",
                "file_type": "docx",
                "notice_type": "add_comment",
                "from_user_id": {"open_id": "ou_sender"},
                "to_user_id": {"open_id": "ou_bot"},
            },
        }

        client.query_document_meta.return_value = {"title": "Doc", "url": "https://feishu.cn/docx/ft"}
        client.batch_query_comment.return_value = {"is_whole": True}
        client.list_comments.return_value = [
            {
                "reply_list": {
                    "replies": [
                        {
                            "user_id": {"open_id": "ou_sender"},
                            "content": {"elements": [{"type": "text_run", "text_run": {"text": "question?"}}]},
                        },
                        {
                            "user_id": {"open_id": "ou_bot"},
                            "content": {"elements": [{"type": "text_run", "text_run": {"text": "answer"}}]},
                        },
                    ]
                }
            }
        ]
        client.add_comment_reaction.return_value = True
        client.delete_comment_reaction.return_value = True

        captured: list[object] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: captured.append(msg))  # type: ignore[assignment]

        handler = CommentHandler(client, "ou_bot")
        await handler.handle_comment_event(event_data, ch)

        assert len(captured) == 1
        inbound = captured[0]
        assert ":1" in inbound.chat_id
        assert "whole-document comment" in inbound.content

    @pytest.mark.asyncio
    async def test_whole_comment_no_current_text_fallback(self) -> None:
        ch = _make_channel()
        client = _mock_client(ch, bot_open_id="ou_bot")

        event_data: dict[str, object] = {
            "comment_id": "c1",
            "notice_meta": {
                "file_token": "ft",
                "file_type": "docx",
                "notice_type": "add_comment",
                "from_user_id": {"open_id": "ou_other_user"},
                "to_user_id": {"open_id": "ou_bot"},
            },
        }

        client.query_document_meta.return_value = {"title": "Doc", "url": ""}
        client.batch_query_comment.return_value = {"is_whole": True}
        client.list_comments.return_value = [
            {
                "reply_list": {
                    "replies": [
                        {
                            "user_id": {"open_id": "ou_someone"},
                            "content": {"elements": [{"type": "text_run", "text_run": {"text": "hello"}}]},
                        },
                    ]
                }
            }
        ]
        client.add_comment_reaction.return_value = True
        client.delete_comment_reaction.return_value = True

        captured: list[object] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: captured.append(msg))  # type: ignore[assignment]

        handler = CommentHandler(client, "ou_bot")
        await handler.handle_comment_event(event_data, ch)
        assert len(captured) == 1

    @pytest.mark.asyncio
    async def test_whole_comment_string_reply_list(self) -> None:
        ch = _make_channel()
        client = _mock_client(ch, bot_open_id="ou_bot")

        event_data: dict[str, object] = {
            "comment_id": "c1",
            "notice_meta": {
                "file_token": "ft",
                "file_type": "docx",
                "notice_type": "add_comment",
                "from_user_id": {"open_id": "ou_sender"},
                "to_user_id": {"open_id": "ou_bot"},
            },
        }

        client.query_document_meta.return_value = {"title": "Doc", "url": ""}
        client.batch_query_comment.return_value = {"is_whole": True}
        client.list_comments.return_value = [
            {
                "reply_list": json.dumps(
                    {
                        "replies": [
                            {"user_id": "ou_sender", "content": {"elements": [{"type": "text_run", "text_run": {"text": "hi"}}]}}
                        ]
                    }
                )
            }
        ]
        client.add_comment_reaction.return_value = True
        client.delete_comment_reaction.return_value = True

        captured: list[object] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: captured.append(msg))  # type: ignore[assignment]

        handler = CommentHandler(client, "ou_bot")
        await handler.handle_comment_event(event_data, ch)
        assert len(captured) == 1

    @pytest.mark.asyncio
    async def test_local_comment_fallback_target(self) -> None:
        ch = _make_channel()
        client = _mock_client(ch, bot_open_id="ou_bot")

        event_data: dict[str, object] = {
            "comment_id": "c1",
            "reply_id": "r_nonexistent",
            "notice_meta": {
                "file_token": "ft",
                "file_type": "docx",
                "notice_type": "add_reply",
                "from_user_id": {"open_id": "ou_sender"},
                "to_user_id": {"open_id": "ou_bot"},
            },
        }

        client.query_document_meta.return_value = {"title": "Doc", "url": ""}
        client.batch_query_comment.return_value = {"is_whole": False, "quote": "quoted"}
        client.list_comment_replies.return_value = [
            {
                "reply_id": "r1",
                "user_id": {"open_id": "ou_sender"},
                "content": {"elements": [{"type": "text_run", "text_run": {"text": "my msg"}}]},
            },
        ]
        client.add_comment_reaction.return_value = True
        client.delete_comment_reaction.return_value = True

        captured: list[object] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: captured.append(msg))  # type: ignore[assignment]

        handler = CommentHandler(client, "ou_bot")
        await handler.handle_comment_event(event_data, ch)
        assert len(captured) == 1

    @pytest.mark.asyncio
    async def test_collect_raw_replies_handles_variants(self) -> None:
        comments: list[dict[str, object]] = [
            {"reply_list": {"replies": [{"text": "a"}, "not_a_dict"]}},
            {"reply_list": json.dumps({"replies": [{"text": "b"}]})},
            {"reply_list": "invalid json {"},
            {"reply_list": 42},
        ]
        result = CommentHandler._collect_raw_replies(comments)
        assert len(result) == 2
        assert result[0]["text"] == "a"
        assert result[1]["text"] == "b"
