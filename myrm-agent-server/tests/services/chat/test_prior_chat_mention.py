"""prior_chat mention integration tests."""

from __future__ import annotations

import pytest
from search_support import seed_chat_and_messages
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.agent.params.models import MentionReferenceRequest
from app.services.chat.chat_crud import _ChatCrudMixin


@pytest.mark.asyncio
async def test_prior_chat_reference_inlines_recall_document(
    fts_db: AsyncSession,
) -> None:
    from app.services.agent.params.mention import _build_mention_reference_context

    chat_id = await seed_chat_and_messages(fts_db)
    context, warnings, tokens = await _build_mention_reference_context(
        [
            MentionReferenceRequest(
                type="prior_chat",
                path=chat_id,
                label="@chat:Docker deployment",
            )
        ],
        "/tmp/workspace",
    )

    assert 'type="prior-chat"' in context
    assert "Docker deployment discussion" in context
    assert "conversation_id:" in context
    assert warnings == []
    assert tokens > 0

    from app.services.chat.conversation_recall_index_service import (
        ConversationRecallIndexService,
    )

    items, total = await ConversationRecallIndexService.search_citable_chats(
        "Docker",
        limit=10,
    )
    assert total >= 1
    assert any(item["chat_id"] == chat_id for item in items)


@pytest.mark.asyncio
async def test_prior_chat_reference_rejects_incognito(fts_db: AsyncSession) -> None:
    from app.services.agent.params.mention import _build_mention_reference_context

    chat_id = await seed_chat_and_messages(fts_db)
    await fts_db.execute(
        text("UPDATE chats SET is_incognito = 1 WHERE id = :chat_id"),
        {"chat_id": chat_id},
    )
    await fts_db.commit()

    context, warnings, _tokens = await _build_mention_reference_context(
        [MentionReferenceRequest(type="prior_chat", path=chat_id, label="@chat:test")],
        "/tmp/workspace",
    )

    assert 'error="incognito chats cannot be referenced"' in context
    assert warnings == []


@pytest.mark.asyncio
async def test_prior_chat_reference_inlines_without_workspace_dir(
    fts_db: AsyncSession,
) -> None:
    from app.services.agent.params.mention import (
        _MENTION_PRIOR_CHAT_FALLBACK_WORKSPACE,
        _build_mention_reference_context,
    )

    chat_id = await seed_chat_and_messages(fts_db)
    context, warnings, tokens = await _build_mention_reference_context(
        [
            MentionReferenceRequest(
                type="prior_chat",
                path=chat_id,
                label="@chat:Docker deployment",
            )
        ],
        _MENTION_PRIOR_CHAT_FALLBACK_WORKSPACE,
    )

    assert 'type="prior-chat"' in context
    assert "Docker deployment discussion" in context
    assert warnings == []
    assert tokens > 0


@pytest.mark.asyncio
async def test_ensure_chat_source_only_upgrades_web(fts_db: AsyncSession) -> None:
    from app.database.models import Chat

    chat_id = await seed_chat_and_messages(fts_db)
    await _ChatCrudMixin.ensure_chat_source(chat_id, "cron")
    chat = await fts_db.get(Chat, chat_id)
    assert chat is not None
    assert chat.source == "cron"

    await fts_db.execute(
        text("UPDATE chats SET source = 'feishu' WHERE id = :chat_id"),
        {"chat_id": chat_id},
    )
    await fts_db.commit()
    fts_db.expire_all()
    await _ChatCrudMixin.ensure_chat_source(chat_id, "cron")
    chat = await fts_db.get(Chat, chat_id)
    assert chat is not None
    await fts_db.refresh(chat)
    assert chat.source == "feishu"


@pytest.mark.asyncio
async def test_ensure_chat_source_ignores_kanban(fts_db: AsyncSession) -> None:
    from app.database.models import Chat

    chat_id = await seed_chat_and_messages(fts_db)
    await _ChatCrudMixin.ensure_chat_source(chat_id, "kanban")
    chat = await fts_db.get(Chat, chat_id)
    assert chat is not None
    assert chat.source == "web"


@pytest.mark.asyncio
async def test_ensure_chat_source_syncs_recall_document_source(
    fts_db: AsyncSession,
) -> None:
    chat_id = await seed_chat_and_messages(fts_db)

    row = (
        await fts_db.execute(
            text(
                "SELECT source FROM conversation_recall_documents WHERE chat_id = :chat_id"
            ),
            {"chat_id": chat_id},
        )
    ).first()
    assert row is not None
    assert row[0] == "web"

    await _ChatCrudMixin.ensure_chat_source(chat_id, "cron")

    row = (
        await fts_db.execute(
            text(
                "SELECT source FROM conversation_recall_documents WHERE chat_id = :chat_id"
            ),
            {"chat_id": chat_id},
        )
    ).first()
    assert row is not None
    assert row[0] == "cron"


@pytest.mark.asyncio
async def test_prior_chat_reference_rebuilds_missing_recall_document(
    fts_db: AsyncSession,
) -> None:
    from app.services.agent.params.mention import _build_mention_reference_context

    chat_id = await seed_chat_and_messages(fts_db)
    await fts_db.execute(
        text("DELETE FROM conversation_recall_documents WHERE chat_id = :chat_id"),
        {"chat_id": chat_id},
    )
    await fts_db.commit()

    context, warnings, tokens = await _build_mention_reference_context(
        [
            MentionReferenceRequest(
                type="prior_chat",
                path=chat_id,
                label="@chat:Docker deployment",
            )
        ],
        "/tmp/workspace",
    )

    assert 'type="prior-chat"' in context
    assert "Docker deployment discussion" in context
    assert warnings == []
    assert tokens > 0
