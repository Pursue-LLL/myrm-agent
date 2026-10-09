"""Integration tests for Natural Language Memory Feedback and Live Correction API endpoints.

[POS]
Server-side integration test suite verifying intent detection, live memory correction execution,
candidate localization, mutation records, and user acknowledgement receipts.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.memory_feedback_router import (
    router as memory_feedback_router,
)


@pytest.fixture
def test_app() -> FastAPI:
    """Create isolated FastAPI app mounting memory feedback router."""
    api_app = FastAPI()
    api_app.include_router(memory_feedback_router, prefix="/api/memory")
    return api_app


@pytest.mark.asyncio
async def test_feedback_health_endpoint(test_app: FastAPI) -> None:
    """Verify health endpoint of memory feedback subsystem."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/memory/feedback/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["subsystem"] == "memory_live_correction"


@pytest.mark.asyncio
async def test_detect_correction_endpoint(test_app: FastAPI) -> None:
    """Verify detection and slot extraction endpoint."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Positive case: preference correction
        resp = await client.post(
            "/api/memory/feedback/detect",
            json={"utterance": "我更喜欢无糖乌龙茶而不是拿铁"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["detected"] is True
        assert data["intent"] == "preference_update"
        assert data["corrected_value"] == "无糖乌龙茶"
        assert data["negated_value"] == "拿铁"

        # 2. Negative case: normal conversation
        resp_neg = await client.post(
            "/api/memory/feedback/detect",
            json={"utterance": "请帮我解释一下什么是协程？"},
        )
        assert resp_neg.status_code == 200
        data_neg = resp_neg.json()
        assert data_neg["detected"] is False
        assert data_neg["intent"] is None


@pytest.mark.asyncio
async def test_execute_live_correction_with_candidate_api(test_app: FastAPI) -> None:
    """Verify end-to-end live correction execution against matching candidate."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "utterance": "我不喜欢拿铁，更喜欢无糖乌龙茶",
            "candidates": [
                {
                    "memory_id": "cand_drink_1",
                    "content": "用户常喝拿铁咖啡",
                    "cube_id": "cube_user_profile",
                    "match_score": 1.0,
                },
                {
                    "memory_id": "cand_ide_2",
                    "content": "用户使用 VS Code 开发",
                    "cube_id": "cube_user_profile",
                    "match_score": 1.0,
                },
            ],
        }
        resp = await client.post("/api/memory/feedback/live-correction", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["intent"] == "preference_update"
        assert "无糖乌龙茶" in data["ack_message"]
        assert data["mutation"] is not None
        assert data["mutation"]["action"] == "supersede"
        assert data["mutation"]["target_memory_id"] == "cand_drink_1"
        assert data["mutation"]["new_content"] == "无糖乌龙茶"


@pytest.mark.asyncio
async def test_execute_live_correction_fallback_api(test_app: FastAPI) -> None:
    """Verify fallback response when no correction intent is present."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "utterance": "今天下午三点开会",
            "candidates": [],
        }
        resp = await client.post("/api/memory/feedback/live-correction", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["intent"] == "none"
        assert data["mutation"] is None
