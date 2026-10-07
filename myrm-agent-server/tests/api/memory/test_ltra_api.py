"""Integration and API unit tests for Listen-Translate-Remember-Act (LTRA) cognitive pipeline.

[POS]
随身感知“听—译—记—办” REST API 测试套件。端到端验证多说话人转录摄入、
四元组事实蒸馏、原话追问引用、沙箱工单闭环派发与 HTTP 206 音频切片流式回放。

[INPUT]
- FastAPI AsyncClient 与模拟多说话人时间戳切片

[OUTPUT]
- 严格断言 HTTP 状态码、事实四元组契约、派发幂等性与流式 Range 头字段
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.ltra import router as ltra_router
from app.services.memory.ltra import get_ltra_service


@pytest.fixture
def test_app() -> FastAPI:
    """Create isolated FastAPI app mounting LTRA cognitive router."""
    api_app = FastAPI()
    api_app.include_router(ltra_router, prefix="/api/memory")
    return api_app


@pytest.fixture(autouse=True)
def reset_service() -> None:
    """Reset service in-memory collections before each test."""
    service = get_ltra_service()
    with service._lock:
        service._facts.clear()
        service._dispatched_tasks.clear()
        service._idempotency_cache.clear()
        service._audio_store.clear()


@pytest.mark.asyncio
async def test_ltra_ingest_and_distill_pipeline(test_app: FastAPI) -> None:
    """Test ingesting multi-speaker conversation and verifying distilled facts."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "segments": [
                {
                    "speaker_id": "spk_0",
                    "text": "大家上午好，今天讨论一下新系统架构。",
                    "start_ms": 0,
                    "end_ms": 2500,
                    "confidence": 0.95,
                },
                {
                    "speaker_id": "spk_0",
                    "text": "我们核心诉求是支持离线私有化部署，担心内网升级复杂度太高，这是主要风险。",
                    "start_ms": 3000,
                    "end_ms": 9000,
                    "confidence": 0.98,
                },
                {
                    "speaker_id": "spk_1",
                    "text": "张总放心，我们承诺在两周内交付离线沙箱安装包与升级脚本，完全支持这个要求。",
                    "start_ms": 9500,
                    "end_ms": 16000,
                    "confidence": 0.94,
                },
            ],
            "audio_id": "rec_meeting_offline",
            "speaker_aliases": {
                "spk_0": "张总(客户决策人)",
                "spk_1": "我方架构师",
            },
            "project_id": "proj_offline_suite",
        }

        res = await client.post("/api/memory/ltra/ingest-transcript", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert data["processed_segments_count"] == 3
        assert data["distilled_facts_count"] >= 1

        fact = data["facts"][0]
        assert fact["subject"] == "张总(客户决策人)"
        assert "支持离线私有化部署" in fact["demand"]
        assert len(fact["anchors"]) == 1
        assert fact["anchors"][0]["start_ms"] == 3000
        assert fact["anchors"][0]["end_ms"] == 9000


@pytest.mark.asyncio
async def test_ltra_query_and_cite_flow(test_app: FastAPI) -> None:
    """Test querying facts by natural language question with verbatim citation."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Pre-seed via ingestion
        ingest_payload = {
            "segments": [
                {
                    "speaker_id": "spk_client",
                    "text": "我们必须支持微信与飞书双通道消息推送，难点在于需要审批权限。",
                    "start_ms": 1000,
                    "end_ms": 6000,
                    "confidence": 0.92,
                }
            ],
            "audio_id": "rec_msg_sync",
            "speaker_aliases": {"spk_client": "李总"},
            "project_id": "proj_im_bridge",
        }
        await client.post("/api/memory/ltra/ingest-transcript", json=ingest_payload)

        # Query
        query_payload = {
            "query": "微信 飞书 双通道",
            "project_id": "proj_im_bridge",
        }
        res_query = await client.post("/api/memory/ltra/query-and-cite", json=query_payload)
        assert res_query.status_code == 200
        query_data = res_query.json()
        assert query_data["matched_facts_count"] == 1
        assert query_data["facts"][0]["subject"] == "李总"
        assert query_data["suggested_task_draft"] is not None


@pytest.mark.asyncio
async def test_ltra_dispatch_task_and_idempotency(test_app: FastAPI) -> None:
    """Test dispatching task to sandbox with idempotency verification."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Pre-seed
        ingest_payload = {
            "segments": [
                {
                    "speaker_id": "spk_customer",
                    "text": "需要实现基于多因素认证的单点登录。",
                    "start_ms": 500,
                    "end_ms": 4000,
                }
            ],
            "audio_id": "rec_auth_sso",
            "speaker_aliases": {"spk_customer": "安全总监"},
        }
        res_ingest = await client.post("/api/memory/ltra/ingest-transcript", json=ingest_payload)
        fact_id = res_ingest.json()["facts"][0]["fact_id"]

        # Dispatch
        dispatch_payload = {
            "fact_id": fact_id,
            "target_agent_role": "身份安全专家",
        }
        res_dispatch_1 = await client.post("/api/memory/ltra/dispatch-task", json=dispatch_payload)
        assert res_dispatch_1.status_code == 200
        data_1 = res_dispatch_1.json()
        assert data_1["status"] == "dispatched"
        assert "安全总监" in data_1["title"]
        assert len(data_1["action_plan_steps"]) == 4

        # Dispatch again (idempotent duplicate should return existing blueprint)
        res_dispatch_2 = await client.post("/api/memory/ltra/dispatch-task", json=dispatch_payload)
        assert res_dispatch_2.status_code == 200
        data_2 = res_dispatch_2.json()
        assert data_2["task_id"] == data_1["task_id"]
        assert data_2["idempotency_token"] == data_1["idempotency_token"]


@pytest.mark.asyncio
async def test_ltra_audio_slice_stream_http_206(test_app: FastAPI) -> None:
    """Test HTTP 206 Partial Content audio slice range streaming."""
    service = get_ltra_service()
    service.store_audio_bytes("rec_sample_audio", b"\x00" * 32000)  # 32KB simulated audio

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/memory/ltra/audio/rec_sample_audio/clip?start_ms=100&end_ms=300")
        assert res.status_code == 206
        assert "bytes" in res.headers["Accept-Ranges"]
        assert "Content-Range" in res.headers
        assert len(res.content) > 0

        # Invalid range (end <= start) returns 400
        res_invalid = await client.get("/api/memory/ltra/audio/rec_sample_audio/clip?start_ms=500&end_ms=200")
        assert res_invalid.status_code == 400


@pytest.mark.asyncio
async def test_ltra_nonexistent_fact_dispatch_404(test_app: FastAPI) -> None:
    """Test dispatching nonexistent fact returns 404."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/memory/ltra/dispatch-task",
            json={"fact_id": "nonexistent_fact_999"},
        )
        assert res.status_code == 404
