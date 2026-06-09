"""测试 health 端点 WebSocket 功能标识

验证 /api/v1/health 端点返回 WebSocket 功能状态
"""

import pytest
from httpx import ASGITransport, AsyncClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="health")
@pytest.fixture
async def async_client():
    """提供 async HTTP client"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_health_endpoint_returns_websocket_enabled(async_client: AsyncClient):
    """验证 health 端点返回 websocket_enabled 状态"""
    response = await async_client.get("/api/v1/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "healthy"
    assert data["message"] == "MyrmAgent backend is running"

    # 验证 features 字段存在且包含 websocket_enabled
    assert "features" in data
    assert isinstance(data["features"], dict)
    assert "websocket_enabled" in data["features"]
    assert data["features"]["websocket_enabled"] is True
