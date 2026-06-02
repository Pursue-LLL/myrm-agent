"""Tests for SQLSkillQualityDataSource"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adapters.skill_optimization import SQLSkillQualityDataSource
from app.database.models import Base
from app.database.models.skill_optimization import SkillQualityHistory


@pytest.fixture
async def engine():
    """Create test database engine"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session_factory(engine):
    """Create session factory"""
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
async def populated_db(session_factory):
    """Populate test database with sample data"""
    async with session_factory() as session:
        now = datetime.now()

        records = [
            SkillQualityHistory(
                id=f"test-{i}",
                skill_id="web_search",
                overall_score=0.85 + i * 0.01,
                success_rate=0.9,
                token_efficiency=0.8,
                execution_time=2.5,
                user_satisfaction=0.88,
                call_frequency=0.7,
                quality_score={
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                    "total_tokens": 150,
                    "llm_cost_usd": 0.001,
                },
                recorded_at=now - timedelta(days=i),
            )
            for i in range(10)
        ]

        records.extend(
            [
                SkillQualityHistory(
                    id=f"test-pdf-{i}",
                    skill_id="pdf_generator",
                    overall_score=0.92,
                    success_rate=0.95,
                    token_efficiency=0.85,
                    execution_time=3.0,
                    user_satisfaction=0.9,
                    call_frequency=0.6,
                    quality_score={
                        "prompt_tokens": 200,
                        "completion_tokens": 100,
                        "total_tokens": 300,
                        "llm_cost_usd": 0.002,
                    },
                    recorded_at=now - timedelta(days=i),
                )
                for i in range(5)
            ]
        )

        for record in records:
            session.add(record)
        await session.commit()


@pytest.mark.asyncio
async def test_query_raw_records_all(session_factory, populated_db):
    """Test querying all records"""
    data_source = SQLSkillQualityDataSource(session_factory)
    records = await data_source.query_raw_records(time_range_days=30)

    assert len(records) == 15
    assert all(hasattr(r, "id") for r in records)
    assert all(hasattr(r, "skill_id") for r in records)
    assert all(hasattr(r, "overall_score") for r in records)


@pytest.mark.asyncio
async def test_query_raw_records_by_skill(session_factory, populated_db):
    """Test querying records filtered by skill_id"""
    data_source = SQLSkillQualityDataSource(session_factory)
    records = await data_source.query_raw_records(skill_id="web_search", time_range_days=30)

    assert len(records) == 10
    assert all(r.skill_id == "web_search" for r in records)


@pytest.mark.asyncio
async def test_query_raw_records_time_range(session_factory, populated_db):
    """Test querying records with time range filter"""
    data_source = SQLSkillQualityDataSource(session_factory)
    records = await data_source.query_raw_records(time_range_days=5)

    assert len(records) == 10
    assert all((datetime.now() - r.recorded_at).days <= 5 for r in records)


@pytest.mark.asyncio
async def test_query_aggregated_not_implemented(session_factory, populated_db):
    """Test query_aggregated returns empty list (not implemented)"""
    data_source = SQLSkillQualityDataSource(session_factory)
    result = await data_source.query_aggregated(group_by="skill_id", time_range_days=30)

    assert result == []


@pytest.mark.asyncio
async def test_orm_to_snapshot_conversion(session_factory, populated_db):
    """Test ORM to Snapshot conversion"""
    data_source = SQLSkillQualityDataSource(session_factory)
    records = await data_source.query_raw_records(skill_id="web_search", time_range_days=30)

    snapshot = records[0]

    assert snapshot.id.startswith("test-")
    assert snapshot.skill_id == "web_search"
    assert 0.85 <= snapshot.overall_score <= 0.95
    assert snapshot.success_rate == 0.9
    assert snapshot.token_efficiency == 0.8
    assert snapshot.execution_time == 2.5
    assert snapshot.user_satisfaction == 0.88
    assert snapshot.prompt_tokens == 100
    assert snapshot.completion_tokens == 50
    assert snapshot.total_tokens == 150
    assert snapshot.llm_cost_usd == 0.001
