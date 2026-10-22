"""
[INPUT]:
- httpx, ASGITransport
- app.api.system.debug_share_api::router

[OUTPUT]:
- Pytest test cases verifying sanitized debug dump creation, ephemeral link generation, and burn-after-reading consumption.

[POS]:
tests/api/system/test_debug_share_api.py — 零外泄调试包导出与阅后即焚分享 API 单元测试。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import FastAPI
import httpx
from httpx import ASGITransport
import pytest

from app.api.system.debug_share_api import router as debug_share_router

test_app = FastAPI()
test_app.include_router(debug_share_router, prefix="/api/v1/system")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_create_and_get_sanitized_dump(async_client: httpx.AsyncClient) -> None:
    # 1. 提交包含敏感 Token 与私密环境变量的请求
    payload = {
        "raw_logs": [
            "2026-10-12 INFO Authenticating with sk-ant-api03-1234567890123456789012345678901234567890",
            "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.secret",
            "Normal non-sensitive log message",
        ],
        "recent_traces": [
            {
                "event": "llm_call",
                "auth_header": "Bearer ghp_1234567890abcdefghijklmnopqrstuvwxyz",
            }
        ],
        "user_note": "Please debug my instance, token was sk-proj-123456789012345678901234567890",
    }
    resp = await async_client.post("/api/v1/system/debug-share/dump", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    dump_id = data["dump_id"]
    assert dump_id.startswith("dump_")
    assert len(data["sanitized_logs"]) == 3
    # 验证敏感凭证已被脱敏打码
    assert "sk-ant-api03-" not in data["sanitized_logs"][0]
    assert "[REDACTED_API_KEY]" in data["sanitized_logs"][0]
    assert "eyJhbGci" not in data["sanitized_logs"][1]
    assert "[REDACTED_TOKEN]" in data["sanitized_logs"][1]
    # 验证 trace 和 user_note 也已被脱敏
    assert "ghp_" not in data["recent_traces"][0]["auth_header"]
    assert "sk-proj-" not in data["user_note"]
    assert data["total_redacted_count"] >= 3
    assert len(data["checksum_sha256"]) == 64
    assert data["vitals"]["cpu_cores"] >= 1

    # 2. 查询该 dump_id
    get_resp = await async_client.get(f"/api/v1/system/debug-share/dump/{dump_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["dump_id"] == dump_id

    # 3. 查询不存在的 dump_id
    not_found_resp = await async_client.get("/api/v1/system/debug-share/dump/dump_nonexistent")
    assert not_found_resp.status_code == 404


@pytest.mark.asyncio
async def test_ephemeral_share_link_lifecycle_and_burn(async_client: httpx.AsyncClient) -> None:
    # 1. 创建 dump
    dump_resp = await async_client.post(
        "/api/v1/system/debug-share/dump",
        json={"raw_logs": ["safe log row"], "user_note": "need assistance"},
    )
    dump_id = dump_resp.json()["dump_id"]

    # 2. 生成阅后即焚链接
    link_resp = await async_client.post(
        "/api/v1/system/debug-share/ephemeral-link",
        json={"dump_id": dump_id, "base_url": "https://test.myrm.ai/share"},
    )
    assert link_resp.status_code == 200
    link_data = link_resp.json()
    share_token = link_data["share_token"]
    assert share_token.startswith("share_")
    assert link_data["max_views"] == 3
    assert link_data["remaining_views"] == 3
    assert link_data["is_destroyed"] is False

    # 3. 消费第 1 次
    view1 = await async_client.get(f"/api/v1/system/debug-share/view/{share_token}")
    assert view1.status_code == 200
    v1_data = view1.json()
    assert v1_data["dump"] is not None
    assert v1_data["remaining_views"] == 2
    assert v1_data["is_destroyed"] is False

    # 4. 消费第 2 次
    view2 = await async_client.get(f"/api/v1/system/debug-share/view/{share_token}")
    assert view2.status_code == 200
    v2_data = view2.json()
    assert v2_data["dump"] is not None
    assert v2_data["remaining_views"] == 1
    assert v2_data["is_destroyed"] is False

    # 5. 消费第 3 次（达限自毁）
    view3 = await async_client.get(f"/api/v1/system/debug-share/view/{share_token}")
    assert view3.status_code == 200
    v3_data = view3.json()
    assert v3_data["dump"] is not None
    assert v3_data["remaining_views"] == 0
    assert v3_data["is_destroyed"] is True

    # 6. 第 4 次访问应已被彻底自毁
    view4 = await async_client.get(f"/api/v1/system/debug-share/view/{share_token}")
    assert view4.status_code == 200
    v4_data = view4.json()
    assert v4_data["dump"] is None
    assert v4_data["is_destroyed"] is True
    assert "自毁" in v4_data["error"]
