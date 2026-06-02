"""GoogleChatChannel tests — contract compliance + webhook parsing + health + send errors."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.channels.core.base import BaseChannel
from app.channels.core.exceptions import ChannelSendError
from app.channels.providers.googlechat import GoogleChatChannel
from app.channels.types import ChannelStatus, OutboundMessage

from .channel_test_base import ChannelTestBase


class TestGoogleChatChannelBase(ChannelTestBase):
    def create_channel(self) -> BaseChannel:
        return GoogleChatChannel(service_account_json="")


class TestGoogleChatWebhook:
    """Inbound webhook event parsing."""

    def _make_channel(self) -> tuple[GoogleChatChannel, list[object]]:
        ch = GoogleChatChannel(service_account_json="")
        received: list[object] = []

        async def _handler(msg: object) -> None:
            received.append(msg)

        ch.set_inbound_handler(_handler)
        return ch, received

    @pytest.mark.asyncio
    async def test_message_event_parsed(self) -> None:
        ch, received = self._make_channel()

        event = {
            "type": "MESSAGE",
            "message": {
                "name": "spaces/AAA/messages/BBB",
                "text": "hello bot",
                "argumentText": "hello bot",
                "thread": {"name": "spaces/AAA/threads/CCC"},
            },
            "space": {"name": "spaces/AAA", "type": "ROOM"},
            "user": {"name": "users/123", "displayName": "Alice"},
        }

        await ch.handle_webhook(event)
        assert len(received) == 1
        msg = received[0]
        assert msg.content == "hello bot"
        assert msg.sender_id == "users/123"
        assert msg.chat_id == "spaces/AAA"
        assert msg.is_group is True
        assert msg.thread_id == "spaces/AAA/threads/CCC"
        assert msg.message_id == "spaces/AAA/messages/BBB"

    @pytest.mark.asyncio
    async def test_non_message_event_ignored(self) -> None:
        ch, received = self._make_channel()
        await ch.handle_webhook({"type": "ADDED_TO_SPACE", "space": {}, "user": {}})
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_empty_text_ignored(self) -> None:
        ch, received = self._make_channel()

        event = {
            "type": "MESSAGE",
            "message": {"name": "m1", "text": "", "argumentText": ""},
            "space": {"name": "spaces/AAA", "type": "DM"},
            "user": {"name": "users/123", "displayName": "Alice"},
        }
        await ch.handle_webhook(event)
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_dm_detected(self) -> None:
        ch, received = self._make_channel()

        event = {
            "type": "MESSAGE",
            "message": {"name": "m1", "text": "hi"},
            "space": {"name": "spaces/DM1", "type": "DM"},
            "user": {"name": "users/1", "displayName": "Bob"},
        }
        await ch.handle_webhook(event)
        assert len(received) == 1
        assert received[0].is_group is False

    @pytest.mark.asyncio
    async def test_invalid_message_structure(self) -> None:
        ch, received = self._make_channel()

        await ch.handle_webhook({"type": "MESSAGE", "message": "not-a-dict"})
        assert len(received) == 0

        await ch.handle_webhook({"type": "MESSAGE", "message": {}, "space": "bad"})
        assert len(received) == 0


class TestGoogleChatHealth:
    """Health check and collect_issues."""

    def test_collect_issues_unconfigured(self) -> None:
        ch = GoogleChatChannel(service_account_json="")
        issues = ch.collect_issues()
        assert len(issues) == 1
        assert issues[0].kind.value == "config"
        assert "Service Account" in issues[0].message

    def test_collect_issues_no_issues_when_healthy(self) -> None:
        ch = GoogleChatChannel(service_account_json="")
        ch._api._client_email = "test@proj.iam.gserviceaccount.com"
        ch._api._private_key = object()  # type: ignore[assignment]
        assert ch.collect_issues() == []

    def test_collect_issues_runtime_error(self) -> None:
        ch = GoogleChatChannel(service_account_json="")
        ch._api._client_email = "test@proj.iam.gserviceaccount.com"
        ch._api._private_key = object()  # type: ignore[assignment]
        ch.health.record_failure("Token expired")
        issues = ch.collect_issues()
        assert len(issues) == 1
        assert issues[0].kind.value == "runtime"
        assert "Token expired" in issues[0].message


class TestGoogleChatSend:
    """Outbound send edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_send_no_recipient(self) -> None:
        ch = GoogleChatChannel(service_account_json="")
        msg = OutboundMessage(channel="googlechat", user_id="u1", recipient_id="", content="hi")
        result = await ch.send(msg)
        assert result is None

    @pytest.mark.asyncio
    async def test_send_no_content(self) -> None:
        ch = GoogleChatChannel(service_account_json="")
        msg = OutboundMessage(channel="googlechat", user_id="u1", recipient_id="spaces/AAA", content="")
        result = await ch.send(msg)
        assert result is None

    @pytest.mark.asyncio
    async def test_send_success_records_health(self) -> None:
        ch = GoogleChatChannel(service_account_json="")
        mock_result = {"name": "spaces/AAA/messages/111"}
        with patch.object(ch._api, "send_message", new_callable=AsyncMock, return_value=mock_result):
            msg = OutboundMessage(channel="googlechat", user_id="u1", recipient_id="spaces/AAA", content="hello")
            result = await ch.send(msg)

        assert result == "spaces/AAA/messages/111"
        assert not ch.health.last_error

    @pytest.mark.asyncio
    async def test_send_http_error_raises_channel_send_error(self) -> None:
        ch = GoogleChatChannel(service_account_json="")
        mock_resp = httpx.Response(status_code=500, request=httpx.Request("POST", "https://x"))
        exc = httpx.HTTPStatusError("Server Error", request=mock_resp.request, response=mock_resp)

        with patch.object(ch._api, "send_message", new_callable=AsyncMock, side_effect=exc):
            msg = OutboundMessage(channel="googlechat", user_id="u1", recipient_id="spaces/AAA", content="hello")
            with pytest.raises(ChannelSendError) as exc_info:
                await ch.send(msg)

        assert exc_info.value.status_code == 500
        assert exc_info.value.retriable is True
        assert ch.health.last_error == "HTTP 500"

    @pytest.mark.asyncio
    async def test_send_generic_error_raises_channel_send_error(self) -> None:
        ch = GoogleChatChannel(service_account_json="")
        with patch.object(ch._api, "send_message", new_callable=AsyncMock, side_effect=RuntimeError("network")):
            msg = OutboundMessage(channel="googlechat", user_id="u1", recipient_id="spaces/AAA", content="hello")
            with pytest.raises(ChannelSendError):
                await ch.send(msg)

        assert ch.health.last_error == "network"

    @pytest.mark.asyncio
    async def test_send_4xx_not_retriable(self) -> None:
        ch = GoogleChatChannel(service_account_json="")
        mock_resp = httpx.Response(status_code=403, request=httpx.Request("POST", "https://x"))
        exc = httpx.HTTPStatusError("Forbidden", request=mock_resp.request, response=mock_resp)

        with patch.object(ch._api, "send_message", new_callable=AsyncMock, side_effect=exc):
            msg = OutboundMessage(channel="googlechat", user_id="u1", recipient_id="spaces/AAA", content="hello")
            with pytest.raises(ChannelSendError) as exc_info:
                await ch.send(msg)

        assert exc_info.value.status_code == 403
        assert exc_info.value.retriable is False

    @pytest.mark.asyncio
    async def test_send_429_retriable(self) -> None:
        ch = GoogleChatChannel(service_account_json="")
        mock_resp = httpx.Response(status_code=429, request=httpx.Request("POST", "https://x"))
        exc = httpx.HTTPStatusError("Rate Limited", request=mock_resp.request, response=mock_resp)

        with patch.object(ch._api, "send_message", new_callable=AsyncMock, side_effect=exc):
            msg = OutboundMessage(channel="googlechat", user_id="u1", recipient_id="spaces/AAA", content="hello")
            with pytest.raises(ChannelSendError) as exc_info:
                await ch.send(msg)

        assert exc_info.value.status_code == 429
        assert exc_info.value.retriable is True


