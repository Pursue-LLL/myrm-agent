"""Test SQLAlchemyStorage

SQLAlchemyStorage 单元测试：Protocol完整性、session管理模式、SkillVersion操作。
"""

import pytest
from myrm_agent_harness.agent.skills.optimization.types import SkillQualityScore
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.adapters.skill_optimization.sqlalchemy_storage import SQLAlchemyStorage
from app.database.models import Base


@pytest.fixture
async def engine():
    """创建测试数据库引擎"""
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(eng.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield eng

    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest.fixture
async def session(engine):
    """创建固定session（API模式）"""
    async with AsyncSession(engine) as session:
        yield session


@pytest.fixture
def session_factory(engine):
    """创建session_factory（scheduler模式）"""
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def quality_score() -> SkillQualityScore:
    return SkillQualityScore(
        success_rate=0.85,
        token_efficiency=0.75,
        execution_time=0.90,
        user_satisfaction=0.80,
        call_frequency=0.60,
    )


# ==================== Constructor Tests ====================


def test_constructor_requires_session_or_factory():
    """必须传入session或session_factory"""
    with pytest.raises(ValueError, match="Must provide either"):
        SQLAlchemyStorage()


def test_constructor_with_session(session):
    """session模式构造"""
    storage = SQLAlchemyStorage(session=session)
    assert storage._fixed_session is session
    assert storage._session_factory is None


def test_constructor_with_factory(session_factory):
    """factory模式构造"""
    storage = SQLAlchemyStorage(session_factory=session_factory)
    assert storage._fixed_session is None
    assert storage._session_factory is session_factory


# ==================== Health Check Tests ====================


@pytest.mark.asyncio
async def test_health_check_session_mode(session: AsyncSession):
    """测试健康检查（session模式）"""
    storage = SQLAlchemyStorage(session=session)
    result = await storage.health_check()

    assert result["healthy"] is True
    assert result["storage_type"] == "sqlalchemy"
    assert result["readable"] is True
    assert result["writable"] is True


@pytest.mark.asyncio
async def test_health_check_factory_mode(session_factory):
    """测试健康检查（factory模式）"""
    storage = SQLAlchemyStorage(session_factory=session_factory)
    result = await storage.health_check()

    assert result["healthy"] is True
    assert result["storage_type"] == "sqlalchemy"


# ==================== SkillVersion Tests (session_factory mode) ====================


@pytest.mark.asyncio
async def test_save_and_get_skill_version_factory(session_factory, quality_score):
    """测试保存和获取版本（factory模式）"""
    storage = SQLAlchemyStorage(session_factory=session_factory)

    saved = await storage.save_skill_version(
        skill_id="skill-001",
        version=1,
        content="def hello(): pass",
        quality_score=quality_score,
        created_by="llm",
        optimization_id="opt-001",
    )

    assert saved.skill_id == "skill-001"
    assert saved.version == 1

    retrieved = await storage.get_skill_version("skill-001", 1)
    assert retrieved is not None
    assert retrieved.content == "def hello(): pass"
    assert retrieved.quality_score is not None
    assert retrieved.quality_score.success_rate == 0.85


@pytest.mark.asyncio
async def test_list_skill_versions_factory(session_factory):
    """测试列出版本（factory模式）"""
    storage = SQLAlchemyStorage(session_factory=session_factory)

    for i in range(1, 6):
        await storage.save_skill_version(
            skill_id="skill-001",
            version=i,
            content=f"v{i} content",
        )

    versions = await storage.list_skill_versions("skill-001")
    assert len(versions) == 5
    assert versions[0].version == 5


@pytest.mark.asyncio
async def test_activate_version_factory(session_factory):
    """测试激活版本（factory模式）"""
    storage = SQLAlchemyStorage(session_factory=session_factory)

    await storage.save_skill_version(skill_id="s1", version=1, content="v1")
    await storage.save_skill_version(skill_id="s1", version=2, content="v2")

    result = await storage.activate_version("s1", 2)
    assert result.is_active is True

    active = await storage.get_active_version("s1")
    assert active is not None
    assert active.version == 2


@pytest.mark.asyncio
async def test_activate_nonexistent_version_raises_storage_error(session_factory):
    """测试激活不存在版本抛出StorageError"""
    from myrm_agent_harness.agent.skills.optimization import StorageError

    storage = SQLAlchemyStorage(session_factory=session_factory)
    await storage.save_skill_version(skill_id="s1", version=1, content="v1")

    with pytest.raises(StorageError):
        await storage.activate_version("s1", 999)


@pytest.mark.asyncio
async def test_delete_skill_versions_factory(session_factory):
    """测试删除旧版本（factory模式）"""
    storage = SQLAlchemyStorage(session_factory=session_factory)

    for i in range(1, 11):
        await storage.save_skill_version(skill_id="s1", version=i, content=f"v{i}")

    deleted = await storage.delete_skill_versions("s1", keep_latest=3)
    assert deleted == 7

    versions = await storage.list_skill_versions("s1")
    assert len(versions) == 3


@pytest.mark.asyncio
async def test_get_nonexistent_version(session_factory):
    """测试获取不存在的版本返回None"""
    storage = SQLAlchemyStorage(session_factory=session_factory)
    result = await storage.get_skill_version("nonexistent", 1)
    assert result is None


@pytest.mark.asyncio
async def test_get_active_version_none(session_factory):
    """测试无激活版本返回None"""
    storage = SQLAlchemyStorage(session_factory=session_factory)
    result = await storage.get_active_version("nonexistent")
    assert result is None


# ==================== SkillVersion Tests (session mode) ====================


@pytest.mark.asyncio
async def test_save_and_get_version_session_mode(session: AsyncSession, quality_score):
    """测试session模式下的版本操作"""
    storage = SQLAlchemyStorage(session=session)

    await storage.save_skill_version(
        skill_id="skill-session",
        version=1,
        content="session content",
        quality_score=quality_score,
    )

    retrieved = await storage.get_skill_version("skill-session", 1)
    assert retrieved is not None
    assert retrieved.content == "session content"
