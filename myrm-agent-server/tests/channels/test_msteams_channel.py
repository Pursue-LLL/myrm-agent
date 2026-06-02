"""MSTeamsChannel contract compliance + activity parsing + outbound + helpers tests."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.channels.core.base import BaseChannel, ChannelStatus
from app.channels.core.exceptions import ChannelAuthError
from app.channels.providers.msteams import MSTeamsChannel
from app.channels.providers.msteams.helpers import (
    build_adaptive_card_activity,
    decode_html_entities,
    decode_message_key,
    encode_message_key,
    extract_quote_context,
    html_to_plain,
    strip_mention_tags,
)
from app.channels.providers.msteams.models import (
    BotActivity,
)
from app.channels.types import MediaAttachment, MediaType, OutboundMessage
from app.channels.types.components import (
    ActionButton,
    ButtonStyle,
    QuickReply,
)

from .channel_test_base import ChannelTestBase


def _make_channel(**kwargs: object) -> MSTeamsChannel:
    defaults: dict[str, object] = {"app_id": "test_app_id", "app_password": "test_app_password"}
    defaults.update(kwargs)
    return MSTeamsChannel(**defaults)


def _seed_service_url(ch: MSTeamsChannel, conv_id: str, url: str = "https://smba.trafficmanager.net/apis") -> None:
    ch._api._service_url_cache[conv_id] = (url, time.monotonic())


def _make_outbound(recipient_id: str, content: str = "", **kwargs: object) -> OutboundMessage:
    return OutboundMessage(channel="teams", user_id="u1", recipient_id=recipient_id, content=content, **kwargs)


def _mock_http_on_channel(ch: MSTeamsChannel) -> MagicMock:
    """Replace the shared HTTP client on both channel and api."""
    mock_http = MagicMock()
    ch._http = mock_http
    ch._api._http = mock_http
    return mock_http


def _set_valid_token(ch: MSTeamsChannel) -> None:
    """Set a valid token on the api layer."""
    ch._api._access_token = "tok"
    ch._api._token_expires_at = time.monotonic() + 3600


class TestMSTeamsChannelContract(ChannelTestBase):
    def create_channel(self) -> BaseChannel:
        return MSTeamsChannel(app_id="test_app_id", app_password="test_app_password")


# ── Pydantic Model Tests ─────────────────────────────────────


class TestBotActivityModel:
    def test_message_activity(self) -> None:
        raw = {
            "type": "message",
            "id": "msg_1",
            "from": {"id": "user_1", "name": "Alice"},
            "conversation": {"id": "conv_1", "isGroup": False},
            "text": "<at>Bot</at> hello",
            "serviceUrl": "https://smba.trafficmanager.net/apis",
        }
        act = BotActivity.model_validate(raw)
        assert act.type == "message"
        assert act.from_user is not None
        assert act.from_user.id == "user_1"
        assert act.conversation is not None
        assert act.conversation.id == "conv_1"
        assert act.service_url == "https://smba.trafficmanager.net/apis"

    def test_invoke_activity(self) -> None:
        raw = {
            "type": "invoke",
            "id": "inv_1",
            "from": {"id": "user_1"},
            "conversation": {"id": "conv_1"},
            "value": {"quick_reply": "yes"},
        }
        act = BotActivity.model_validate(raw)
        assert act.type == "invoke"
        assert act.value is not None
        assert act.value.get("quick_reply") == "yes"

    def test_conversation_update(self) -> None:
        raw = {
            "type": "conversationUpdate",
            "membersAdded": [{"id": "test_app_id"}],
            "recipient": {"id": "test_app_id"},
            "conversation": {"id": "conv_1", "conversationType": "personal"},
            "serviceUrl": "https://smba.trafficmanager.net/apis",
        }
        act = BotActivity.model_validate(raw)
        assert act.type == "conversationUpdate"
        assert act.members_added is not None
        assert len(act.members_added) == 1

    def test_extra_fields_allowed(self) -> None:
        act = BotActivity.model_validate({"type": "message", "unknown_field": "value"})
        assert act.type == "message"

    def test_attachments_parsed(self) -> None:
        raw = {
            "type": "message",
            "attachments": [
                {"contentType": "image/png", "contentUrl": "https://example.com/img.png", "name": "img.png"},
            ],
        }
        act = BotActivity.model_validate(raw)
        assert len(act.attachments) == 1
        assert act.attachments[0].content_type == "image/png"

    def test_entities_with_mention(self) -> None:
        raw = {
            "type": "message",
            "entities": [{"type": "mention", "mentioned": {"id": "test_app_id"}}],
        }
        act = BotActivity.model_validate(raw)
        assert len(act.entities) == 1
        assert act.entities[0].mentioned is not None


# ── Helper Function Tests ─────────────────────────────────────


class TestHelpers:
    def test_decode_html_entities(self) -> None:
        assert decode_html_entities("&lt;b&gt;hello&lt;/b&gt;") == "<b>hello</b>"
        assert decode_html_entities("&amp;&nbsp;&quot;") == '& "'
        assert decode_html_entities("&#39;&#x27;") == "''"

    def test_strip_mention_tags(self) -> None:
        assert strip_mention_tags("<at>Bot</at> hello") == "hello"
        assert strip_mention_tags("no mentions") == "no mentions"
        assert strip_mention_tags("<at id='123'>Bot</at> <at>Other</at> text") == "text"

    def test_html_to_plain(self) -> None:
        assert html_to_plain("<b>bold</b> &amp; <i>italic</i>") == "bold & italic"

    def test_encode_decode_message_key(self) -> None:
        key = encode_message_key("act_1", "https://svc.url", "conv_1")
        decoded = decode_message_key(key)
        assert decoded == ("act_1", "https://svc.url", "conv_1")

    def test_decode_message_key_invalid(self) -> None:
        assert decode_message_key("not-json") is None
        assert decode_message_key('{"aid":"a"}') is None

    def test_extract_quote_context(self) -> None:
        html_content = (
            '<blockquote itemscope itemtype="http://schema.skype.com/Reply">'
            '<strong itemprop="mri">Alice</strong>'
            '<p itemprop="copy">Hello world</p>'
            "</blockquote>"
        )
        result = extract_quote_context([{"contentType": "text/html", "content": html_content}])
        assert result is not None
        assert result["quote_sender"] == "Alice"
        assert result["quote_body"] == "Hello world"

    def test_extract_quote_context_no_match(self) -> None:
        assert extract_quote_context([{"contentType": "text/html", "content": "no reply"}]) is None
        assert extract_quote_context([]) is None

    def test_build_adaptive_card_with_buttons(self) -> None:
        btn = ActionButton(label="Click", action_id="btn_1", style=ButtonStyle.PRIMARY)
        qr = QuickReply(label="Yes", text="yes")
        result = build_adaptive_card_activity(
            components=((btn,),),
            quick_replies=(qr,),
            text="Choose:",
        )
        assert result["type"] == "message"
        attachments = result["attachments"]
        assert len(attachments) == 1
        card = attachments[0]["content"]
        assert card["type"] == "AdaptiveCard"
        assert len(card["actions"]) == 2
        assert card["actions"][0]["style"] == "positive"
        assert card["actions"][1]["data"]["quick_reply"] == "yes"

    def test_build_adaptive_card_url_button(self) -> None:
        btn = ActionButton(label="Open", action_id="open_1", url="https://example.com")
        result = build_adaptive_card_activity(components=((btn,),), quick_replies=(), text="")
        card = result["attachments"][0]["content"]
        assert card["actions"][0]["type"] == "Action.OpenUrl"
        assert card["actions"][0]["url"] == "https://example.com"

    def test_build_adaptive_card_danger_button(self) -> None:
        btn = ActionButton(label="Delete", action_id="del_1", style=ButtonStyle.DANGER)
        result = build_adaptive_card_activity(components=((btn,),), quick_replies=(), text="")
        card = result["attachments"][0]["content"]
        assert card["actions"][0]["style"] == "destructive"


# ── Inbound Activity Tests ────────────────────────────────────


class TestHandleActivity:
    @staticmethod
    def _setup_handler(ch: MSTeamsChannel) -> list[object]:
        received: list[object] = []

        async def handler(msg: object) -> None:
            received.append(msg)

        ch.set_inbound_handler(handler)
        ch._status = "running"
        return received

    @pytest.mark.asyncio
    async def test_message_activity_emits_inbound(self) -> None:
        ch = _make_channel()
        received = self._setup_handler(ch)

        raw = {
            "type": "message",
            "id": "msg_1",
            "from": {"id": "user_1", "name": "Alice"},
            "conversation": {"id": "conv_1", "isGroup": False},
            "text": "hello world",
            "serviceUrl": "https://smba.trafficmanager.net/apis",
        }
        await ch.handle_activity(raw)
        assert len(received) == 1
        assert received[0].content == "hello world"
        assert received[0].sender_id == "user_1"

    @pytest.mark.asyncio
    async def test_self_message_filtered(self) -> None:
        ch = _make_channel()
        received = self._setup_handler(ch)

        raw = {
            "type": "message",
            "from": {"id": "test_app_id", "name": "Bot"},
            "conversation": {"id": "conv_1"},
            "text": "echo",
            "serviceUrl": "https://smba.trafficmanager.net/apis",
        }
        await ch.handle_activity(raw)
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_empty_text_no_media_filtered(self) -> None:
        ch = _make_channel()
        received = self._setup_handler(ch)

        raw = {
            "type": "message",
            "from": {"id": "user_1"},
            "conversation": {"id": "conv_1"},
            "text": "   ",
            "serviceUrl": "https://smba.trafficmanager.net/apis",
        }
        await ch.handle_activity(raw)
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_mention_detection(self) -> None:
        ch = _make_channel()
        received = self._setup_handler(ch)

        raw = {
            "type": "message",
            "from": {"id": "user_1"},
            "conversation": {"id": "conv_1", "isGroup": True},
            "text": "<at>Bot</at> hello",
            "serviceUrl": "https://smba.trafficmanager.net/apis",
            "entities": [{"type": "mention", "mentioned": {"id": "test_app_id"}}],
        }
        await ch.handle_activity(raw)
        assert len(received) == 1
        assert received[0].mentioned is True

    @pytest.mark.asyncio
    async def test_attachment_image(self) -> None:
        ch = _make_channel()
        received = self._setup_handler(ch)

        raw = {
            "type": "message",
            "from": {"id": "user_1"},
            "conversation": {"id": "conv_1"},
            "text": "",
            "serviceUrl": "https://smba.trafficmanager.net/apis",
            "attachments": [
                {"contentType": "image/png", "contentUrl": "https://example.com/img.png", "name": "img.png"},
            ],
        }
        await ch.handle_activity(raw)
        assert len(received) == 1
        assert len(received[0].media) == 1
        assert received[0].media[0].media_type == MediaType.IMAGE

    @pytest.mark.asyncio
    async def test_attachment_audio(self) -> None:
        ch = _make_channel()
        received = self._setup_handler(ch)

        raw = {
            "type": "message",
            "from": {"id": "user_1"},
            "conversation": {"id": "conv_1"},
            "text": "",
            "serviceUrl": "https://smba.trafficmanager.net/apis",
            "attachments": [
                {"contentType": "audio/mp3", "contentUrl": "https://example.com/a.mp3", "name": "a.mp3"},
            ],
        }
        await ch.handle_activity(raw)
        assert received[0].media[0].media_type == MediaType.AUDIO

    @pytest.mark.asyncio
    async def test_attachment_video(self) -> None:
        ch = _make_channel()
        received = self._setup_handler(ch)

        raw = {
            "type": "message",
            "from": {"id": "user_1"},
            "conversation": {"id": "conv_1"},
            "text": "",
            "serviceUrl": "https://smba.trafficmanager.net/apis",
            "attachments": [
                {"contentType": "video/mp4", "contentUrl": "https://example.com/v.mp4", "name": "v.mp4"},
            ],
        }
        await ch.handle_activity(raw)
        assert received[0].media[0].media_type == MediaType.VIDEO

    @pytest.mark.asyncio
    async def test_attachment_document(self) -> None:
        ch = _make_channel()
        received = self._setup_handler(ch)

        raw = {
            "type": "message",
            "from": {"id": "user_1"},
            "conversation": {"id": "conv_1"},
            "text": "",
            "serviceUrl": "https://smba.trafficmanager.net/apis",
            "attachments": [
                {"contentType": "application/pdf", "contentUrl": "https://example.com/d.pdf", "name": "d.pdf"},
            ],
        }
        await ch.handle_activity(raw)
        assert received[0].media[0].media_type == MediaType.DOCUMENT

    @pytest.mark.asyncio
    async def test_card_attachment_skipped(self) -> None:
        ch = _make_channel()
        received = self._setup_handler(ch)

        raw = {
            "type": "message",
            "from": {"id": "user_1"},
            "conversation": {"id": "conv_1"},
            "text": "with card",
            "serviceUrl": "https://smba.trafficmanager.net/apis",
            "attachments": [
                {"contentType": "application/vnd.microsoft.card.adaptive", "content": {}},
            ],
        }
        await ch.handle_activity(raw)
        assert len(received) == 1
        assert len(received[0].media) == 0

    @pytest.mark.asyncio
    async def test_invoke_quick_reply(self) -> None:
        ch = _make_channel()
        received = self._setup_handler(ch)

        raw = {
            "type": "invoke",
            "from": {"id": "user_1"},
            "conversation": {"id": "conv_1"},
            "value": {"quick_reply": "yes"},
            "serviceUrl": "https://smba.trafficmanager.net/apis",
        }
        await ch.handle_activity(raw)
        assert len(received) == 1
        assert received[0].content == "yes"

    @pytest.mark.asyncio
    async def test_invoke_action_id(self) -> None:
        ch = _make_channel()
        received = self._setup_handler(ch)

        raw = {
            "type": "invoke",
            "from": {"id": "user_1"},
            "conversation": {"id": "conv_1"},
            "value": {"action_id": "approve"},
            "serviceUrl": "https://smba.trafficmanager.net/apis",
        }
        await ch.handle_activity(raw)
        assert len(received) == 1
        assert received[0].content == "approve"

    @pytest.mark.asyncio
    async def test_invoke_no_value_ignored(self) -> None:
        ch = _make_channel()
        received = self._setup_handler(ch)

        raw = {
            "type": "invoke",
            "from": {"id": "user_1"},
            "conversation": {"id": "conv_1"},
            "serviceUrl": "https://smba.trafficmanager.net/apis",
        }
        await ch.handle_activity(raw)
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_invalid_payload_skipped(self) -> None:
        ch = _make_channel()
        received = self._setup_handler(ch)
        await ch.handle_activity({})
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_service_url_cached(self) -> None:
        ch = _make_channel()
        raw = {
            "type": "message",
            "from": {"id": "user_1"},
            "conversation": {"id": "conv_cache"},
            "text": "hello",
            "serviceUrl": "https://smba.trafficmanager.net/apis",
        }
        await ch.handle_activity(raw)
        cached = ch._api._service_url_cache.get("conv_cache")
        assert cached is not None
        assert cached[0] == "https://smba.trafficmanager.net/apis"

    @pytest.mark.asyncio
    async def test_reply_to_id_parsed(self) -> None:
        ch = _make_channel()
        received = self._setup_handler(ch)

        raw = {
            "type": "message",
            "from": {"id": "user_1"},
            "conversation": {"id": "conv_1"},
            "text": "reply",
            "replyToId": "original_msg_id",
            "serviceUrl": "https://smba.trafficmanager.net/apis",
        }
        await ch.handle_activity(raw)
        assert len(received) == 1
        assert received[0].reply_to_id == "original_msg_id"

    @pytest.mark.asyncio
    async def test_conversation_update_welcome(self) -> None:
        ch = _make_channel(welcome_text="Welcome!", prompt_starters=["Help", "Start"])
        _set_valid_token(ch)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": "act_w"}
        mock_http = _mock_http_on_channel(ch)
        mock_http.post = AsyncMock(return_value=mock_resp)

        raw = {
            "type": "conversationUpdate",
            "membersAdded": [{"id": "test_app_id"}],
            "recipient": {"id": "test_app_id"},
            "conversation": {"id": "conv_w", "conversationType": "personal"},
            "serviceUrl": "https://smba.trafficmanager.net/apis",
        }
        await ch.handle_activity(raw)
        mock_http.post.assert_called_once()
        call_json = mock_http.post.call_args.kwargs.get("json", mock_http.post.call_args[1].get("json"))
        assert call_json is not None
        assert "attachments" in call_json

    @pytest.mark.asyncio
    async def test_conversation_update_no_welcome_config(self) -> None:
        ch = _make_channel()
        mock_http = _mock_http_on_channel(ch)
        mock_http.post = AsyncMock()

        raw = {
            "type": "conversationUpdate",
            "membersAdded": [{"id": "test_app_id"}],
            "recipient": {"id": "test_app_id"},
            "conversation": {"id": "conv_w"},
            "serviceUrl": "https://smba.trafficmanager.net/apis",
        }
        await ch.handle_activity(raw)
        mock_http.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_conversation_update_group_welcome_text(self) -> None:
        ch = _make_channel(welcome_text="Hi group!")
        _set_valid_token(ch)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": "act_g"}
        mock_http = _mock_http_on_channel(ch)
        mock_http.post = AsyncMock(return_value=mock_resp)

        raw = {
            "type": "conversationUpdate",
            "membersAdded": [{"id": "test_app_id"}],
            "recipient": {"id": "test_app_id"},
            "conversation": {"id": "conv_g", "conversationType": "groupChat"},
            "serviceUrl": "https://smba.trafficmanager.net/apis",
        }
        await ch.handle_activity(raw)
        mock_http.post.assert_called_once()
        call_json = mock_http.post.call_args.kwargs.get("json", mock_http.post.call_args[1].get("json"))
        assert call_json.get("text") == "Hi group!"


# ── Outbound Tests ────────────────────────────────────────────


class TestOutbound:
    @pytest.mark.asyncio
    async def test_send_text_message(self) -> None:
        ch = _make_channel()
        _set_valid_token(ch)
        _seed_service_url(ch, "conv_out")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": "act_out"}
        mock_http = _mock_http_on_channel(ch)
        mock_http.post = AsyncMock(return_value=mock_resp)

        msg = _make_outbound("conv_out", "Hello!")
        result = await ch.send(msg)
        assert result is not None
        mock_http.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_with_media(self) -> None:
        ch = _make_channel()
        _set_valid_token(ch)
        _seed_service_url(ch, "conv_media")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": "act_m"}
        mock_http = _mock_http_on_channel(ch)
        mock_http.post = AsyncMock(return_value=mock_resp)

        media = MediaAttachment(media_type=MediaType.IMAGE, url="https://example.com/img.png", mime_type="image/png")
        msg = _make_outbound("conv_media", "", media=(media,))
        await ch.send(msg)
        assert mock_http.post.call_count >= 1

    @pytest.mark.asyncio
    async def test_send_empty_content_no_components_returns_none(self) -> None:
        ch = _make_channel()
        _set_valid_token(ch)
        _seed_service_url(ch, "conv_empty")

        mock_http = _mock_http_on_channel(ch)
        mock_http.post = AsyncMock()

        msg = _make_outbound("conv_empty", "")
        result = await ch.send(msg)
        assert result is None

    @pytest.mark.asyncio
    async def test_edit_message(self) -> None:
        ch = _make_channel()
        _set_valid_token(ch)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_http = _mock_http_on_channel(ch)
        mock_http.put = AsyncMock(return_value=mock_resp)

        key = encode_message_key("act_1", "https://svc.url", "conv_1")
        await ch.edit_message("conv_1", key, "updated text")
        mock_http.put.assert_called_once()

    @pytest.mark.asyncio
    async def test_edit_message_plain_id_with_cache(self) -> None:
        ch = _make_channel()
        _set_valid_token(ch)
        _seed_service_url(ch, "conv_e")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_http = _mock_http_on_channel(ch)
        mock_http.put = AsyncMock(return_value=mock_resp)

        await ch.edit_message("conv_e", "plain_act_id", "updated")
        mock_http.put.assert_called_once()

    @pytest.mark.asyncio
    async def test_edit_message_no_service_url(self) -> None:
        ch = _make_channel()
        _set_valid_token(ch)
        mock_http = _mock_http_on_channel(ch)
        mock_http.put = AsyncMock()

        await ch.edit_message("unknown_conv", "act_id", "text")
        mock_http.put.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_message(self) -> None:
        ch = _make_channel()
        _set_valid_token(ch)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_http = _mock_http_on_channel(ch)
        mock_http.delete = AsyncMock(return_value=mock_resp)

        key = encode_message_key("act_d", "https://svc.url", "conv_d")
        await ch.delete_message("conv_d", key)
        mock_http.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_message_no_service_url(self) -> None:
        ch = _make_channel()
        _set_valid_token(ch)
        mock_http = _mock_http_on_channel(ch)
        mock_http.delete = AsyncMock()

        await ch.delete_message("unknown", "act_id")
        mock_http.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_placeholder(self) -> None:
        ch = _make_channel()
        _set_valid_token(ch)
        _seed_service_url(ch, "conv_ph")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": "act_ph"}
        mock_http = _mock_http_on_channel(ch)
        mock_http.post = AsyncMock(return_value=mock_resp)

        result = await ch.send_placeholder("conv_ph", "Thinking...")
        assert result is not None

    @pytest.mark.asyncio
    async def test_send_placeholder_no_service_url(self) -> None:
        ch = _make_channel()
        result = await ch.send_placeholder("unknown", "text")
        assert result is None

    @pytest.mark.asyncio
    async def test_start_typing(self) -> None:
        ch = _make_channel()
        _set_valid_token(ch)
        _seed_service_url(ch, "conv_t")

        mock_http = _mock_http_on_channel(ch)
        mock_http.post = AsyncMock()

        await ch.start_typing("conv_t")
        mock_http.post.assert_called_once()
        call_json = mock_http.post.call_args.kwargs.get("json", mock_http.post.call_args[1].get("json"))
        assert call_json["type"] == "typing"

    @pytest.mark.asyncio
    async def test_start_typing_no_service_url(self) -> None:
        ch = _make_channel()
        mock_http = _mock_http_on_channel(ch)
        mock_http.post = AsyncMock()
        await ch.start_typing("unknown")
        mock_http.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_react_to_message(self) -> None:
        ch = _make_channel()
        _set_valid_token(ch)

        mock_http = _mock_http_on_channel(ch)
        mock_http.post = AsyncMock()

        key = encode_message_key("act_r", "https://svc.url", "conv_r")
        await ch.react_to_message("conv_r", key, "\U0001F44D")
        mock_http.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_react_empty_emoji(self) -> None:
        ch = _make_channel()
        mock_http = _mock_http_on_channel(ch)
        mock_http.post = AsyncMock()
        await ch.react_to_message("conv", "mid", "")
        mock_http.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_post_activity_failure(self) -> None:
        ch = _make_channel()
        _set_valid_token(ch)

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_http = _mock_http_on_channel(ch)
        mock_http.post = AsyncMock(return_value=mock_resp)

        result = await ch._api.post_activity("https://svc.url", "conv_1", {"type": "message", "text": "hi"})
        assert result is None

    @pytest.mark.asyncio
    async def test_post_activity_no_service_url(self) -> None:
        ch = _make_channel()
        result = await ch._api.post_activity("", "conv_1", {"type": "message"})
        assert result is None

    @pytest.mark.asyncio
    async def test_post_activity_non_json_response(self) -> None:
        ch = _make_channel()
        _set_valid_token(ch)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.side_effect = ValueError("not json")
        mock_http = _mock_http_on_channel(ch)
        mock_http.post = AsyncMock(return_value=mock_resp)

        result = await ch._api.post_activity("https://svc.url", "conv_1", {"type": "message"})
        assert result is None

    @pytest.mark.asyncio
    async def test_send_attachment_no_url(self) -> None:
        ch = _make_channel()
        media = MediaAttachment(media_type=MediaType.IMAGE, url="", mime_type="image/png")
        result = await ch._api.send_attachment("https://svc.url", "conv_1", media)
        assert result is None

    @pytest.mark.asyncio
    async def test_send_attachment_with_caption(self) -> None:
        ch = _make_channel()
        _set_valid_token(ch)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": "att_1"}
        mock_http = _mock_http_on_channel(ch)
        mock_http.post = AsyncMock(return_value=mock_resp)

        media = MediaAttachment(
            media_type=MediaType.IMAGE,
            url="https://example.com/img.png",
            mime_type="image/png",
            caption="Look at this",
        )
        result = await ch._api.send_attachment("https://svc.url", "conv_1", media)
        assert result is not None
        call_json = mock_http.post.call_args.kwargs.get("json", mock_http.post.call_args[1].get("json"))
        assert call_json.get("text") == "Look at this"

    @pytest.mark.asyncio
    async def test_edit_placeholder_message(self) -> None:
        ch = _make_channel()
        _set_valid_token(ch)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_http = _mock_http_on_channel(ch)
        mock_http.put = AsyncMock(return_value=mock_resp)

        key = encode_message_key("act_ep", "https://svc.url", "conv_ep")
        msg = _make_outbound("conv_ep", "Final answer")
        await ch.edit_placeholder_message("conv_ep", key, msg)
        mock_http.put.assert_called_once()


# ── Lifecycle Tests ───────────────────────────────────────────


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_start_success(self) -> None:
        ch = _make_channel()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"access_token": "tok123", "expires_in": 3600}
        mock_http = _mock_http_on_channel(ch)
        mock_http.post = AsyncMock(return_value=mock_resp)

        await ch.start()
        assert ch._status == ChannelStatus.RUNNING
        assert ch._api._access_token == "tok123"

    @pytest.mark.asyncio
    async def test_start_no_credentials(self) -> None:
        ch = MSTeamsChannel(app_id="", app_password="")
        await ch.start()
        assert ch._status != ChannelStatus.RUNNING

    @pytest.mark.asyncio
    async def test_start_token_failure(self) -> None:
        ch = _make_channel()
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_http = _mock_http_on_channel(ch)
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.aclose = AsyncMock()

        await ch.start()
        assert ch._status == ChannelStatus.ERROR

    @pytest.mark.asyncio
    async def test_stop(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.RUNNING
        ch._api._service_url_cache["conv"] = ("url", time.monotonic())
        mock_http = _mock_http_on_channel(ch)
        mock_http.aclose = AsyncMock()

        await ch.stop()
        assert ch._status == ChannelStatus.STOPPED
        assert len(ch._api._service_url_cache) == 0

    @pytest.mark.asyncio
    async def test_health_check_running(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.RUNNING
        _set_valid_token(ch)
        assert await ch.health_check() is True

    @pytest.mark.asyncio
    async def test_health_check_stopped(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.STOPPED
        assert await ch.health_check() is False

    @pytest.mark.asyncio
    async def test_health_check_token_refresh_fails(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.RUNNING
        ch._api._token_expires_at = 0
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_http = _mock_http_on_channel(ch)
        mock_http.post = AsyncMock(return_value=mock_resp)
        assert await ch.health_check() is False

    def test_collect_issues_no_app_id(self) -> None:
        ch = MSTeamsChannel(app_id="", app_password="pw")
        issues = ch.collect_issues()
        assert any("App ID" in i.message for i in issues)

    def test_collect_issues_no_password(self) -> None:
        ch = MSTeamsChannel(app_id="id", app_password="")
        issues = ch.collect_issues()
        assert any("password" in i.message for i in issues)

    def test_collect_issues_error_status(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.ERROR
        issues = ch.collect_issues()
        assert any("OAuth" in i.message for i in issues)


# ── Service URL Cache Tests ───────────────────────────────────


class TestServiceUrlCache:
    def test_cache_and_resolve(self) -> None:
        ch = _make_channel()
        ch._api.cache_service_url("conv_1", "https://svc.url")
        assert ch._api.resolve_service_url("conv_1") == "https://svc.url"

    def test_resolve_missing(self) -> None:
        ch = _make_channel()
        assert ch._api.resolve_service_url("unknown") == ""

    def test_cache_eviction(self) -> None:
        ch = _make_channel()
        for i in range(510):
            ch._api.cache_service_url(f"conv_{i}", f"https://svc{i}.url")
        assert len(ch._api._service_url_cache) <= 500

    def test_resolve_expired(self) -> None:
        ch = _make_channel()
        ch._api._service_url_cache["conv_old"] = ("https://old.url", time.monotonic() - 100000)
        assert ch._api.resolve_service_url("conv_old") == ""


# ── Token Management Tests ────────────────────────────────────


class TestTokenManagement:
    @pytest.mark.asyncio
    async def test_refresh_token_success(self) -> None:
        ch = _make_channel()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"access_token": "new_tok", "expires_in": 7200}
        mock_http = _mock_http_on_channel(ch)
        mock_http.post = AsyncMock(return_value=mock_resp)

        await ch._api.refresh_token()
        assert ch._api._access_token == "new_tok"
        assert ch._api._token_expires_at > time.monotonic()

    @pytest.mark.asyncio
    async def test_refresh_token_failure(self) -> None:
        ch = _make_channel()
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_http = _mock_http_on_channel(ch)
        mock_http.post = AsyncMock(return_value=mock_resp)

        with pytest.raises(ChannelAuthError):
            await ch._api.refresh_token()

    @pytest.mark.asyncio
    async def test_ensure_token_skips_when_valid(self) -> None:
        ch = _make_channel()
        _set_valid_token(ch)
        mock_http = _mock_http_on_channel(ch)
        mock_http.post = AsyncMock()

        await ch._api.ensure_token()
        mock_http.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_ensure_token_refreshes_when_expired(self) -> None:
        ch = _make_channel()
        ch._api._token_expires_at = 0
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"access_token": "refreshed", "expires_in": 3600}
        mock_http = _mock_http_on_channel(ch)
        mock_http.post = AsyncMock(return_value=mock_resp)

        await ch._api.ensure_token()
        assert ch._api._access_token == "refreshed"


# ---------------------------------------------------------------------------
# BotFrameworkJwtVerifier tests
# ---------------------------------------------------------------------------

from app.channels.providers.msteams.auth import (  # noqa: E402
    BotFrameworkJwtVerifier,
)


class TestBotFrameworkJwtVerifier:
    @pytest.mark.asyncio
    async def test_no_app_id_allows_all(self) -> None:
        http = AsyncMock(spec=httpx.AsyncClient)
        verifier = BotFrameworkJwtVerifier("", http)
        result = await verifier.verify("Bearer fake", {})
        assert result is True

    @pytest.mark.asyncio
    async def test_missing_auth_header(self) -> None:
        http = AsyncMock(spec=httpx.AsyncClient)
        verifier = BotFrameworkJwtVerifier("app123", http)
        assert await verifier.verify("", {}) is False

    @pytest.mark.asyncio
    async def test_invalid_auth_header(self) -> None:
        http = AsyncMock(spec=httpx.AsyncClient)
        verifier = BotFrameworkJwtVerifier("app123", http)
        assert await verifier.verify("Basic abc", {}) is False

    @pytest.mark.asyncio
    async def test_get_jwks_url_cached(self) -> None:
        http = AsyncMock(spec=httpx.AsyncClient)
        verifier = BotFrameworkJwtVerifier("app123", http)
        verifier._jwks_url_cache = "https://cached.url/jwks"
        verifier._jwks_fetched_at = float("inf")
        url = await verifier._get_jwks_url()
        assert url == "https://cached.url/jwks"
        http.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_jwks_url_fetch_success(self) -> None:
        http = AsyncMock(spec=httpx.AsyncClient)
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"jwks_uri": "https://login.botframework.com/jwks"}
        http.get.return_value = resp

        verifier = BotFrameworkJwtVerifier("app123", http)
        url = await verifier._get_jwks_url()
        assert url == "https://login.botframework.com/jwks"

    @pytest.mark.asyncio
    async def test_get_jwks_url_fetch_failure(self) -> None:
        http = AsyncMock(spec=httpx.AsyncClient)
        resp = MagicMock()
        resp.status_code = 500
        http.get.return_value = resp

        verifier = BotFrameworkJwtVerifier("app123", http)
        url = await verifier._get_jwks_url()
        assert url == ""

    @pytest.mark.asyncio
    async def test_get_jwks_url_fetch_exception(self) -> None:
        http = AsyncMock(spec=httpx.AsyncClient)
        http.get.side_effect = RuntimeError("network error")

        verifier = BotFrameworkJwtVerifier("app123", http)
        url = await verifier._get_jwks_url()
        assert url == ""
