"""
[INPUT]:
- httpx, ASGITransport
- app.api.system.turn_context_provenance_api::router

[OUTPUT]:
- Pytest test cases verifying turn context provenance manifest, diffing, and token breakdown endpoints.

[POS]:
tests/api/system/test_turn_context_provenance_api.py — 会话逐轮上下文注入来源清单与可复现审计 API 单元测试。
"""

from collections.abc import AsyncGenerator

from fastapi import FastAPI
import httpx
from httpx import ASGITransport
import pytest

from app.api.system.turn_context_provenance_api import router as turn_context_provenance_router

test_app = FastAPI()
test_app.include_router(turn_context_provenance_router, prefix="/api/v1/system")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_record_and_get_turn_manifest_lifecycle(async_client: httpx.AsyncClient) -> None:
    session_id = "sess_api_provenance_01"
    turn_id = "turn_001"

    payload = {
        "session_id": session_id,
        "turn_id": turn_id,
        "model_snapshot_id": "claude-3-7-sonnet-20250219",
        "chunks": [
            {
                "source_id": "sys_main",
                "kind": "system_prompt",
                "content": "You are a senior software architect.",
                "estimated_tokens": 15,
                "meta": {"version": "v1.2"},
            },
            {
                "source_id": "mem_pref",
                "kind": "memory",
                "content": "Prefers concise code and zero any types.",
                "estimated_tokens": 10,
                "meta": {"memory_type": "preference"},
            },
            {
                "source_id": "skill_git",
                "kind": "skill",
                "content": "Skill git diff inspection commands.",
                "estimated_tokens": 12,
                "meta": {"slug": "git-diff"},
            },
        ],
    }

    # 1. 记录单轮 manifest
    rec_resp = await async_client.post("/api/v1/system/turn-context/manifest/record", json=payload)
    assert rec_resp.status_code == 200
    rec_data = rec_resp.json()
    assert rec_data["session_id"] == session_id
    assert rec_data["turn_id"] == turn_id
    assert rec_data["model_snapshot_id"] == "claude-3-7-sonnet-20250219"
    assert rec_data["total_tokens"] == 37
    assert len(rec_data["chunks"]) == 3
    assert rec_data["chunks"][0]["source_id"] == "sys_main"
    assert len(rec_data["chunks"][0]["content_sha256"]) == 64

    # 2. 查询单轮 manifest
    get_resp = await async_client.get(f"/api/v1/system/turn-context/manifest/{session_id}/{turn_id}")
    assert get_resp.status_code == 200
    get_data = get_resp.json()
    assert get_data["total_tokens"] == 37
    assert len(get_data["chunks"]) == 3

    # 3. 验证四色来源 Token 分解
    breakdown_resp = await async_client.get(
        f"/api/v1/system/turn-context/token-breakdown/{session_id}/{turn_id}"
    )
    assert breakdown_resp.status_code == 200
    b_data = breakdown_resp.json()
    assert b_data["total_tokens"] == 37
    breakdown = b_data["breakdown_by_kind"]
    assert "system_prompt" in breakdown
    assert breakdown["system_prompt"]["tokens"] == 15
    assert "memory" in breakdown
    assert breakdown["memory"]["tokens"] == 10
    assert "skill" in breakdown
    assert breakdown["skill"]["tokens"] == 12


@pytest.mark.asyncio
async def test_cross_turn_diff_api(async_client: httpx.AsyncClient) -> None:
    session_id = "sess_api_diff_02"
    t1 = "turn_101"
    t2 = "turn_102"

    # 上报 Turn 1
    await async_client.post(
        "/api/v1/system/turn-context/manifest/record",
        json={
            "session_id": session_id,
            "turn_id": t1,
            "chunks": [
                {"source_id": "sys", "kind": "system_prompt", "content": "Prompt v1", "estimated_tokens": 10},
                {"source_id": "mem_1", "kind": "memory", "content": "Memory persistent", "estimated_tokens": 8},
                {"source_id": "tool_old", "kind": "skill", "content": "Tool old", "estimated_tokens": 5},
            ],
        },
    )

    # 上报 Turn 2 (sys 修改, mem_1 不变, tool_old 移除, mcp_new 新增)
    await async_client.post(
        "/api/v1/system/turn-context/manifest/record",
        json={
            "session_id": session_id,
            "turn_id": t2,
            "chunks": [
                {"source_id": "sys", "kind": "system_prompt", "content": "Prompt v2 modified", "estimated_tokens": 18},
                {"source_id": "mem_1", "kind": "memory", "content": "Memory persistent", "estimated_tokens": 8},
                {"source_id": "mcp_new", "kind": "mcp_server", "content": "MCP Server tool schemas", "estimated_tokens": 20},
            ],
        },
    )

    # 比对 Turn 1 与 Turn 2
    diff_resp = await async_client.post(
        "/api/v1/system/turn-context/diff",
        json={
            "session_id": session_id,
            "previous_turn_id": t1,
            "current_turn_id": t2,
        },
    )
    assert diff_resp.status_code == 200
    diff_data = diff_resp.json()
    assert diff_data["previous_turn_id"] == t1
    assert diff_data["current_turn_id"] == t2
    assert diff_data["total_token_delta"] == (46 - 23)  # 23增量

    items = {item["source_id"]: item for item in diff_data["diff_items"]}
    assert items["sys"]["diff_type"] == "MODIFIED"
    assert items["mem_1"]["diff_type"] == "UNCHANGED"
    assert items["tool_old"]["diff_type"] == "REMOVED"
    assert items["mcp_new"]["diff_type"] == "ADDED"
