"""[POS]: tests/api/memory/test_noise_free_memory_api.py
[INPUT]: None.
[OUTPUT]: Comprehensive integration tests for noise-free memory extraction, PII screening, and purge epoch fencing API endpoints.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.noise_free_memory_router import (
    router as noise_free_memory_router,
)
from app.services.memory.noise_free_memory_service import (
    get_noise_free_memory_service,
)


@pytest.fixture
def test_app() -> FastAPI:
    """Create isolated FastAPI app mounting noise-free memory router."""
    api_app = FastAPI()
    api_app.include_router(noise_free_memory_router, prefix="/api/memory")
    return api_app


@pytest.fixture(autouse=True)
def reset_service() -> None:
    """Reset noise free service state between test cases."""
    service = get_noise_free_memory_service()
    # Reset internal facts and generations
    service._extractor._facts_store.clear()
    service._extractor.epoch_manager._user_generations.clear()
    service._extractor.epoch_manager._stale_drops.clear()
    service._extractor.epoch_manager._pii_blocked_counts.clear()


@pytest.mark.asyncio
async def test_clean_dialogue_api(test_app: FastAPI) -> None:
    """Verify tool noise stripping from conversation turns via API."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "user_id": "test_user_01",
            "turns": [
                {"role": "user", "content": "我想订明早去上海的高铁，二等座。"},
                {
                    "role": "assistant",
                    "content": "正在为您查询班次...\n```json\n{\"train\": \"G102\", \"price\": 550}\n```",
                    "tool_calls": [{"name": "search_trains", "args": "{}"}],
                },
                {
                    "role": "tool",
                    "content": "{\"result\": \"success\", \"seats\": 5}",
                    "tool_call_id": "call_train_1",
                },
                {"role": "assistant", "content": "已为您找到 G102 次列车，二等座余票充足。"},
            ],
        }
        resp = await client.post("/api/memory/noise-free/clean-dialogue", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == "test_user_01"
        assert data["observed_generation"] == 1
        assert "二等座" in data["clean_transcript"]
        assert "G102" not in data["clean_transcript"] or "```json" not in data["clean_transcript"]
        assert data["stripped_turns_count"] == 1
        assert data["tokens_saved"] > 0


@pytest.mark.asyncio
async def test_inspect_pii_api(test_app: FastAPI) -> None:
    """Verify PII regular expression screening catches sensitive card numbers and tokens."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Safe statement
        resp_safe = await client.post(
            "/api/memory/noise-free/inspect-pii",
            json={"statement": "用户喜欢深色模式并偏好 Python 语言。", "mask_instead_of_reject": False},
        )
        assert resp_safe.status_code == 200
        assert resp_safe.json()["is_clean"] is True
        assert len(resp_safe.json()["violations"]) == 0

        # Credit Card statement (Luhn-compliant card)
        resp_cc = await client.post(
            "/api/memory/noise-free/inspect-pii",
            json={"statement": "用户的卡号是 4111 1111 1111 1111", "mask_instead_of_reject": False},
        )
        assert resp_cc.status_code == 200
        data_cc = resp_cc.json()
        assert data_cc["is_clean"] is False
        assert any(v["rule_name"] == "credit_card" for v in data_cc["violations"])

        # Masking mode
        resp_mask = await client.post(
            "/api/memory/noise-free/inspect-pii",
            json={
                "statement": "密码是 password: secret_12345678",
                "mask_instead_of_reject": True,
            },
        )
        assert resp_mask.status_code == 200
        data_mask = resp_mask.json()
        assert "[plaintext_credential_REDACTED]" in data_mask["sanitized_text"]


@pytest.mark.asyncio
async def test_commit_fact_and_epoch_fence_api(test_app: FastAPI) -> None:
    """Verify epoch fencing rejects stale generation writes after user purge."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        user_id = "user_epoch_test"

        # 1. Commit valid fact in generation 1
        commit_payload = {
            "user_id": user_id,
            "candidate": {
                "fact_id": "fact_01",
                "fact_text": "用户常驻北京，喜欢周末徒步。",
                "category": "lifestyle",
                "confidence": 0.95,
                "generation_observed": 1,
            },
        }
        resp_commit = await client.post("/api/memory/noise-free/commit-fact", json=commit_payload)
        assert resp_commit.status_code == 200
        assert resp_commit.json()["success"] is True

        # Check facts list
        resp_facts = await client.get(f"/api/memory/noise-free/facts?user_id={user_id}")
        assert resp_facts.status_code == 200
        assert len(resp_facts.json()) == 1

        # 2. User purges memory -> Generation bumps to 2
        resp_purge = await client.post("/api/memory/noise-free/purge", json={"user_id": user_id})
        assert resp_purge.status_code == 200
        purge_data = resp_purge.json()
        assert purge_data["new_generation"] == 2
        assert purge_data["purged_facts_count"] == 1

        # Verify facts empty
        resp_facts_after = await client.get(f"/api/memory/noise-free/facts?user_id={user_id}")
        assert len(resp_facts_after.json()) == 0

        # 3. Stale async task attempts commit with old generation 1 -> Dropped!
        stale_payload = {
            "user_id": user_id,
            "candidate": {
                "fact_id": "fact_stale_ghost",
                "fact_text": "用户曾在北京租房住海淀区。",
                "category": "profile",
                "confidence": 0.9,
                "generation_observed": 1,
            },
        }
        resp_stale = await client.post("/api/memory/noise-free/commit-fact", json=stale_payload)
        assert resp_stale.status_code == 200
        assert resp_stale.json()["success"] is False
        assert "Stale generation write dropped" in resp_stale.json()["message"]

        # 4. Check status
        resp_status = await client.get(f"/api/memory/noise-free/status?user_id={user_id}")
        assert resp_status.status_code == 200
        status_data = resp_status.json()
        assert status_data["current_generation"] == 2
        assert status_data["stale_writes_dropped"] == 1
        assert status_data["stored_facts_count"] == 0
