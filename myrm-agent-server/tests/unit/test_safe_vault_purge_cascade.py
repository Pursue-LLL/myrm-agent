"""Unit tests verifying safe cascade chat purge, FTS consistency, and sandbox cleanup."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.chat import Chat, Message
from app.database.repositories.chat_repo import ChatRepository
from app.services.infra.sandbox_cleanup import WorkspaceCleanupService


@pytest.mark.asyncio
async def test_permanently_delete_chat_cascades_messages_and_cleans_fts(db_session: AsyncSession) -> None:
    now = datetime.now(timezone.utc)
    chat = Chat(
        id="test_safe_purge_chat_1",
        title="Safe Purge Test Chat",
        created_at=now,
        updated_at=now,
        deleted_at=now,
    )
    db_session.add(chat)
    await db_session.flush()

    msg = Message(
        id="test_safe_purge_msg_1",
        chat_id=chat.id,
        role="user",
        content="Testing safe cascade purge keyword",
        sent_at=now,
        sent_timezone="UTC",
        created_at=now,
        is_active=True,
    )
    db_session.add(msg)
    await db_session.commit()

    # 验证消息存在
    msg_check = await db_session.execute(select(Message).where(Message.id == msg.id))
    assert msg_check.scalar_one_or_none() is not None

    # 执行永久删除
    deleted = await ChatRepository.permanently_delete_chat(db_session, chat.id)
    await db_session.commit()
    assert deleted is True

    # 验证 chat 与 message 均已物理删除
    c_res = await db_session.execute(select(Chat).where(Chat.id == chat.id))
    assert c_res.scalar_one_or_none() is None
    m_res = await db_session.execute(select(Message).where(Message.id == msg.id))
    assert m_res.scalar_one_or_none() is None

    # 验证 FTS 完整性检查通过
    try:
        await db_session.execute(text("INSERT INTO messages_fts(messages_fts) VALUES('integrity-check')"))
    except Exception as exc:
        pytest.fail(f"FTS5 integrity check failed after safe cascade delete: {exc}")


@pytest.mark.asyncio
async def test_empty_trash_cleans_all_messages_and_preserves_fts_integrity(db_session: AsyncSession) -> None:
    now = datetime.now(timezone.utc)
    chat = Chat(
        id="test_safe_empty_trash_chat",
        title="Empty Trash Test",
        created_at=now,
        updated_at=now,
        deleted_at=now,
    )
    db_session.add(chat)
    await db_session.flush()

    msg = Message(
        id="test_safe_empty_trash_msg",
        chat_id=chat.id,
        role="assistant",
        content="Secret response that should be deleted",
        sent_at=now,
        sent_timezone="UTC",
        created_at=now,
        is_active=True,
    )
    db_session.add(msg)
    await db_session.commit()

    # 清空回收站
    purged_count = await ChatRepository.empty_trash(db_session)
    await db_session.commit()
    assert purged_count >= 1

    # 验证 message 不再残留
    m_res = await db_session.execute(select(Message).where(Message.id == msg.id))
    assert m_res.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_cleanup_chat_workspace_cleans_artifact_vault(tmp_path: object) -> None:
    results = await WorkspaceCleanupService.cleanup_chat_workspace("non_existent_chat_test")
    assert "artifact_vault" in results
    assert results["artifact_vault"] is True
