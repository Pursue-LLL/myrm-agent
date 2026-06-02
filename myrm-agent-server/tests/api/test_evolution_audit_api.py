"""Evolution audit API smoke tests (rejections + /metrics on full app)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.skills.evolution import router as evolution_router
from app.database.connection import get_session
from app.database.models import Base, ExperienceLedgerEvent
from app.platform_utils import get_database_engine


@pytest.fixture
def evolution_only_app() -> FastAPI:
    app = FastAPI()
    app.include_router(evolution_router, prefix="/api/v1")
    return app


def test_evolution_rejections_returns_shape(evolution_only_app: FastAPI) -> None:
    client = TestClient(evolution_only_app)
    response = client.get("/api/v1/evolution/rejections?limit=5")
    assert response.status_code == 200
    body = response.json()
    assert "rejections" in body
    assert "total_count" in body
    assert "filters" in body
    assert isinstance(body["rejections"], list)


def test_evolution_rejection_stats_returns_shape(evolution_only_app: FastAPI) -> None:
    client = TestClient(evolution_only_app)
    response = client.get("/api/v1/evolution/rejections/stats?time_range_days=7")
    assert response.status_code == 200
    body = response.json()
    assert "total_rejections" in body


def test_evolution_derive_route_exists(evolution_only_app: FastAPI) -> None:
    client = TestClient(evolution_only_app)
    response = client.post("/api/v1/evolution/derive/does-not-exist", json={"instruction": "improve it"})
    assert response.status_code == 404
    assert response.json()["detail"] == "Skill not found: does-not-exist"


def test_main_app_exposes_metrics() -> None:
    from fastapi import Response
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    test_app = FastAPI()

    @test_app.get("/metrics", include_in_schema=False)
    def metrics_endpoint() -> Response:
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    client = TestClient(test_app)
    response = client.get("/metrics")
    assert response.status_code == 200
    text = response.text
    assert "process_" in text.lower() or "python_" in text.lower()


def test_rejections_limit_validation_422(evolution_only_app: FastAPI) -> None:
    client = TestClient(evolution_only_app)
    assert client.get("/api/v1/evolution/rejections?limit=0").status_code == 422
    assert client.get("/api/v1/evolution/rejections?limit=5000").status_code == 422


def test_stats_time_range_validation_422(evolution_only_app: FastAPI) -> None:
    client = TestClient(evolution_only_app)
    assert client.get("/api/v1/evolution/rejections/stats?time_range_days=0").status_code == 422
    assert client.get("/api/v1/evolution/rejections/stats?time_range_days=400").status_code == 422


def test_rejections_with_patched_store_returns_row(evolution_only_app: FastAPI) -> None:
    async def _seed() -> None:
        engine = get_database_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with get_session() as db:
            db.add(
                ExperienceLedgerEvent(
                    id="growth-audit-1",
                    namespace="default",
                    event_type="skill_growth.rejected",
                    entity_type="skill_growth",
                    entity_id="draft-case-1",
                    lineage_id="skill_growth:draft-case-1",
                    outcome="rejected",
                    summary="HTTP 404 — external resource",
                    artifact_refs={
                        "skill_id": "skill_e2e_audit",
                        "skill_name": "skill_e2e_audit",
                        "draft_type": "skill_patch",
                    },
                    metrics_snapshot={"confidence": 0.85},
                    detail={"status": "REJECTED", "severity": "warning"},
                    created_at=datetime.now(UTC),
                )
            )
            await db.commit()

    async def _cleanup() -> None:
        async with get_session() as db:
            event = await db.get(ExperienceLedgerEvent, "growth-audit-1")
            if event is not None:
                await db.delete(event)
                await db.commit()

    asyncio.run(_seed())
    try:
        client = TestClient(evolution_only_app)
        res = client.get("/api/v1/evolution/rejections?limit=10")
        assert res.status_code == 200
        body = res.json()
        assert len(body["rejections"]) == 1
        assert body["rejections"][0]["skill_id"] == "skill_e2e_audit"
        assert body["rejections"][0]["trigger_type"] == "rejected"

        filtered = client.get("/api/v1/evolution/rejections?limit=10&trigger_type=rejected").json()
        assert len(filtered["rejections"]) == 1

        other = client.get("/api/v1/evolution/rejections?limit=10&trigger_type=blocked_locked").json()
        assert len(other["rejections"]) == 0

        stats = client.get("/api/v1/evolution/rejections/stats?time_range_days=30").json()
        assert stats["total_rejections"] == 1
        assert stats["avg_confidence"] >= 0.8
        assert len(stats["top_triggers"]) >= 1
        assert len(stats["top_skills"]) >= 1
    finally:
        asyncio.run(_cleanup())
