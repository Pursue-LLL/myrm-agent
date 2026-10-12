"""Integration tests for Natural Language Memory Feedback and Live Correction API.

[POS]
Server-side integration test suite verifying conversational correction detection,
candidate conflict localization, atomic memory state mutations, and receipt generation.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.live_correction_router import (
    router as live_correction_router,
)
from app.services.memory.live_correction_service import (
    get_live_correction_service,
)


@pytest.fixture
def test_app() -> FastAPI:
    """Create isolated FastAPI app mounting live correction router."""
    api_app = FastAPI()
    api_app.include_router(live_correction_router, prefix="/api/memory")
    return api_app


@pytest.fixture(autouse=True)
def reset_service() -> None:
    """Reset live correction service state to default seeds before each test."""
    service = get_live_correction_service()
    service.clear_all()
    service.seed_default_candidates()


@pytest.mark.asyncio
async def test_process_preference_live_correction_api(test_app: FastAPI) -> None:
    """Verify live preference correction utterance supersedes matching candidate node."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "utterance": "我不喜欢美式咖啡，换成燕麦拿铁",
        }
        resp = await client.post("/api/memory/live-correction/process", json=payload)
        assert resp.status_code == 200
        data = resp.json()

        assert data["success"] is True
        assert data["intent"] == "preference_update"
        assert "燕麦拿铁" in data["ack_message"]
        assert data["slot"]["corrected_value"] == "燕麦拿铁"

        mutated = data["mutated_record"]
        assert mutated is not None
        assert mutated["action"] == "supersede"
        assert mutated["target_memory_id"] == "mem_pref_beverage"
        assert mutated["new_content"] == "燕麦拿铁"
        assert mutated["status"] == "applied"


@pytest.mark.asyncio
async def test_process_fact_superseded_api(test_app: FastAPI) -> None:
    """Verify factual supersession utterance updates architecture memory candidate."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "utterance": "其实主数据库并非 MySQL，而是 SQLite WAL",
        }
        resp = await client.post("/api/memory/live-correction/process", json=payload)
        assert resp.status_code == 200
        data = resp.json()

        assert data["success"] is True
        assert data["intent"] == "fact_superseded"
        assert data["slot"]["corrected_value"] == "SQLite WAL"

        mutated = data["mutated_record"]
        assert mutated is not None
        assert mutated["action"] == "supersede"
        assert mutated["target_memory_id"] == "mem_fact_database"
        assert mutated["new_content"] == "SQLite WAL"


@pytest.mark.asyncio
async def test_process_retraction_api(test_app: FastAPI) -> None:
    """Verify retracting sensitive memory candidate node."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "utterance": "删除关于 API Key 的记录",
        }
        resp = await client.post("/api/memory/live-correction/process", json=payload)
        assert resp.status_code == 200
        data = resp.json()

        assert data["success"] is True
        assert data["intent"] == "retract_mistake"
        assert "撤回" in data["ack_message"] or "Retracted" in data["ack_message"]

        mutated = data["mutated_record"]
        assert mutated is not None
        assert mutated["action"] == "retract"
        assert mutated["status"] == "retracted"


@pytest.mark.asyncio
async def test_unrecognized_utterance_422(test_app: FastAPI) -> None:
    """Verify normal conversational input with no correction triggers HTTP 422."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "utterance": "今天天气非常晴朗，阳光明媚",
        }
        resp = await client.post("/api/memory/live-correction/process", json=payload)
        assert resp.status_code == 422
        assert "No memory correction intent detected" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_candidates_and_history_lifecycle_api(test_app: FastAPI) -> None:
    """Verify listing candidates, seeding new candidate, viewing history, and resetting."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. List candidates
        resp_list = await client.get("/api/memory/live-correction/candidates")
        assert resp_list.status_code == 200
        candidates = resp_list.json()
        assert len(candidates) >= 4

        # 2. Seed a custom candidate
        resp_seed = await client.post(
            "/api/memory/live-correction/candidates",
            json={
                "memory_id": "mem_custom_editor",
                "content": "用户日常主要使用 VS Code 开发",
                "cube_id": "tools_pref",
                "attributes": {"category": "preference"},
            },
        )
        assert resp_seed.status_code == 201
        assert resp_seed.json()["memory_id"] == "mem_custom_editor"

        # 3. Correct the newly seeded candidate
        resp_corr = await client.post(
            "/api/memory/live-correction/process",
            json={"utterance": "我更喜欢 Neovim 而不是 VS Code"},
        )
        assert resp_corr.status_code == 200
        assert resp_corr.json()["mutated_record"]["target_memory_id"] == "mem_custom_editor"

        # 4. Check history
        resp_hist = await client.get("/api/memory/live-correction/history")
        assert resp_hist.status_code == 200
        hist_data = resp_hist.json()
        assert hist_data["total"] >= 1
        assert hist_data["history"][0]["new_content"] == "Neovim"

        # 5. Reset pool
        resp_reset = await client.post("/api/memory/live-correction/reset")
        assert resp_reset.status_code == 200
        assert resp_reset.json()["service_status"] == "reset_completed"
