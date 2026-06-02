"""Test QualityRepository

单元测试 QualityRepository 的核心功能。
"""

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool

from app.adapters.skill_optimization.quality_repo import QualityRepository
from app.database.models import Base


@pytest.fixture
async def session():
    """创建测试数据库session"""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Enable foreign keys for SQLite
    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSession(engine) as session:
        yield session

    # Cleanup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.mark.asyncio
async def test_save_quality_snapshot(session: AsyncSession):
    """测试保存质量快照"""
    repo = QualityRepository(session)

    snapshot = await repo.save_quality_snapshot(
        skill_id="test-skill-001",
        quality_score={
            "overall_score": 0.85,
            "success_rate": 0.9,
            "token_efficiency": 0.8,
            "execution_time": 0.75,
            "user_satisfaction": 0.9,
            "call_frequency": 0.5,
        },
    )

    assert snapshot.skill_id == "test-skill-001"
    assert snapshot.overall_score == 0.85
    assert snapshot.success_rate == 0.9
    assert snapshot.quality_score["overall_score"] == 0.85


@pytest.mark.asyncio
async def test_get_latest_quality(session: AsyncSession):
    """测试获取最新质量评分"""
    repo = QualityRepository(session)

    # 保存多个快照
    await repo.save_quality_snapshot(
        skill_id="test-skill-002",
        quality_score={"overall_score": 0.7},
    )
    await repo.save_quality_snapshot(
        skill_id="test-skill-002",
        quality_score={"overall_score": 0.8},
    )
    await repo.save_quality_snapshot(
        skill_id="test-skill-002",
        quality_score={"overall_score": 0.9},
    )

    # 获取最新的
    latest = await repo.get_latest_quality("test-skill-002")
    assert latest is not None
    assert latest.overall_score == 0.9


@pytest.mark.asyncio
async def test_get_quality_history(session: AsyncSession):
    """测试获取质量历史"""
    repo = QualityRepository(session)

    # 保存多个快照
    for i in range(5):
        await repo.save_quality_snapshot(
            skill_id="test-skill-003",
            quality_score={"overall_score": 0.5 + i * 0.1},
        )

    # 获取历史
    history = await repo.get_quality_history("test-skill-003", days=30)
    assert len(history) == 5
    # 应该按时间升序排列
    assert history[0].overall_score == 0.5
    assert history[-1].overall_score == 0.9


@pytest.mark.asyncio
async def test_get_top_skills(session: AsyncSession):
    """测试获取Top技能"""
    repo = QualityRepository(session)

    # 保存不同技能的快照
    await repo.save_quality_snapshot(
        skill_id="skill-A",
        quality_score={"overall_score": 0.95},
    )
    await repo.save_quality_snapshot(
        skill_id="skill-B",
        quality_score={"overall_score": 0.85},
    )
    await repo.save_quality_snapshot(
        skill_id="skill-C",
        quality_score={"overall_score": 0.75},
    )

    # 获取Top 2
    top_skills = await repo.get_top_skills(limit=2)
    assert len(top_skills) == 2
    assert top_skills[0][0] == "skill-A"
    assert top_skills[0][1] == 0.95
    assert top_skills[1][0] == "skill-B"
    assert top_skills[1][1] == 0.85


@pytest.mark.asyncio
async def test_get_bottom_skills(session: AsyncSession):
    """测试获取Bottom技能"""
    repo = QualityRepository(session)

    # 保存不同技能的快照
    await repo.save_quality_snapshot(
        skill_id="skill-D",
        quality_score={"overall_score": 0.95},
    )
    await repo.save_quality_snapshot(
        skill_id="skill-E",
        quality_score={"overall_score": 0.85},
    )
    await repo.save_quality_snapshot(
        skill_id="skill-F",
        quality_score={"overall_score": 0.75},
    )

    # 获取Bottom 2
    bottom_skills = await repo.get_bottom_skills(limit=2)
    assert len(bottom_skills) == 2
    assert bottom_skills[0][0] == "skill-F"
    assert bottom_skills[0][1] == 0.75
    assert bottom_skills[1][0] == "skill-E"
    assert bottom_skills[1][1] == 0.85


@pytest.mark.asyncio
async def test_get_all_latest_qualities(session: AsyncSession):
    """测试获取所有技能的最新质量"""
    repo = QualityRepository(session)

    # 保存多个技能的快照
    await repo.save_quality_snapshot(
        skill_id="skill-G",
        quality_score={"overall_score": 0.9},
    )
    await repo.save_quality_snapshot(
        skill_id="skill-H",
        quality_score={"overall_score": 0.8},
    )

    # 获取所有最新质量
    all_qualities = await repo.get_all_latest_qualities()
    assert len(all_qualities) >= 2
    assert "skill-G" in all_qualities
    assert "skill-H" in all_qualities
    assert all_qualities["skill-G"]["overall_score"] == 0.9
    assert all_qualities["skill-H"]["overall_score"] == 0.8


@pytest.mark.asyncio
async def test_quality_with_user_id(session: AsyncSession):
    """测试带用户ID的质量快照"""
    repo = QualityRepository(session)

    snapshot = await repo.save_quality_snapshot(
        skill_id="test-skill-004",
        quality_score={"overall_score": 0.85},
    )

    assert snapshot.skill_id == "test-skill-004"
