"""
[INPUT]:
- httpx, ASGITransport
- app.api.system.context_breakdown_api::router

[OUTPUT]:
- Pytest verification for seven-category context usage resolution, 60%/90% alert boundaries, and threshold config endpoints.

[POS]:
tests/api/system/test_context_breakdown_api.py — 上下文用量七分类精准解析与警戒线 API 单元测试。
"""

from collections.abc import AsyncGenerator

from fastapi import FastAPI
import httpx
from httpx import ASGITransport
import pytest

from app.api.system.context_breakdown_api import router as context_breakdown_router

test_app = FastAPI()
test_app.include_router(context_breakdown_router, prefix="/api/v1/system")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_resolve_context_breakdown_api(
    async_client: httpx.AsyncClient,
) -> None:
    # 模拟真实工程上下文注入
    system_content = (
        "You are an AI coding assistant.\n"
        "<user_memory_context>\n"
        "User prefers concise responses and zero Any type.\n"
        "</user_memory_context>\n"
        "<workspace_context>\n"
        "Path: /workspace/open-perplexity. Rules: adhere to PEP8.\n"
        "</workspace_context>\n"
    )

    messages = [
        {
            "role": "user",
            "content": (
                "<bound_skills>\n"
                "- code-search: Fast grep & AST query\n"
                "</bound_skills>\n"
                "Please refactor the context breakdown module."
            ),
        },
        {
            "role": "tool",
            "content": "Tool stdout: AST inspection finished without lint warnings.",
        },
        {
            "role": "assistant",
            "content": "All files updated and verified.",
        },
    ]

    resp = await async_client.post(
        "/api/v1/system/context-breakdown/resolve",
        json={
            "system_content": system_content,
            "messages": messages,
            "tools_schema_tokens": 300,
            "provider_actual_tokens": 6500,
            "total_window_tokens": 10000,
        },
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["total_window_tokens"] == 10000
    assert data["provider_actual_tokens"] == 6500
    assert data["usage_ratio_pct"] == 65.0
    # 65% 落在 60%~90% 区间，必须触发 WARNING_60 警戒线
    assert data["alert_level"] == "WARNING_60"
    assert "60%" in data["alert_message"]

    categories = data["categories"]
    # 确保七大细分项均被解析
    assert "system_prompt" in categories
    assert "memory" in categories
    assert "workspace" in categories
    assert "skills" in categories
    assert "tools_schema" in categories
    assert "tool_results" in categories
    assert "chat_messages" in categories

    assert categories["memory"]["estimated_tokens"] > 0
    assert categories["workspace"]["estimated_tokens"] > 0
    assert categories["skills"]["estimated_tokens"] > 0
    assert categories["tools_schema"]["estimated_tokens"] == 300
    assert categories["tool_results"]["estimated_tokens"] > 0


@pytest.mark.asyncio
async def test_get_context_thresholds_api(
    async_client: httpx.AsyncClient,
) -> None:
    resp = await async_client.get("/api/v1/system/context-breakdown/thresholds")
    assert resp.status_code == 200
    data = resp.json()
    assert data["warning_ratio_pct"] == 60.0
    assert data["critical_ratio_pct"] == 90.0
    assert "60%" in data["recommended_action_60"]
    assert "90%" in data["recommended_action_90"]
