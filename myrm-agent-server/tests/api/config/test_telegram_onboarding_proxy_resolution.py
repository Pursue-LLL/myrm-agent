"""Which proxy a Telegram onboarding run uses: the one the user typed, else the one already saved."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.config.telegram_onboarding import (
    TelegramAssistantOnboardingRequest,
    _build_telegram_credentials,
    _resolve_telegram_proxy,
)

_STORED: dict[str, object] = {"botToken": "old-token", "proxy": "http://127.0.0.1:7890"}


@pytest.mark.parametrize(
    ("requested", "stored", "expected"),
    [
        (None, _STORED, "http://127.0.0.1:7890"),
        ("", _STORED, "http://127.0.0.1:7890"),
        ("   ", _STORED, "http://127.0.0.1:7890"),
        (None, {"botToken": "old-token"}, None),
        (None, None, None),
        ("http://127.0.0.1:8080", _STORED, "http://127.0.0.1:8080"),
        ("  socks5h://proxy.lan:1080  ", None, "socks5h://proxy.lan:1080"),
        ("socks://127.0.0.1:1080", None, "socks5://127.0.0.1:1080"),
    ],
)
def test_the_typed_proxy_wins_and_a_blank_one_keeps_the_saved_proxy(
    requested: str | None, stored: dict[str, object] | None, expected: str | None
) -> None:
    assert _resolve_telegram_proxy(requested, stored) == expected


@pytest.mark.parametrize(
    "requested",
    ["ftp://127.0.0.1:21", "127.0.0.1:7890", "http://", "http://169.254.169.254:80", "http://0.0.0.0:8080"],
)
def test_an_unusable_proxy_is_refused_with_422(requested: str) -> None:
    with pytest.raises(HTTPException) as refused:
        _resolve_telegram_proxy(requested, _STORED)

    assert refused.value.status_code == 422
    assert isinstance(refused.value.detail, dict)
    assert refused.value.detail["code"] == "TELEGRAM_PROXY_REJECTED"


@pytest.mark.parametrize(
    ("previous", "proxy", "expected"),
    [
        ({"botToken": "old-token"}, "socks5://127.0.0.1:1080", "socks5://127.0.0.1:1080"),
        (_STORED, "http://127.0.0.1:8080", "http://127.0.0.1:8080"),
        (_STORED, None, None),
        (None, None, None),
    ],
)
def test_the_credentials_carry_exactly_the_resolved_proxy(
    previous: dict[str, object] | None, proxy: str | None, expected: str | None
) -> None:
    request = TelegramAssistantOnboardingRequest(botToken="1234567890:VALID_TOKEN")

    credentials = _build_telegram_credentials(previous, request, proxy)

    assert credentials.get("proxy") == expected
    assert ("proxy" in credentials) is (expected is not None)
