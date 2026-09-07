"""Tests for Provider Balance REST API and Service.

[INPUT]
- app.api.providers.balance_router::router
- app.services.providers.balance_service::provider_balance_service
- httpx::ASGITransport, AsyncClient

[OUTPUT]
- test_provider_balance_gauges_endpoint
- test_provider_balance_service_probes

[POS]
Server integration and unit tests for live provider quota and balance gauges.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.providers.balance_service import (
    ProviderBalanceResult,
    ProviderBalanceService,
    ProviderBalanceStatus,
)


@pytest.mark.asyncio
async def test_provider_balance_service_determine_status() -> None:
    service = ProviderBalanceService()

    # CNY status
    assert service._determine_status(50.0, "CNY") == ProviderBalanceStatus.HEALTHY
    assert service._determine_status(5.0, "CNY") == ProviderBalanceStatus.WARNING
    assert service._determine_status(1.5, "CNY") == ProviderBalanceStatus.CRITICAL

    # USD status
    assert service._determine_status(10.0, "USD") == ProviderBalanceStatus.HEALTHY
    assert service._determine_status(1.5, "USD") == ProviderBalanceStatus.WARNING
    assert service._determine_status(0.2, "USD") == ProviderBalanceStatus.CRITICAL

    # None balance
    assert service._determine_status(None, "USD") == ProviderBalanceStatus.UNSUPPORTED


@pytest.mark.asyncio
async def test_provider_balance_service_probes_mocked() -> None:
    service = ProviderBalanceService()

    # Mock DeepSeek probe
    fake_deepseek_resp = MagicMock()
    fake_deepseek_resp.status_code = 200
    fake_deepseek_resp.json.return_value = {
        "balance_infos": [{"currency": "CNY", "total_balance": "88.50"}]
    }

    mock_client = AsyncMock()
    mock_client.get.return_value = fake_deepseek_resp

    res = await service._probe_deepseek(mock_client, api_key="sk-test")
    assert res.provider_id == "deepseek"
    assert res.balance == 88.50
    assert res.currency == "CNY"
    assert res.status == ProviderBalanceStatus.HEALTHY
    assert res.is_estimated is False

    # Mock SiliconFlow probe
    fake_sf_resp = MagicMock()
    fake_sf_resp.status_code = 200
    fake_sf_resp.json.return_value = {
        "data": {"totalBalance": "1.50"}
    }
    mock_client.get.return_value = fake_sf_resp
    res_sf = await service._probe_siliconflow(mock_client, api_key="sk-test")
    assert res_sf.provider_id == "siliconflow"
    assert res_sf.balance == 1.50
    assert res_sf.status == ProviderBalanceStatus.CRITICAL

    # Mock OpenRouter probe
    fake_or_resp = MagicMock()
    fake_or_resp.status_code = 200
    fake_or_resp.json.return_value = {
        "data": {"limit": 10.0, "usage": 9.0}
    }
    mock_client.get.return_value = fake_or_resp
    res_or = await service._probe_openrouter(mock_client, api_key="sk-test")
    assert res_or.provider_id == "openrouter"
    assert res_or.balance == 1.0  # 10 - 9
    assert res_or.currency == "USD"
    assert res_or.status == ProviderBalanceStatus.WARNING


@pytest.mark.asyncio
async def test_get_provider_balance_gauges_endpoint() -> None:
    mock_result = [
        ProviderBalanceResult(
            provider_id="deepseek",
            balance=50.0,
            currency="CNY",
            status=ProviderBalanceStatus.HEALTHY,
            details="Mocked",
        ).to_dict()
    ]

    with patch(
        "app.api.providers.balance_router.provider_balance_service.get_all_provider_balances",
        new=AsyncMock(return_value=mock_result),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
            resp = await client.get("/api/v1/providers/balance-gauges")
            assert resp.status_code == 200
            data = resp.json()
            assert data["code"] == 0
            assert isinstance(data["data"], list)
            assert len(data["data"]) == 1
            assert data["data"][0]["provider_id"] == "deepseek"
            assert data["data"][0]["status"] == "healthy"
