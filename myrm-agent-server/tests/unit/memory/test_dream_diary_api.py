"""Unit tests for Dream Diary and Surgical Memory Unlearning API endpoints.

Tests route handling, cross-session idle dreaming consolidation execution,
human review feedback submission, and precision session memory unlearning.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

from app.api.memory.dream_diary import router as dream_diary_router
from app.api.memory.dream_diary import unlearn_router


@pytest.fixture
def app_client() -> FastAPI:
    """Create lightweight test FastAPI instance mounting dream diary routers."""
    test_app = FastAPI()
    test_app.include_router(dream_diary_router)
    test_app.include_router(unlearn_router)
    return test_app


@pytest.mark.asyncio
async def test_dream_diary_run_and_query_flow(app_client: FastAPI) -> None:
    transport = httpx.ASGITransport(app=app_client)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Trigger dreaming run
        run_payload = {
            "fragments": [
                {
                    "session_id": "sess_101",
                    "memories": [
                        {
                            "content": "User prefers FastAPI over Flask for async microservices",
                            "confidence": 0.85,
                            "evidence": [{"quote_snippet": "Always build with FastAPI"}],
                        }
                    ],
                    "topic_keywords": ["fastapi", "async"],
                    "chat_turn_count": 6,
                },
                {
                    "session_id": "sess_102",
                    "memories": [
                        {
                            "content": "User builds async microservices with FastAPI",
                            "confidence": 0.9,
                            "evidence": [{"quote_snippet": "Microservices in FastAPI"}],
                        }
                    ],
                    "topic_keywords": ["fastapi"],
                    "chat_turn_count": 4,
                },
            ]
        }
        res_run = await client.post("/dream-diary/run", json=run_payload)
        assert res_run.status_code == 200
        run_data = res_run.json()
        assert run_data["status"] == "success"
        assert run_data["generated_count"] >= 1
        entry = run_data["entries"][0]
        entry_id = entry["entry_id"]
        assert "FastAPI" in entry["cognitive_statement"]

        # 2. Query list
        res_list = await client.get("/dream-diary")
        assert res_list.status_code == 200
        list_data = res_list.json()
        assert list_data["count"] >= 1

        # 3. Query single entry
        res_single = await client.get(f"/dream-diary/{entry_id}")
        assert res_single.status_code == 200
        single_data = res_single.json()
        assert single_data["entry"]["entry_id"] == entry_id

        # 4. Submit feedback (accept)
        res_fb = await client.post(
            f"/dream-diary/{entry_id}/feedback",
            json={"action": "accept"},
        )
        assert res_fb.status_code == 200
        fb_data = res_fb.json()
        assert fb_data["entry"]["status"] == "accepted"


@pytest.mark.asyncio
async def test_dream_diary_feedback_rejection_and_404(app_client: FastAPI) -> None:
    transport = httpx.ASGITransport(app=app_client)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Non-existent entry
        res_404 = await client.get("/dream-diary/non_existent_id")
        assert res_404.status_code == 404

        res_fb_404 = await client.post(
            "/dream-diary/non_existent_id/feedback",
            json={"action": "reject", "reason": "Not true"},
        )
        assert res_fb_404.status_code == 404

        # Invalid filter query
        res_bad_filter = await client.get("/dream-diary?status=invalid_status")
        assert res_bad_filter.status_code == 400


@pytest.mark.asyncio
async def test_surgical_unlearn_session_endpoint(app_client: FastAPI) -> None:
    transport = httpx.ASGITransport(app=app_client)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "memory_items": [
                {"id": "mem_purge_1", "session_id": "target_leak_session"},
                {"id": "mem_purge_2", "metadata": {"session_id": "target_leak_session"}},
                {"id": "mem_keep_3", "session_id": "safe_session"},
            ],
            "chat_turn_count": 8,
        }
        res_unlearn = await client.post(
            "/sessions/target_leak_session/unlearn", json=payload
        )
        assert res_unlearn.status_code == 200
        unlearn_data = res_unlearn.json()
        assert unlearn_data["status"] == "success"
        report = unlearn_data["report"]
        assert report["session_id"] == "target_leak_session"
        assert set(report["unlearned_memory_ids"]) == {"mem_purge_1", "mem_purge_2"}
        assert report["purged_vector_count"] == 2
        assert report["preserved_chat_turns"] == 8
        assert report["status"] == "completed"