class TestGoogleChatLifecycle:
    """Start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_unconfigured(self) -> None:
        ch = GoogleChatChannel(service_account_json="")
        await ch.start()
        assert ch._status != ChannelStatus.RUNNING

    @pytest.mark.asyncio
    async def test_start_auth_failure(self) -> None:
        ch = GoogleChatChannel(service_account_json="")
        ch._api._client_email = "test@proj.iam.gserviceaccount.com"
        ch._api._private_key = object()  # type: ignore[assignment]

        with patch.object(ch._api, "verify_token", new_callable=AsyncMock, return_value=False):
            await ch.start()

        assert ch._status == ChannelStatus.DEGRADED


class TestVerifyGoogleChatBearer:
    """Bearer token verification function tests."""

    @pytest.mark.asyncio
    async def test_invalid_token_format(self) -> None:
        from app.channels.providers.googlechat.api import (
            verify_google_chat_bearer,
        )

        assert await verify_google_chat_bearer("not-a-jwt", "https://example.com") is False
        assert await verify_google_chat_bearer("a.b", "https://example.com") is False
        assert await verify_google_chat_bearer("", "https://example.com") is False

    @pytest.mark.asyncio
    async def test_wrong_algorithm(self) -> None:
        import base64
        import json

        from app.channels.providers.googlechat.api import (
            verify_google_chat_bearer,
        )

        def _b64url(data: bytes) -> str:
            return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

        header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
        claims = _b64url(json.dumps({"iss": "chat@system.gserviceaccount.com"}).encode())
        token = f"{header}.{claims}.fakesig"
        assert await verify_google_chat_bearer(token, "https://example.com") is False

    @pytest.mark.asyncio
    async def test_wrong_issuer(self) -> None:
        import base64
        import json
        import time

        from app.channels.providers.googlechat.api import (
            verify_google_chat_bearer,
        )

        def _b64url(data: bytes) -> str:
            return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

        now = int(time.time())
        header = _b64url(json.dumps({"alg": "RS256", "typ": "JWT", "kid": "k1"}).encode())
        claims = _b64url(
            json.dumps(
                {
                    "iss": "wrong@issuer.com",
                    "aud": "https://example.com",
                    "iat": now,
                    "exp": now + 3600,
                }
            ).encode()
        )
        token = f"{header}.{claims}.fakesig"
        assert await verify_google_chat_bearer(token, "https://example.com") is False

    @pytest.mark.asyncio
    async def test_wrong_audience(self) -> None:
        import base64
        import json
        import time

        from app.channels.providers.googlechat.api import (
            verify_google_chat_bearer,
        )

        def _b64url(data: bytes) -> str:
            return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

        now = int(time.time())
        header = _b64url(json.dumps({"alg": "RS256", "typ": "JWT", "kid": "k1"}).encode())
        claims = _b64url(
            json.dumps(
                {
                    "iss": "chat@system.gserviceaccount.com",
                    "aud": "https://wrong.example.com",
                    "iat": now,
                    "exp": now + 3600,
                }
            ).encode()
        )
        token = f"{header}.{claims}.fakesig"
        assert await verify_google_chat_bearer(token, "https://example.com") is False

    @pytest.mark.asyncio
    async def test_expired_token(self) -> None:
        import base64
        import json
        import time

        from app.channels.providers.googlechat.api import (
            verify_google_chat_bearer,
        )

        def _b64url(data: bytes) -> str:
            return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

        now = int(time.time())
        header = _b64url(json.dumps({"alg": "RS256", "typ": "JWT", "kid": "k1"}).encode())
        claims = _b64url(
            json.dumps(
                {
                    "iss": "chat@system.gserviceaccount.com",
                    "aud": "https://example.com",
                    "iat": now - 7200,
                    "exp": now - 3600,
                }
            ).encode()
        )
        token = f"{header}.{claims}.fakesig"
        assert await verify_google_chat_bearer(token, "https://example.com") is False
