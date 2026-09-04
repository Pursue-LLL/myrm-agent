"""Shared Context memory-operation events must be persisted after API operations.

[POS]
回归保护：archive_shared_context / delete_shared_context_binding 的 ledger 事件此前只发布
SSE 而不落库（get_db_session 不自动 commit），刷新后事件消失。修复后必须落库。
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.memory.operations.shared_context.shared_contexts import (
    archive_shared_context,
    delete_shared_context_binding,
)
from app.database.models import Base
from app.database.models.memory import MemoryOperationEventModel
from app.services.memory.shared_context.shared_context import SharedContextService

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def db() -> AsyncIterator[AsyncSession]:
    """In-memory SQLite session with full schema for one test."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record) -> None:
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _fetch_events(
    db: AsyncSession,
    *,
    kind: str,
    target_kind: str,
) -> list[MemoryOperationEventModel]:
    result = await db.execute(
        select(MemoryOperationEventModel).where(
            MemoryOperationEventModel.source == "shared_context_api",
            MemoryOperationEventModel.kind == kind,
            MemoryOperationEventModel.target_kind == target_kind,
        )
    )
    return list(result.scalars().all())


async def test_archive_shared_context_persists_forget_event(db: AsyncSession) -> None:
    context = await SharedContextService(db).create_context(
        name="prod-ctx",
        description="events regression",
    )

    await archive_shared_context(context.id, db)

    rows = await _fetch_events(db, kind="forget", target_kind="shared_context")
    assert len(rows) == 1
    assert rows[0].target_id == context.id
    assert rows[0].memory_type == "shared_context"
    assert rows[0].metadata_json == {"name": "prod-ctx"}


async def test_delete_shared_context_binding_persists_write_event(db: AsyncSession) -> None:
    service = SharedContextService(db)
    context = await service.create_context(name="prod-ctx")
    binding = await service.bind_context(
        context_id=context.id,
        target_type="agent",
        target_id="agent-1",
    )
    assert binding is not None

    await delete_shared_context_binding(context.id, binding.id, db)

    rows = await _fetch_events(db, kind="write", target_kind="shared_context_binding")
    assert len(rows) == 1
    assert rows[0].target_id == binding.id
    assert rows[0].memory_id == context.id


async def test_binding_api_and_target_query_flow(db: AsyncSession) -> None:
    """全面测试共享知识库与会话绑定的完整API层交互契约：

    1. 创建共享上下文并在绑定时校验返回的 context_name。
    2. 通过 list_shared_context_bindings_for_target 查询会话绑定，验证 context_name 连表正常。
    3. 验证单会话上限 6 个知识库的安全门禁（第 7 个抛 400 异常）。
    4. 验证 delete_shared_context_binding_by_target 按目标类型与目标ID精准解绑。
    """
    from fastapi import HTTPException

    from app.api.memory.operations.shared_context.shared_contexts import (
        create_shared_context_binding,
        delete_shared_context_binding_by_target,
        list_shared_context_bindings_for_target,
    )
    from app.api.memory.shared_context_schemas import CreateSharedContextBindingRequest

    service = SharedContextService(db)
    ctx_main = await service.create_context(name="核心工程标准", description="标准规范")

    # 1. 创建会话绑定，验证返回的 context_name
    create_req = CreateSharedContextBindingRequest(
        target_type="conversation",
        target_id="conv-flow-1",
    )
    binding_item = await create_shared_context_binding(
        context_id=ctx_main.id,
        body=create_req,
        db=db,
    )
    assert binding_item.context_id == ctx_main.id
    assert binding_item.context_name == "核心工程标准"
    assert binding_item.target_type == "conversation"
    assert binding_item.target_id == "conv-flow-1"

    # 2. 查询该会话的绑定列表，验证连表解析出来的 context_name
    target_res = await list_shared_context_bindings_for_target(
        target_type="conversation",
        target_id="conv-flow-1",
        db=db,
    )
    assert target_res.total == 1
    assert target_res.items[0].context_id == ctx_main.id
    assert target_res.items[0].context_name == "核心工程标准"

    # 3. 构造 5 个额外的知识库并绑定，使当前会话达到 6 个上限
    extra_contexts = []
    for i in range(5):
        c = await service.create_context(name=f"扩展知识库_{i}")
        extra_contexts.append(c)
        await create_shared_context_binding(
            context_id=c.id,
            body=CreateSharedContextBindingRequest(target_type="conversation", target_id="conv-flow-1"),
            db=db,
        )

    # 验证此时恰好 6 个绑定
    res_six = await list_shared_context_bindings_for_target(
        target_type="conversation",
        target_id="conv-flow-1",
        db=db,
    )
    assert res_six.total == 6

    # 尝试绑定第 7 个，验证 6 库安全门禁生效
    c_seven = await service.create_context(name="超出上限知识库")
    with pytest.raises(HTTPException) as exc_info:
        await create_shared_context_binding(
            context_id=c_seven.id,
            body=CreateSharedContextBindingRequest(target_type="conversation", target_id="conv-flow-1"),
            db=db,
        )
    assert exc_info.value.status_code == 400
    assert "Maximum 6 knowledge bases" in exc_info.value.detail

    # 4. 按目标批量解绑 delete_shared_context_binding_by_target
    await delete_shared_context_binding_by_target(
        context_id=ctx_main.id,
        target_type="conversation",
        target_id="conv-flow-1",
        db=db,
    )

    # 验证解绑后只剩 5 个，且不包含 ctx_main
    res_after_unbind = await list_shared_context_bindings_for_target(
        target_type="conversation",
        target_id="conv-flow-1",
        db=db,
    )
    assert res_after_unbind.total == 5
    assert not any(item.context_id == ctx_main.id for item in res_after_unbind.items)
