"""Test SnapshotRepository

SnapshotRepository 单元测试：版本保存、查询、激活、删除。
"""

import pytest
from myrm_agent_harness.agent.skills.optimization.types import SkillQualityScore
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool

from app.adapters.skill_optimization.snapshot_repo import SnapshotRepository
from app.database.models import Base


@pytest.fixture
async def session():
    """创建测试数据库session"""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSession(engine) as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
def quality_score() -> SkillQualityScore:
    return SkillQualityScore(
        success_rate=0.85,
        token_efficiency=0.75,
        execution_time=0.90,
        user_satisfaction=0.80,
        call_frequency=0.60,
    )


@pytest.mark.asyncio
async def test_save_version(session: AsyncSession, quality_score: SkillQualityScore):
    """测试保存版本"""
    repo = SnapshotRepository(session)

    version = await repo.save_version(
        skill_id="skill-001",
        version=1,
        content="def hello(): pass",
        quality_score=quality_score,
        created_by="llm",
        optimization_id="opt-001",
        metadata={"note": "initial version"},
    )

    assert version.skill_id == "skill-001"
    assert version.version == 1
    assert version.content == "def hello(): pass"
    assert version.created_by == "llm"
    assert version.is_active is False
    assert version.optimization_id == "opt-001"
    assert version.metadata == {"note": "initial version"}
    assert version.quality_score is not None
    assert version.quality_score.success_rate == 0.85


@pytest.mark.asyncio
async def test_save_version_without_quality_score(session: AsyncSession):
    """测试保存不含质量评分的版本"""
    repo = SnapshotRepository(session)

    version = await repo.save_version(
        skill_id="skill-001",
        version=1,
        content="def hello(): pass",
    )

    assert version.quality_score is None


@pytest.mark.asyncio
async def test_get_version(session: AsyncSession):
    """测试获取指定版本"""
    repo = SnapshotRepository(session)

    await repo.save_version(skill_id="skill-001", version=1, content="v1 content")
    await repo.save_version(skill_id="skill-001", version=2, content="v2 content")

    v1 = await repo.get_version("skill-001", 1)
    v2 = await repo.get_version("skill-001", 2)
    v3 = await repo.get_version("skill-001", 3)

    assert v1 is not None
    assert v1.content == "v1 content"
    assert v2 is not None
    assert v2.content == "v2 content"
    assert v3 is None


@pytest.mark.asyncio
async def test_get_version_nonexistent_skill(session: AsyncSession):
    """测试获取不存在的skill版本"""
    repo = SnapshotRepository(session)
    result = await repo.get_version("nonexistent", 1)
    assert result is None


@pytest.mark.asyncio
async def test_get_active_version(session: AsyncSession):
    """测试获取激活版本"""
    repo = SnapshotRepository(session)

    await repo.save_version(skill_id="skill-001", version=1, content="v1")
    await repo.save_version(skill_id="skill-001", version=2, content="v2")

    # 初始没有激活版本
    active = await repo.get_active_version("skill-001")
    assert active is None

    # 激活版本1
    await repo.activate_version("skill-001", 1)
    active = await repo.get_active_version("skill-001")
    assert active is not None
    assert active.version == 1
    assert active.is_active is True


@pytest.mark.asyncio
async def test_list_versions(session: AsyncSession):
    """测试列出版本（倒序）"""
    repo = SnapshotRepository(session)

    for i in range(1, 6):
        await repo.save_version(skill_id="skill-001", version=i, content=f"v{i}")

    versions = await repo.list_versions("skill-001")
    assert len(versions) == 5
    assert versions[0].version == 5
    assert versions[-1].version == 1


@pytest.mark.asyncio
async def test_list_versions_with_limit(session: AsyncSession):
    """测试列出版本（带数量限制）"""
    repo = SnapshotRepository(session)

    for i in range(1, 11):
        await repo.save_version(skill_id="skill-001", version=i, content=f"v{i}")

    versions = await repo.list_versions("skill-001", limit=3)
    assert len(versions) == 3
    assert versions[0].version == 10


@pytest.mark.asyncio
async def test_list_versions_empty(session: AsyncSession):
    """测试列出不存在的skill版本"""
    repo = SnapshotRepository(session)
    versions = await repo.list_versions("nonexistent")
    assert versions == []


