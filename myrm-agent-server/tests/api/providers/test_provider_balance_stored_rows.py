"""Balance probes read a provider row the way the WebUI stores it.

A stored row keeps its keys in ``apiKeys`` and its endpoint in ``apiUrl``. The probe sends the first active key to that
endpoint (the vendor's own host only when the row names none) and does not probe at all without a key the user typed.

[INPUT]
- app.services.providers.balance_service::ProviderBalanceService
- httpx::MockTransport (in-memory vendor, no network)

[OUTPUT]
- test_*: probe_single_provider / get_all_provider_balances against stored provider rows

[POS]
Server unit tests for the shape of provider rows consumed by live balance probes.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services.providers.balance_service import (
    ProviderBalanceResult,
    ProviderBalanceService,
    ProviderBalanceStatus,
)

Handler = Callable[[httpx.Request], httpx.Response]

# provider id, endpoint the WebUI preset stores, balance path, vendor reply, balance parsed from that reply
_VENDORS = [
    pytest.param(
        "deepseek",
        "https://api.deepseek.com",
        "/user/balance",
        {"balance_infos": [{"currency": "CNY", "total_balance": "88.50"}]},
        88.5,
        id="deepseek",
    ),
    pytest.param(
        "siliconflow",
        "https://api.siliconflow.cn/v1",
        "/user/info",
        {"data": {"totalBalance": "50.00"}},
        50.0,
        id="siliconflow",
    ),
    pytest.param(
        "openrouter",
        "https://openrouter.ai/api/v1",
        "/auth/key",
        {"data": {"limit": 10.0, "usage": 1.0}},
        9.0,
        id="openrouter",
    ),
    pytest.param(
        "moonshot",
        "https://api.moonshot.cn/v1",
        "/users/me/balance",
        {"data": {"cash_balance": 20.0, "voucher_balance": 5.0}},
        25.0,
        id="moonshot",
    ),
]

_DEEPSEEK_REPLY: dict[str, object] = {"balance_infos": [{"currency": "CNY", "total_balance": "88.50"}]}


def _key(key: str, *, active: bool = True) -> dict[str, object]:
    """One ``apiKeys`` entry as the WebUI stores it."""
    return {"id": f"id-{key}", "key": key, "remark": "", "isActive": active}


def _row(
    provider_id: str,
    *,
    keys: list[dict[str, object]] | None = None,
    api_url: str = "",
    **extra: object,
) -> dict[str, object]:
    """A stored provider row; ``keys=None`` gives it one active key."""
    return {
        "id": provider_id,
        "isEnabled": True,
        "apiKeys": [_key("sk-stored")] if keys is None else keys,
        "apiUrl": api_url,
        **extra,
    }


def _reply(body: dict[str, object]) -> Handler:
    return lambda _request: httpx.Response(200, json=body)


def _vendor(seen: list[httpx.Request], handler: Handler) -> Handler:
    """In-memory vendor that records every request it receives."""

    def vendor(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    return vendor


async def _probe(row: dict[str, object], handler: Handler) -> tuple[ProviderBalanceResult, list[httpx.Request]]:
    """Run ``probe_single_provider`` against an in-memory vendor and return what it asked for."""
    seen: list[httpx.Request] = []
    async with httpx.AsyncClient(transport=httpx.MockTransport(_vendor(seen, handler))) as client:
        result = await ProviderBalanceService().probe_single_provider(client, str(row["id"]), row)
    return result, seen


@pytest.mark.asyncio
@pytest.mark.parametrize(("provider_id", "preset_url", "path", "reply", "balance"), _VENDORS)
async def test_preset_endpoint_of_each_vendor_reaches_its_balance_path(
    provider_id: str, preset_url: str, path: str, reply: dict[str, object], balance: float
) -> None:
    result, seen = await _probe(_row(provider_id, api_url=preset_url), _reply(reply))

    assert [str(request.url) for request in seen] == [preset_url + path]
    assert seen[0].headers["authorization"] == "Bearer sk-stored"
    assert result.status == ProviderBalanceStatus.HEALTHY
    assert result.balance == balance


@pytest.mark.asyncio
@pytest.mark.parametrize(("provider_id", "preset_url", "path", "reply", "balance"), _VENDORS)
async def test_row_without_endpoint_probes_the_vendor_default_host(
    provider_id: str, preset_url: str, path: str, reply: dict[str, object], balance: float
) -> None:
    result, seen = await _probe(_row(provider_id), _reply(reply))

    assert [str(request.url) for request in seen] == [preset_url + path]
    assert result.balance == balance


@pytest.mark.asyncio
async def test_custom_endpoint_gets_the_key_and_the_vendor_host_gets_nothing() -> None:
    row = _row("deepseek", api_url="https://gateway.example/deepseek/")

    result, seen = await _probe(row, _reply(_DEEPSEEK_REPLY))

    assert [str(request.url) for request in seen] == ["https://gateway.example/deepseek/user/balance"]
    assert seen[0].headers["authorization"] == "Bearer sk-stored"
    assert result.balance == 88.5


@pytest.mark.asyncio
async def test_first_active_key_is_the_one_probed() -> None:
    keys = [_key("sk-off", active=False), _key("sk-first"), _key("sk-second")]

    _, seen = await _probe(_row("deepseek", keys=keys), _reply(_DEEPSEEK_REPLY))

    assert [request.headers["authorization"] for request in seen] == ["Bearer sk-first"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "row",
    [
        pytest.param(_row("deepseek", keys=[]), id="no-keys"),
        pytest.param(_row("deepseek", keys=[_key("sk-off", active=False)]), id="only-inactive-keys"),
        pytest.param(_row("deepseek", keys=[_key("   ")]), id="blank-key"),
        pytest.param(_row("deepseek", keys=[], apiKey="sk-flat"), id="flat-api-key-field"),
        pytest.param(_row("deepseek", keys=[], _oauthToken="oauth-token"), id="oauth-token-only"),
    ],
)
async def test_without_a_key_the_user_typed_nothing_is_probed(row: dict[str, object]) -> None:
    result, seen = await _probe(row, _reply(_DEEPSEEK_REPLY))

    assert seen == []
    assert result.status == ProviderBalanceStatus.UNSUPPORTED
    assert result.details == "No API key configured"


@pytest.mark.asyncio
async def test_provider_without_a_balance_endpoint_never_receives_the_key() -> None:
    estimate = ProviderBalanceResult(
        provider_id="openai",
        balance=None,
        currency="UNKNOWN",
        status=ProviderBalanceStatus.UNSUPPORTED,
        is_estimated=True,
    )

    with patch.object(ProviderBalanceService, "_estimate_from_local_usage", new=AsyncMock(return_value=estimate)) as local:
        result, seen = await _probe(_row("openai", api_url="https://api.openai.com/v1"), _reply({}))

    assert result is estimate
    assert seen == []
    local.assert_awaited_once_with("openai")


@pytest.mark.asyncio
async def test_rejected_key_is_reported_as_unsupported_with_the_http_status() -> None:
    result, seen = await _probe(_row("deepseek"), lambda _request: httpx.Response(401))

    assert len(seen) == 1
    assert result.status == ProviderBalanceStatus.UNSUPPORTED
    assert result.details == "HTTP 401"


@pytest.mark.asyncio
async def test_stored_providers_become_gauges_for_enabled_rows_only() -> None:
    providers = [
        _row("deepseek", api_url="https://api.deepseek.com"),
        _row("siliconflow", api_url="https://api.siliconflow.cn/v1", isEnabled=False),
        _row("ollama", keys=[]),
    ]
    seen: list[httpx.Request] = []
    real_client = httpx.AsyncClient

    def client_on_in_memory_vendor(**kwargs: float) -> httpx.AsyncClient:
        return real_client(transport=httpx.MockTransport(_vendor(seen, _reply(_DEEPSEEK_REPLY))), **kwargs)

    configs = SimpleNamespace(providers_dict={"providers": providers})
    with (
        patch("app.core.channel_bridge.config_loader.load_user_configs", new=AsyncMock(return_value=configs)),
        patch("app.services.providers.balance_service.httpx.AsyncClient", side_effect=client_on_in_memory_vendor),
    ):
        gauges = await ProviderBalanceService().get_all_provider_balances()

    by_provider = {str(gauge["provider_id"]): gauge for gauge in gauges}
    assert set(by_provider) == {"deepseek", "ollama"}
    assert by_provider["deepseek"]["status"] == "healthy"
    assert by_provider["deepseek"]["balance"] == 88.5
    assert by_provider["ollama"]["currency"] == "UNLIMITED"
    assert [str(request.url) for request in seen] == ["https://api.deepseek.com/user/balance"]


@pytest.mark.asyncio
async def test_no_providers_config_gives_no_gauges_and_no_warning(caplog: pytest.LogCaptureFixture) -> None:
    configs = SimpleNamespace(providers_dict=None)

    with (
        patch("app.core.channel_bridge.config_loader.load_user_configs", new=AsyncMock(return_value=configs)),
        caplog.at_level(logging.WARNING, logger="app.services.providers.balance_service"),
    ):
        gauges = await ProviderBalanceService().get_all_provider_balances()

    assert gauges == []
    assert caplog.records == []
