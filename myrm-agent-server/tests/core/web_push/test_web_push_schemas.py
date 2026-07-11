"""Tests for Web Push Pydantic schemas — input validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.web_push.schemas import (
    WebPushSubscriptionRequest,
    WebPushTestRequest,
    WebPushUnsubscribeRequest,
    WebPushVapidKeyResponse,
)


class TestWebPushSubscriptionRequest:
    def test_valid_request(self) -> None:
        req = WebPushSubscriptionRequest(
            endpoint="https://fcm.googleapis.com/fcm/send/abc",
            p256dh="BNc...",
            auth="xyz",
        )
        assert req.endpoint == "https://fcm.googleapis.com/fcm/send/abc"
        assert req.user_agent == ""

    def test_with_user_agent(self) -> None:
        req = WebPushSubscriptionRequest(
            endpoint="https://e.com",
            p256dh="k",
            auth="a",
            user_agent="Mozilla/5.0",
        )
        assert req.user_agent == "Mozilla/5.0"

    def test_rejects_empty_endpoint(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            WebPushSubscriptionRequest(endpoint="", p256dh="k", auth="a")
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("endpoint",) for e in errors)

    def test_rejects_empty_p256dh(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            WebPushSubscriptionRequest(endpoint="https://e.com", p256dh="", auth="a")
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("p256dh",) for e in errors)

    def test_rejects_empty_auth(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            WebPushSubscriptionRequest(endpoint="https://e.com", p256dh="k", auth="")
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("auth",) for e in errors)


class TestWebPushVapidKeyResponse:
    def test_serialization(self) -> None:
        resp = WebPushVapidKeyResponse(public_key="BNc123")
        assert resp.model_dump() == {"public_key": "BNc123"}


class TestWebPushUnsubscribeRequest:
    def test_valid(self) -> None:
        req = WebPushUnsubscribeRequest(endpoint="https://e.com")
        assert req.endpoint == "https://e.com"


class TestWebPushTestRequest:
    def test_defaults(self) -> None:
        req = WebPushTestRequest()
        assert req.title == "Test Notification"
        assert "test push" in req.body.lower()

    def test_custom_values(self) -> None:
        req = WebPushTestRequest(title="Custom", body="Custom body")
        assert req.title == "Custom"
        assert req.body == "Custom body"
