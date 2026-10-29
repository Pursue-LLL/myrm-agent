"""Webhook routes served over real HTTP through FastAPIRouteRegistrar.

The registrar is the only thing standing between a platform's POST and a channel's
webhook handler, so these tests drive requests through it end to end instead of
inspecting what was registered.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from collections.abc import Awaitable, Callable
from unittest.mock import AsyncMock, patch

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.channels.core.rate_limit import RateLimitConfig
from app.channels.implementations.fastapi.registrar import FastAPIRouteRegistrar
from app.channels.protocols.rate_limiter import RateLimiterProtocol
from app.channels.protocols.route_registrar import (
    CORSConfig,
    GenericRequest,
    GenericResponse,
    HttpMethod,
    RouteMetadata,
)
from app.channels.providers.feishu import FeishuChannel
from app.channels.providers.msteams import MSTeamsChannel
from app.channels.providers.sms import SMSChannel
from app.channels.providers.telegram import TelegramChannel
from tests.channels.channel_test_base import FAKE_TELEGRAM_BOT_TOKEN

Handler = Callable[[GenericRequest], Awaitable[GenericResponse]]


class _Reply:
    """Minimal GenericResponse."""

    def __init__(self, status_code: int = 200, body: bytes = b"ok", headers: dict[str, str] | None = None) -> None:
        self.status_code = status_code
        self.body = body
        self.headers = headers or {}


class _RecordingLimiter:
    """Rate limiter that records who was checked and answers with a fixed verdict."""

    def __init__(self, allowed: bool) -> None:
        self.allowed = allowed
        self.client_ids: list[str] = []

    async def check_limit(self, route_path: str, client_id: str, limit_config: RateLimitConfig) -> tuple[bool, int]:
        self.client_ids.append(client_id)
        return self.allowed, 0


def _client(app: FastAPI) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def _serve(
    handler: Handler,
    metadata: RouteMetadata | None = None,
    *,
    rate_limiter: RateLimiterProtocol | None = None,
    auth_dependency: object | None = None,
) -> TestClient:
    app = FastAPI()
    registrar = FastAPIRouteRegistrar(app, "probe", rate_limiter=rate_limiter, auth_dependency=auth_dependency)
    registrar.add_route(HttpMethod.POST, "hook", handler, metadata or RouteMetadata())
    return _client(app)


async def _ok(request: GenericRequest) -> GenericResponse:
    return _Reply(201, b"created", {"x-probe": "1"})


async def _boom(request: GenericRequest) -> GenericResponse:
    raise RuntimeError("secret internals")


class TestRouteDispatch:
    def test_the_handler_response_reaches_the_client_unchanged(self) -> None:
        response = _serve(_ok).post("/api/channels/probe/hook")

        assert (response.status_code, response.content, response.headers["x-probe"]) == (201, b"created", "1")

    def test_a_failing_handler_yields_a_json_500_that_hides_the_error(self) -> None:
        response = _serve(_boom).post("/api/channels/probe/hook")

        assert (response.status_code, response.json()) == (500, {"error": "Internal server error"})

    def test_a_rate_limited_request_gets_429_and_never_reaches_the_handler(self) -> None:
        handler = AsyncMock()
        metadata = RouteMetadata(rate_limit_policy=RateLimitConfig(max_requests=1, window_seconds=60))

        client = _serve(handler, metadata, rate_limiter=_RecordingLimiter(allowed=False))
        response = client.post("/api/channels/probe/hook")

        assert (response.status_code, response.headers["x-ratelimit-remaining"]) == (429, "0")
        handler.assert_not_awaited()

    def test_an_open_route_is_rate_limited_per_client_address(self) -> None:
        limiter = _RecordingLimiter(allowed=True)
        metadata = RouteMetadata(rate_limit_policy=RateLimitConfig(max_requests=5, window_seconds=60))

        response = _serve(_ok, metadata, rate_limiter=limiter).post("/api/channels/probe/hook")

        assert (response.status_code, limiter.client_ids) == (201, ["testclient"])

    def test_an_authenticated_route_is_rate_limited_per_user(self) -> None:
        limiter = _RecordingLimiter(allowed=True)
        metadata = RouteMetadata(
            requires_auth=True,
            rate_limit_policy=RateLimitConfig(max_requests=5, window_seconds=60),
        )

        client = _serve(_ok, metadata, rate_limiter=limiter, auth_dependency=Depends(lambda: "user-7"))
        response = client.post("/api/channels/probe/hook")

        assert (response.status_code, limiter.client_ids) == (201, ["user-7"])

    def test_cors_headers_are_added_to_success_and_error_responses(self) -> None:
        metadata = RouteMetadata(cors_config=CORSConfig(allow_origins=["https://app.example"]))
        origin = {"Origin": "https://app.example"}

        success = _serve(_ok, metadata).post("/api/channels/probe/hook", headers=origin)
        failure = _serve(_boom, metadata).post("/api/channels/probe/hook", headers=origin)

        assert [r.headers["access-control-allow-origin"] for r in (success, failure)] == ["https://app.example"] * 2


def _mount(channel: object, name: str) -> TestClient:
    app = FastAPI()
    channel.register_routes(FastAPIRouteRegistrar(app, name))  # type: ignore[attr-defined]
    return _client(app)


class TestFeishuWebhook:
    URL = "/api/channels/feishu/webhook"

    def _channel(self) -> FeishuChannel:
        return FeishuChannel(
            app_id="app-1",
            app_secret="secret",
            encrypt_key="key",
            verification_token="token-1",
        )

    def test_url_verification_echoes_the_challenge(self) -> None:
        body = {"challenge": "c-123", "type": "url_verification"}

        response = _mount(self._channel(), "feishu").post(self.URL, json=body)

        assert (response.status_code, response.json()) == (200, {"challenge": "c-123"})

    def test_an_event_with_the_wrong_verification_token_is_rejected(self) -> None:
        event = {"header": {"app_id": "app-1", "event_type": "im.message.receive_v1"}, "token": "forged"}

        response = _mount(self._channel(), "feishu").post(self.URL, json=event)

        assert (response.status_code, response.json()["title"]) == (403, "Invalid Signature")


class TestTelegramWebhook:
    URL = "/api/channels/telegram/webhook"
    SECRET_HEADER = "x-telegram-bot-api-secret-token"

    def test_an_update_with_the_right_secret_is_handled(self) -> None:
        channel = TelegramChannel(FAKE_TELEGRAM_BOT_TOKEN)
        update = {"update_id": 1}
        headers = {self.SECRET_HEADER: channel.webhook_secret}

        with patch.object(channel, "handle_webhook_update", new=AsyncMock()) as handled:
            response = _mount(channel, "telegram").post(self.URL, json=update, headers=headers)

        assert (response.status_code, response.json()) == (200, {"ok": True})
        handled.assert_awaited_once_with(update)

    def test_an_update_with_the_wrong_secret_is_rejected(self) -> None:
        channel = TelegramChannel(FAKE_TELEGRAM_BOT_TOKEN)

        response = _mount(channel, "telegram").post(self.URL, json={"update_id": 1}, headers={self.SECRET_HEADER: "nope"})

        assert (response.status_code, response.json()["title"]) == (403, "Invalid Signature")

    def test_a_body_that_is_not_json_is_a_400(self) -> None:
        channel = TelegramChannel(FAKE_TELEGRAM_BOT_TOKEN)
        headers = {self.SECRET_HEADER: channel.webhook_secret}

        response = _mount(channel, "telegram").post(self.URL, content=b"not json", headers=headers)

        assert (response.status_code, response.json()) == (400, {"ok": False, "error": "Invalid JSON"})


class TestTeamsWebhook:
    URL = "/api/channels/msteams/webhook"

    def test_an_activity_is_handled_when_no_app_id_is_configured(self) -> None:
        channel = MSTeamsChannel(app_id="", app_password="")
        activity = {"type": "message", "text": "hi"}

        with patch.object(channel, "handle_activity", new=AsyncMock()) as handled:
            response = _mount(channel, "msteams").post(self.URL, json=activity)

        assert response.status_code == 200
        handled.assert_awaited_once_with(activity)

    def test_an_activity_without_a_bearer_token_is_rejected_when_an_app_id_is_configured(self) -> None:
        channel = MSTeamsChannel(app_id="app-1", app_password="pw")

        response = _mount(channel, "msteams").post(self.URL, json={"type": "message"})

        assert (response.status_code, response.json()["title"]) == (403, "Invalid Signature")


class TestSmsWebhook:
    URL = "/api/channels/sms/webhook"
    AUTH_TOKEN = "twilio-token"

    def _channel(self) -> SMSChannel:
        return SMSChannel(account_sid="AC123", auth_token=self.AUTH_TOKEN, phone_number="+15550000000")

    def _signature(self, form: dict[str, str]) -> str:
        signed = "http://testserver" + self.URL + "".join(k + v for k, v in sorted(form.items()))
        digest = hmac.new(self.AUTH_TOKEN.encode(), signed.encode(), hashlib.sha1).digest()
        return base64.b64encode(digest).decode()

    def test_a_signed_message_is_accepted_and_answered_with_empty_twiml(self) -> None:
        channel = self._channel()
        form = {"From": "+15551112222", "Body": "hello", "MessageSid": "SM1"}
        headers = {"x-twilio-signature": self._signature(form)}

        with patch.object(channel, "_emit_inbound", new=AsyncMock()) as emitted:
            response = _mount(channel, "sms").post(self.URL, data=form, headers=headers)

        assert (response.status_code, response.headers["content-type"]) == (200, "application/xml")
        assert [call.args[0].content for call in emitted.await_args_list] == ["hello"]

    def test_a_message_with_a_bad_signature_is_a_403(self) -> None:
        channel = self._channel()
        form = {"From": "+15551112222", "Body": "hello"}

        with patch.object(channel, "_emit_inbound", new=AsyncMock()) as emitted:
            response = _mount(channel, "sms").post(self.URL, data=form, headers={"x-twilio-signature": "forged"})

        assert response.status_code == 403
        emitted.assert_not_awaited()