@pytest.mark.asyncio
async def test_activate_version(session: AsyncSession):
    """测试激活版本（互斥性）"""
    repo = SnapshotRepository(session)

    await repo.save_version(skill_id="skill-001", version=1, content="v1")
    await repo.save_version(skill_id="skill-001", version=2, content="v2")
    await repo.save_version(skill_id="skill-001", version=3, content="v3")

    # 激活v2
    result = await repo.activate_version("skill-001", 2)
    assert result.version == 2
    assert result.is_active is True

    # 确认v1和v3不是激活状态
    v1 = await repo.get_version("skill-001", 1)
    v3 = await repo.get_version("skill-001", 3)
    assert v1 is not None and v1.is_active is False
    assert v3 is not None and v3.is_active is False

    # 切换激活到v3
    result = await repo.activate_version("skill-001", 3)
    assert result.is_active is True

    # v2不再是激活状态
    v2 = await repo.get_version("skill-001", 2)
    assert v2 is not None and v2.is_active is False


@pytest.mark.asyncio
async def test_activate_nonexistent_version(session: AsyncSession):
    """测试激活不存在的版本（应保持数据一致性）"""
    repo = SnapshotRepository(session)

    await repo.save_version(skill_id="skill-001", version=1, content="v1")
    await repo.activate_version("skill-001", 1)

    with pytest.raises(ValueError, match="not found"):
        await repo.activate_version("skill-001", 999)

    # 验证v1仍然是激活状态（不会被错误的deactivate all破坏）
    v1 = await repo.get_version("skill-001", 1)
    assert v1 is not None and v1.is_active is True


@pytest.mark.asyncio
async def test_delete_versions(session: AsyncSession):
    """测试删除旧版本"""
    repo = SnapshotRepository(session)

    for i in range(1, 16):
        await repo.save_version(skill_id="skill-001", version=i, content=f"v{i}")

    deleted = await repo.delete_versions("skill-001", keep_latest=5)
    assert deleted == 10

    versions = await repo.list_versions("skill-001")
    assert len(versions) == 5
    assert versions[0].version == 15
    assert versions[-1].version == 11


@pytest.mark.asyncio
async def test_delete_versions_preserves_active(session: AsyncSession):
    """测试删除版本时保护激活版本"""
    repo = SnapshotRepository(session)

    for i in range(1, 11):
        await repo.save_version(skill_id="skill-001", version=i, content=f"v{i}")

    # 激活v3（不在最新5个版本中）
    await repo.activate_version("skill-001", 3)

    deleted = await repo.delete_versions("skill-001", keep_latest=5)

    # v3应该被保护（即使不在最新5个中）
    v3 = await repo.get_version("skill-001", 3)
    assert v3 is not None
    assert v3.is_active is True

    # 总共应该保留6个版本（最新5 + 激活的v3）
    versions = await repo.list_versions("skill-001")
    assert len(versions) == 6
    assert deleted == 4


@pytest.mark.asyncio
async def test_delete_versions_noop_when_within_limit(session: AsyncSession):
    """测试版本数在限制内时不删除"""
    repo = SnapshotRepository(session)

    for i in range(1, 4):
        await repo.save_version(skill_id="skill-001", version=i, content=f"v{i}")

    deleted = await repo.delete_versions("skill-001", keep_latest=5)
    assert deleted == 0


@pytest.mark.asyncio
async def test_quality_score_roundtrip(session: AsyncSession, quality_score: SkillQualityScore):
    """测试质量评分序列化/反序列化完整性"""
    repo = SnapshotRepository(session)

    await repo.save_version(
        skill_id="skill-001",
        version=1,
        content="test content",
        quality_score=quality_score,
    )

    retrieved = await repo.get_version("skill-001", 1)
    assert retrieved is not None
    assert retrieved.quality_score is not None
    assert retrieved.quality_score.success_rate == quality_score.success_rate
    assert retrieved.quality_score.token_efficiency == quality_score.token_efficiency
    assert retrieved.quality_score.execution_time == quality_score.execution_time
    assert retrieved.quality_score.user_satisfaction == quality_score.user_satisfaction
    assert retrieved.quality_score.call_frequency == quality_score.call_frequency
