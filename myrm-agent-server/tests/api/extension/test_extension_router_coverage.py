"""Coverage-completion tests for extension API router endpoints."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.extension.router import (
    _build_extension_ws_url,
    _consume_pairing_or_404,
    _pairing_client_key,
    consume_extension_pairing_get,
    consume_extension_pairing_post,
    create_extension_pairing,
    get_extension_access_policy,
    update_extension_access_policy,
)
from app.services.extension.pairing import create_pairing_ticket


def _request(forwarded: str | None = None, client_host: str | None = "1.2.3.4") -> SimpleNamespace:
    return SimpleNamespace(
        base_url="https://example.com/",
        headers=SimpleNamespace(get=lambda _key: forwarded),
        client=SimpleNamespace(host=client_host) if client_host else None,
    )


def _mock_bridge() -> MagicMock:
    bridge = MagicMock()
    bridge.get_access_policy.return_value = SimpleNamespace(
        allow_all_eligible_tabs=False,
        authorized_domains=["example.com"],
        paused_tab_ids=frozenset(),
    )
    bridge.analyze_domain_policy_warnings.return_value = []
    bridge.is_access_policy_valid.return_value = True
    bridge.set_access_policy = AsyncMock(
        return_value=SimpleNamespace(
            allow_all_eligible_tabs=True,
            authorized_domains=["github.com"],
            paused_tab_ids=frozenset({1}),
        )
    )
    bridge.get_authorized_domains.return_value = ["example.com"]
    return bridge


@pytest.mark.asyncio
async def test_get_extension_access_policy_returns_policy() -> None:
    with patch("app.api.extension.router.get_extension_bridge", return_value=_mock_bridge()) as mock_factory:
        response = await get_extension_access_policy()
        mock_factory.assert_called_once()
    assert response.allow_all_eligible_tabs is False
    assert response.authorized_domains == ["example.com"]
    assert response.policy_valid is True


@pytest.mark.asyncio
async def test_update_extension_access_policy_returns_updated() -> None:
    from app.api.extension.router import AccessPolicyUpdateRequest

    body = AccessPolicyUpdateRequest(
        allow_all_eligible_tabs=True,
        domains=["github.com"],
        paused_tab_ids=[1],
    )
    with patch("app.api.extension.router.get_extension_bridge", return_value=_mock_bridge()):
        response = await update_extension_access_policy(body)
    assert response.allow_all_eligible_tabs is True
    assert response.authorized_domains == ["github.com"]
    assert response.paused_tab_ids == [1]


def test_build_extension_ws_url_https() -> None:
    request = _request()
    request.base_url = "https://example.com/"
    assert _build_extension_ws_url(request) == "wss://example.com/api/v1/ws/extension"


def test_build_extension_ws_url_http() -> None:
    request = _request()
    request.base_url = "http://127.0.0.1:8080/"
    assert _build_extension_ws_url(request) == "ws://127.0.0.1:8080/api/v1/ws/extension"


def test_pairing_client_key_prefers_forwarded() -> None:
    request = _request(forwarded="203.0.113.9, 10.0.0.1")
    assert _pairing_client_key(request) == "203.0.113.9"


def test_pairing_client_key_falls_back_to_client_host() -> None:
    assert _pairing_client_key(_request()) == "1.2.3.4"


def test_pairing_client_key_unknown() -> None:
    assert _pairing_client_key(_request(client_host=None)) == "unknown"


def test_consume_pairing_or_404_valid_and_invalid() -> None:
    code, _ = create_pairing_ticket(ws_url="ws://127.0.0.1:8080/api/v1/ws/extension", auth_token="secret")
    consumed = _consume_pairing_or_404(code)
    assert consumed.auth_token == "secret"
    assert consumed.http_base == "http://127.0.0.1:8080"

    with pytest.raises(Exception) as exc_info:
        _consume_pairing_or_404("no-such-code")
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_create_extension_pairing_builds_urls() -> None:
    with (
        patch("app.config.settings.settings.extension_auth_token") as mock_token,
        patch(
            "app.services.extension.pairing.create_pairing_ticket",
            return_value=("ABC123", 300),
        ),
    ):
        mock_token.get_secret_value.return_value = "secret"
        response = await create_extension_pairing(_request())
    assert response.code == "ABC123"
    assert response.expires_in == 300
    assert response.ws_url == "wss://example.com/api/v1/ws/extension"
    assert response.http_base == "https://example.com"
    assert response.consume_url == "https://example.com/api/v1/extension/pairing/consume"


@pytest.mark.asyncio
async def test_consume_pairing_post_rate_limited() -> None:
    from app.api.extension.router import PairingConsumeRequest

    body = PairingConsumeRequest(code="whatever")
    with (
        patch(
            "app.services.extension.pairing.check_pairing_rate_limit",
            return_value=False,
        ),
        pytest.raises(Exception) as exc_info,
    ):
        await consume_extension_pairing_post(_request(), body)
    assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_consume_pairing_post_success() -> None:
    from app.api.extension.router import PairingConsumeRequest

    code, _ = create_pairing_ticket(ws_url="ws://127.0.0.1:8080/api/v1/ws/extension", auth_token="secret")
    body = PairingConsumeRequest(code=code)
    with patch(
        "app.services.extension.pairing.check_pairing_rate_limit",
        return_value=True,
    ):
        response = await consume_extension_pairing_post(_request(), body)
    assert response.auth_token == "secret"
    assert response.http_base == "http://127.0.0.1:8080"


@pytest.mark.asyncio
async def test_consume_pairing_get_rate_limited() -> None:
    with (
        patch(
            "app.services.extension.pairing.check_pairing_rate_limit",
            return_value=False,
        ),
        pytest.raises(Exception) as exc_info,
    ):
        await consume_extension_pairing_get(_request(), "some-code")
    assert exc_info.value.status_code == 429
