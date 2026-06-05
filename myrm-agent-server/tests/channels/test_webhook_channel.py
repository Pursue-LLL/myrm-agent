"""WebhookChannel tests — contract compliance, send, payload, lifecycle."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.core.base import BaseChannel
from app.channels.core.exceptions import ChannelSendError
from app.channels.providers.webhook import WebhookChannel
from app.channels.types import (
    MediaAttachment,
    MediaType,
    OutboundMessage,
)

from .channel_test_base import ChannelTestBase


class TestWebhookChannel(ChannelTestBase):
    def create_channel(self) -> BaseChannel:
        return WebhookChannel()


class TestWebhookSend:
    @pytest.mark.asyncio
    async def test_send_success(self) -> None:
        ch = WebhookChannel()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": "msg-1"}
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        ch._client = mock_client

        msg = OutboundMessage(channel="webhook", recipient_id="https://example.com/hook", content="Hello", user_id="u1")
        result = await ch.send(msg)
        assert result == "msg-1"
        mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_no_url(self) -> None:
        ch = WebhookChannel()
        msg = OutboundMessage(channel="webhook", recipient_id="", content="Hello", user_id="u1")
        result = await ch.send(msg)
        assert result is None

    @pytest.mark.asyncio
    async def test_send_http_error(self) -> None:
        ch = WebhookChannel()
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        ch._client = mock_client

        msg = OutboundMessage(channel="webhook", recipient_id="https://example.com/hook", content="Hello", user_id="u1")
        with pytest.raises(ChannelSendError) as exc_info:
            await ch.send(msg)
        assert exc_info.value.retriable is True

    @pytest.mark.asyncio
    async def test_send_client_error(self) -> None:
        ch = WebhookChannel()
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        ch._client = mock_client

        msg = OutboundMessage(channel="webhook", recipient_id="https://example.com/hook", content="Hello", user_id="u1")
        with pytest.raises(ChannelSendError) as exc_info:
            await ch.send(msg)
        assert exc_info.value.retriable is False

    @pytest.mark.asyncio
    async def test_send_network_error(self) -> None:
        ch = WebhookChannel()
        mock_client = MagicMock()
        mock_client.post = AsyncMock(side_effect=ConnectionError("refused"))
        ch._client = mock_client

        msg = OutboundMessage(channel="webhook", recipient_id="https://example.com/hook", content="Hello", user_id="u1")
        with pytest.raises(ChannelSendError):
            await ch.send(msg)


class TestWebhookPayload:
    def test_basic_payload(self) -> None:
        ch = WebhookChannel()
        msg = OutboundMessage(channel="webhook", recipient_id="https://example.com", content="Hello", user_id="u1")
        payload = ch._build_payload(msg)
        assert payload["content"] == "Hello"
        assert "timestamp" in payload

    def test_payload_with_media(self) -> None:
        ch = WebhookChannel()
        media = MediaAttachment(media_type=MediaType.IMAGE, url="https://img.png", filename="img.png", caption="Photo")
        msg = OutboundMessage(channel="webhook", recipient_id="https://example.com", content="", user_id="u1", media=(media,))
        payload = ch._build_payload(msg)
        assert "media" in payload
        assert len(payload["media"]) == 1  # type: ignore[arg-type]

    def test_payload_with_reply_to(self) -> None:
        ch = WebhookChannel()
        msg = OutboundMessage(
            channel="webhook", recipient_id="https://example.com", content="Reply", user_id="u1", reply_to_id="orig-1"
        )
        payload = ch._build_payload(msg)
        assert payload["reply_to_id"] == "orig-1"

    def test_payload_with_metadata_sources(self) -> None:
        ch = WebhookChannel()
        msg = OutboundMessage(
            channel="webhook",
            recipient_id="https://example.com",
            content="Hi",
            user_id="u1",
            metadata={"sources": [{"url": "https://src.com"}], "progressSteps": ["step1"]},
        )
        payload = ch._build_payload(msg)
        assert payload["sources"] == [{"url": "https://src.com"}]
        assert payload["steps"] == ["step1"]


class TestWebhookExtractMessageId:
    def test_extract_id(self) -> None:
        resp = MagicMock()
        resp.json.return_value = {"id": "abc-123"}
        assert WebhookChannel._extract_message_id(resp) == "abc-123"

    def test_extract_message_id(self) -> None:
        resp = MagicMock()
        resp.json.return_value = {"message_id": 42}
        assert WebhookChannel._extract_message_id(resp) == "42"

    def test_extract_message_id_camel_case(self) -> None:
        resp = MagicMock()
        resp.json.return_value = {"messageId": "x"}
        assert WebhookChannel._extract_message_id(resp) == "x"

    def test_no_id_in_response(self) -> None:
        resp = MagicMock()
        resp.json.return_value = {"status": "ok"}
        assert WebhookChannel._extract_message_id(resp) is None

    def test_invalid_json(self) -> None:
        resp = MagicMock()
        resp.json.side_effect = json.JSONDecodeError("err", "", 0)
        assert WebhookChannel._extract_message_id(resp) is None

    def test_non_dict_response(self) -> None:
        resp = MagicMock()
        resp.json.return_value = "just a string"
        assert WebhookChannel._extract_message_id(resp) is None


class TestWebhookLifecycle:
    @pytest.mark.asyncio
    async def test_stop_closes_client(self) -> None:
        ch = WebhookChannel()
        mock_client = MagicMock()
        mock_client.aclose = AsyncMock()
        ch._client = mock_client
        await ch.stop()
        mock_client.aclose.assert_called_once()
        assert ch._client is None

    @pytest.mark.asyncio
    async def test_stop_no_client(self) -> None:
        ch = WebhookChannel()
        await ch.stop()

    def test_lazy_client_creation(self) -> None:
        ch = WebhookChannel()
        assert ch._client is None
        client = ch._get_client()
        assert client is not None
        assert ch._client is client
