"""Test OptimizationRepository

单元测试 OptimizationRepository 的核心功能。
"""

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool

from app.adapters.skill_optimization.optimization_repo import OptimizationRepository
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
async def test_create_optimization_record(session: AsyncSession):
    """测试创建优化记录"""
    repo = OptimizationRepository(session)

    record = await repo.create(
        skill_id="test-skill-001",
        skill_type="USER",
        baseline_score={"overall_score": 0.75, "success_rate": 0.8},
        skill_version=1,
    )

    assert record.skill_id == "test-skill-001"
    assert record.skill_type == "USER"
    assert record.baseline_score["overall_score"] == 0.75
    assert record.status == "PENDING"
    assert record.skill_version == 1


@pytest.mark.asyncio
async def test_get_by_id(session: AsyncSession):
    """测试根据ID获取记录"""
    repo = OptimizationRepository(session)

    # 创建记录
    created = await repo.create(
        skill_id="test-skill-002",
        skill_type="PREBUILT",
        baseline_score={"overall_score": 0.85},
    )

    # 获取记录
    retrieved = await repo.get_by_id(created.id)
    assert retrieved is not None
    assert retrieved.id == created.id
    assert retrieved.skill_id == "test-skill-002"


@pytest.mark.asyncio
async def test_get_by_skill_id(session: AsyncSession):
    """测试根据skill_id获取记录"""
    repo = OptimizationRepository(session)

    # 创建多条记录
    r1 = await repo.create(
        skill_id="test-skill-003",
        skill_type="USER",
        baseline_score={"overall_score": 0.7},
    )
    r2 = await repo.create(
        skill_id="test-skill-003",
        skill_type="USER",
        baseline_score={"overall_score": 0.8},
    )

    # 获取记录
    records = await repo.get_by_skill_id("test-skill-003", limit=10)
    assert len(records) == 2
    # 验证两条记录都被创建了
    record_ids = {r.id for r in records}
    assert r1.id in record_ids
    assert r2.id in record_ids


@pytest.mark.asyncio
async def test_update_status(session: AsyncSession):
    """测试更新优化记录状态"""
    repo = OptimizationRepository(session)

    # 创建记录
    created = await repo.create(
        skill_id="test-skill-004",
        skill_type="USER",
        baseline_score={"overall_score": 0.7},
    )

    # 更新状态
    updated = await repo.update_status(
        record_id=created.id,
        status="COMPLETED",
        optimized_content="def foo(): pass",
    )

    assert updated is not None
    assert updated.status == "COMPLETED"
    assert updated.optimized_content == "def foo(): pass"
    assert updated.completed_at is not None


@pytest.mark.asyncio
async def test_delete_record(session: AsyncSession):
    """测试删除优化记录"""
    repo = OptimizationRepository(session)

    # 创建记录
    created = await repo.create(
        skill_id="test-skill-005",
        skill_type="USER",
        baseline_score={"overall_score": 0.7},
    )

    # 删除记录
    success = await repo.delete(created.id)
    assert success is True

    # 验证已删除
    retrieved = await repo.get_by_id(created.id)
    assert retrieved is None


@pytest.mark.asyncio
async def test_get_active_optimizations(session: AsyncSession):
    """测试获取进行中的优化记录"""
    repo = OptimizationRepository(session)

    # 创建不同状态的记录
    r1 = await repo.create(
        skill_id="test-skill-006",
        skill_type="USER",
        baseline_score={"overall_score": 0.7},
    )
    await repo.update_status(r1.id, "IN_PROGRESS")

    r2 = await repo.create(
        skill_id="test-skill-007",
        skill_type="USER",
        baseline_score={"overall_score": 0.7},
    )
    # r2 保持 PENDING 状态

    r3 = await repo.create(
        skill_id="test-skill-008",
        skill_type="USER",
        baseline_score={"overall_score": 0.7},
    )
    await repo.update_status(r3.id, "COMPLETED")

    # 获取进行中的记录
    active = await repo.get_active_optimizations()
    assert len(active) == 2
    active_ids = {r.id for r in active}
    assert r1.id in active_ids
    assert r2.id in active_ids
    assert r3.id not in active_ids
