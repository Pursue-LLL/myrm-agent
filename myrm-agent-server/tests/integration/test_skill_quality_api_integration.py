"""Integration tests for Skill Quality Aggregation API.

Tests the complete DataSource Pattern stack:
SkillQualityHistory → SQLSkillQualityDataSource → UniversalAggregator → API → Response

Validates:
1. Data write and read integrity
2. Aggregation correctness
3. API response format
4. Time range filtering

5. Trends endpoints (SQLite strftime grouping)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.models.skill_optimization.skill_quality_history import SkillQualityHistory


@pytest.fixture
async def test_db():
    """Create an in-memory SQLite database for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(SkillQualityHistory.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    yield session_factory

    await engine.dispose()


def _make_record(
    skill_id: str,
    overall_score: float,
    success_rate: float,
    token_efficiency: float,
    execution_time: float,
    recorded_at: datetime,
) -> SkillQualityHistory:
    return SkillQualityHistory(
        id=str(uuid.uuid4()),
        skill_id=skill_id,
        overall_score=overall_score,
        success_rate=success_rate,
        token_efficiency=token_efficiency,
        execution_time=execution_time,
        user_satisfaction=0.9,
        call_frequency=1.0,
        quality_score={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        recorded_at=recorded_at,
    )


@pytest.fixture
async def populated_db(test_db: async_sessionmaker):
    """Populate test database with sample quality history records."""
    base_time = datetime.now() - timedelta(days=10)

    records = [
        _make_record("skill-1", 0.95, 0.98, 0.92, 1.2, base_time + timedelta(days=1)),
        _make_record("skill-1", 0.93, 0.96, 0.90, 1.5, base_time + timedelta(days=2)),
        _make_record("skill-2", 0.75, 0.80, 0.70, 2.0, base_time + timedelta(days=3)),
        _make_record("skill-2", 0.78, 0.82, 0.72, 1.8, base_time + timedelta(days=4)),
        _make_record("skill-3", 0.88, 0.90, 0.85, 1.3, base_time + timedelta(days=5)),
    ]

    async with test_db() as session:
        session.add_all(records)
        await session.commit()

    return test_db


@pytest.fixture
def test_client(populated_db: async_sessionmaker, monkeypatch):
    """Create a test client with mocked session_factory and db_session."""
    from fastapi.testclient import TestClient

    from app.main import app

    monkeypatch.setattr("app.platform_utils.get_session_factory", lambda: populated_db)
    monkeypatch.setattr("app.database.connection.get_session_factory", lambda: populated_db)
    monkeypatch.setattr("app.database.repositories.uow.get_session_factory", lambda: populated_db)

    async def mock_get_db_session():
        async with populated_db() as session:
            yield session

    monkeypatch.setattr("app.api.skills.quality.get_db_session", mock_get_db_session)

    yield TestClient(app)


def test_global_metrics(test_client):
    """Test GET /api/v1/skill-quality/metrics/global."""
    response = test_client.get("/api/v1/skill-quality/metrics/global?time_range_days=30")
    assert response.status_code == 200, f"API failed: {response.text}"

    data = response.json()
    assert data["total_executions"] == 5
    assert data["total_skills"] == 3
    assert data["total_users"] == 1
    assert 0.85 <= data["avg_quality_score"] <= 0.87


def test_skill_specific_metrics(test_client):
    """Test GET /api/v1/skill-quality/metrics/skill/{skill_id}."""
    response = test_client.get("/api/v1/skill-quality/metrics/skill/skill-1?time_range_days=30")
    assert response.status_code == 200

    data = response.json()
    assert data["skill_id"] == "skill-1"
    assert data["total_executions"] == 2
    assert 0.93 <= data["avg_quality_score"] <= 0.95


def test_user_specific_metrics(test_client):
    """Test GET /api/v1/skill-quality/metrics/user (no user_id param after refactoring)."""
    response = test_client.get("/api/v1/skill-quality/metrics/user?time_range_days=30")
    assert response.status_code == 200

    data = response.json()
    assert data["user_id"] == "default"
    assert data["total_executions"] == 5
    assert data["unique_skills_used"] == 3


def test_quality_percentiles(test_client):
    """Test GET /api/v1/skill-quality/metrics/percentiles."""
    response = test_client.get("/api/v1/skill-quality/metrics/percentiles")
    assert response.status_code == 200

    data = response.json()
    for key in ("p50", "p90", "p95", "p99"):
        assert key in data
        assert 0.0 <= data[key] <= 1.0


def test_global_trends(test_client):
    """Test GET /api/v1/skill-quality/trends/global."""
    response = test_client.get("/api/v1/skill-quality/trends/global?time_range_days=30")
    assert response.status_code == 200

    data = response.json()
    assert "data_points" in data
    assert "time_range_days" in data
    assert data["time_range_days"] == 30

    for point in data["data_points"]:
        assert "timestamp" in point
        assert "avg_quality_score" in point
        assert "avg_success_rate" in point
        assert "execution_count" in point


def test_skill_trends(test_client):
    """Test GET /api/v1/skill-quality/trends/skill/{skill_id}."""
    response = test_client.get("/api/v1/skill-quality/trends/skill/skill-1?time_range_days=30")
    assert response.status_code == 200

    data = response.json()
    assert data["skill_id"] == "skill-1"
    assert "data_points" in data
    assert data["time_range_days"] == 30


def test_time_range_filtering(test_client):
    """Test time range filtering works correctly."""
    r_short = test_client.get("/api/v1/skill-quality/metrics/global?time_range_days=3")
    r_long = test_client.get("/api/v1/skill-quality/metrics/global?time_range_days=30")
    assert r_short.status_code == 200
    assert r_long.status_code == 200

    assert r_long.json()["total_executions"] >= r_short.json()["total_executions"]


def test_nonexistent_skill_returns_404(test_client):
    """Test querying non-existent skill returns 404."""
    response = test_client.get("/api/v1/skill-quality/metrics/skill/nonexistent?time_range_days=30")
    assert response.status_code == 404


def test_user_metrics_returns_data(test_client):
    """Test querying default user returns data (user_id is no longer a path param)."""
    response = test_client.get("/api/v1/skill-quality/metrics/user?time_range_days=30")
    assert response.status_code == 200


def test_trends_empty_data(test_client):
    """Test trends endpoint returns empty data_points for skill with no data."""
    response = test_client.get("/api/v1/skill-quality/trends/skill/no-such-skill?time_range_days=30")
    assert response.status_code == 200

    data = response.json()
    assert data["data_points"] == []
    assert data["skill_id"] == "no-such-skill"
