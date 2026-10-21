"""Integration tests for onboarding insight sampling and first-encounter report API endpoints.

[POS]
历史会话轻量采样与“初见报告” REST API 集成测试套件。
验证外部 Agent 目录探测、多源关键帧滑动提取、初见报告生成与用户勾选批量原子入库。

[INPUT]
- FastAPI AsyncClient 与模拟外部 Agent 会话文件
- app.api.memory.onboarding 路由与 OnboardingInsightService

[OUTPUT]
- 严格断言 HTTP 状态码、初见报告 DTO 契约、事实指纹幂等去重与错误回退
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.toolkits.memory.onboarding.adapters import CursorSourceAdapter

from app.api.memory.onboarding import router as onboarding_router
from app.services.memory.onboarding import get_onboarding_insight_service


@pytest.fixture
def test_app() -> FastAPI:
    """Create isolated FastAPI app mounting onboarding insight router."""
    api_app = FastAPI()
    api_app.include_router(onboarding_router, prefix="/api/memory")
    return api_app


@pytest.fixture(autouse=True)
def reset_service() -> None:
    """Reset service in-memory collections before each test."""
    service = get_onboarding_insight_service()
    service._reports_cache.clear()
    service._ingested_fingerprints.clear()


@pytest.mark.asyncio
async def test_onboarding_scan_sources(test_app: FastAPI) -> None:
    """Verify scanning host machine for external agent source directories."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/memory/onboarding/scan-sources", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert "sources" in data
        assert "total_detected" in data
        assert isinstance(data["sources"], list)
        source_ids = [s["source_id"] for s in data["sources"]]
        assert "cursor" in source_ids
        assert "claude_code" in source_ids


@pytest.mark.asyncio
async def test_onboarding_generate_report_and_distill(test_app: FastAPI, tmp_path: Path) -> None:
    """Verify sampling conversation files and generating structured first-encounter report."""
    service = get_onboarding_insight_service()

    # Setup mock cursor session file
    mock_cursor_dir = tmp_path / "cursor_chats"
    mock_cursor_dir.mkdir(parents=True)
    session_file = mock_cursor_dir / "session_alpha.json"
    session_data = {
        "messages": [
            {
                "role": "user",
                "text": "In this project, always use Pydantic v2 with strict type validation.",
                "createdAt": "2026-10-07T10:00:00Z",
            },
            {
                "role": "assistant",
                "text": "Resolved by using HTTP 206 partial content streaming for clips.",
                "createdAt": "2026-10-07T10:01:00Z",
            },
            {
                "role": "user",
                "text": "We are currently working on memory onboarding pipelines.",
                "createdAt": "2026-10-07T10:02:00Z",
            },
        ]
    }
    session_file.write_text(json.dumps(session_data), encoding="utf-8")

    # Register temporary adapter pointing to mock directory
    service._registry.register(CursorSourceAdapter(base_dir=mock_cursor_dir))

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        generate_payload = {
            "target_sources": ["cursor"],
            "max_sessions_per_source": 5,
            "enable_entropy_inspection": True,
        }
        resp = await client.post("/api/memory/onboarding/generate-report", json=generate_payload)
        assert resp.status_code == 200
        data = resp.json()

        assert "report_id" in data
        assert data["scanned_session_count"] >= 1
        assert "cursor" in data["probed_sources"]
        assert len(data["facts"]) >= 3

        categories = {f["category"] for f in data["facts"]}
        assert "tech_stack_preference" in categories
        assert "hard_learned_lesson" in categories
        assert "active_project_goal" in categories


@pytest.mark.asyncio
async def test_onboarding_confirm_ingest_and_deduplication(test_app: FastAPI, tmp_path: Path) -> None:
    """Verify confirming insight facts ingestion with idempotency deduplication."""
    service = get_onboarding_insight_service()

    # Setup mock session
    mock_dir = tmp_path / "chats"
    mock_dir.mkdir(parents=True)
    sample_file = mock_dir / "s1.json"
    sample_file.write_text(
        json.dumps({
            "messages": [
                {"role": "user", "text": "We prefer FastAPI over Flask.", "createdAt": "2026-10-07"},
                {"role": "assistant", "text": "Discovered pitfall: do not mutate shared state.", "createdAt": "2026-10-07"},
            ]
        }),
        encoding="utf-8",
    )
    service._registry.register(CursorSourceAdapter(base_dir=mock_dir))

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Step 1: Generate report
        gen_resp = await client.post(
            "/api/memory/onboarding/generate-report",
            json={"target_sources": ["cursor"]},
        )
        assert gen_resp.status_code == 200
        report_data = gen_resp.json()
        report_id = report_data["report_id"]
        facts = report_data["facts"]
        assert len(facts) >= 2

        # Step 2: Confirm ingest all
        confirm_resp = await client.post(
            "/api/memory/onboarding/confirm-ingest",
            json={"report_id": report_id, "selected_fact_ids": []},
        )
        assert confirm_resp.status_code == 200
        confirm_data = confirm_resp.json()
        assert confirm_data["status"] == "ok"
        assert confirm_data["ingested_count"] == len(facts)
        assert confirm_data["skipped_count"] == 0

        # Step 3: Repeated confirm should skip due to deduplication fingerprint
        confirm_again = await client.post(
            "/api/memory/onboarding/confirm-ingest",
            json={"report_id": report_id, "selected_fact_ids": []},
        )
        assert confirm_again.status_code == 200
        again_data = confirm_again.json()
        assert again_data["ingested_count"] == 0
        assert again_data["skipped_count"] == len(facts)


@pytest.mark.asyncio
async def test_onboarding_confirm_ingest_missing_report(test_app: FastAPI) -> None:
    """Verify that confirming with an invalid report ID returns a safe error status."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/memory/onboarding/confirm-ingest",
            json={"report_id": "non_existent_report", "selected_fact_ids": []},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "report_not_found"
        assert data["ingested_count"] == 0
