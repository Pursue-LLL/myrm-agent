"""[POS]: tests/api/memory/test_context_ingestion_api.py
[INPUT]: FastAPI TestClient, isolated UniversalContextIngestionGateway, and ingestion endpoints.
[OUTPUT]: Pytest integration tests verifying universal ingest, Plaud webhook, history, and format queries.
"""

import json
from collections.abc import AsyncGenerator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.toolkits.memory import (
    UniversalContextIngestionGateway,
)

from app.api.memory.context_ingestion import (
    get_context_ingestion_gateway,
)
from app.api.memory.context_ingestion import (
    router as context_ingestion_router,
)


@pytest.fixture
def isolated_gateway() -> UniversalContextIngestionGateway:
    """Create isolated UniversalContextIngestionGateway with in-memory SQLite database."""
    return UniversalContextIngestionGateway(db_path=":memory:")


@pytest.fixture
def test_app(isolated_gateway: UniversalContextIngestionGateway) -> FastAPI:
    """Create FastAPI test application with injected isolated gateway."""
    api_app = FastAPI()
    api_app.include_router(context_ingestion_router, prefix="/api/memory")
    api_app.dependency_overrides[get_context_ingestion_gateway] = lambda: isolated_gateway
    return api_app


@pytest.fixture
async def client(test_app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client fixture bound to the isolated test app."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_ingest_raw_transcript_and_deduplication(client: AsyncClient) -> None:
    """Verify ingesting raw transcript and idempotency skip on duplicate."""
    raw_text = """Alice: 确定使用方案B作为生产标准。
Alice: Bob负责本周五前完成基准测试与报告。
Bob: 收到，没问题。
"""
    payload = {
        "source_type": "raw_transcript",
        "device_id": "test_device_001",
        "title": "方案研讨会",
        "raw_payload": raw_text,
    }

    # 1. First Ingestion
    resp1 = await client.post("/api/memory/ingestion/ingest", json=payload)
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["title"] == "方案研讨会"
    assert data1["is_duplicate"] is False
    assert data1["speaker_count"] == 2
    assert len(data1["decisions"]) >= 1
    assert any("确定" in d for d in data1["decisions"])
    assert len(data1["action_items"]) >= 1
    assert any("负责" in a for a in data1["action_items"])

    # 2. Second Ingestion (exact duplicate)
    resp2 = await client.post("/api/memory/ingestion/ingest", json=payload)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["is_duplicate"] is True
    assert data2["fingerprint"] == data1["fingerprint"]
    assert "Skipped duplicate" in data2["summary"]


@pytest.mark.asyncio
async def test_plaud_webhook_sync(client: AsyncClient) -> None:
    """Verify handling Plaud hardware voice card cloud webhook event."""
    plaud_data = {
        "transcription": [
            {
                "speaker": "Team Lead",
                "start_time": 0.0,
                "end_time": 4.5,
                "content": "Good morning. We agreed to prioritize the memory repair suite.",
                "confidence": 0.99,
            },
            {
                "speaker": "Engineer",
                "start_time": 5.0,
                "end_time": 9.0,
                "content": "Understood. I will do the test suite implementation today.",
                "confidence": 0.98,
            },
        ]
    }

    webhook_payload = {
        "device_id": "plaud_sn_882910",
        "meeting_title": "Daily Standup Meeting",
        "transcription_json": json.dumps(plaud_data),
        "tags": {"project": "myrm"},
    }

    resp = await client.post("/api/memory/ingestion/webhook/plaud", json=webhook_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Daily Standup Meeting"
    assert data["source_type"] == "plaud_voice_card"
    assert data["speaker_count"] == 2
    assert data["is_duplicate"] is False
    assert len(data["decisions"]) >= 1
    assert "agreed" in data["decisions"][0]
    assert len(data["action_items"]) >= 1
    assert "will do" in data["action_items"][0]


@pytest.mark.asyncio
async def test_ingestion_history_and_supported_formats(client: AsyncClient) -> None:
    """Verify listing history records and querying supported formats."""
    # 1. Ingest a transcript
    await client.post(
        "/api/memory/ingestion/ingest",
        json={
            "source_type": "raw_transcript",
            "device_id": "phone_mic",
            "title": "One on One Review",
            "raw_payload": "Manager: Next step is release planning.\nMember: Noted.",
        },
    )

    # 2. Get history
    hist_resp = await client.get("/api/memory/ingestion/history?limit=10")
    assert hist_resp.status_code == 200
    hist_data = hist_resp.json()
    assert hist_data["total"] >= 1
    assert hist_data["items"][0]["title"] == "One on One Review"

    # 3. Get supported formats
    fmt_resp = await client.get("/api/memory/ingestion/supported-formats")
    assert fmt_resp.status_code == 200
    fmt_data = fmt_resp.json()
    assert "plaud_voice_card" in fmt_data["formats"]
    assert "webvtt" in fmt_data["formats"]
    assert "srt" in fmt_data["formats"]
    assert len(fmt_data["description"]) >= 4
