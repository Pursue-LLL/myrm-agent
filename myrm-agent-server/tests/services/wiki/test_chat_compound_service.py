"""Tests for chat compound server SSOT service."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage
from myrm_agent_harness.toolkits.wiki.core.claims_contract import (
    parse_claims_from_content,
)
from myrm_agent_harness.toolkits.wiki.core.frontmatter_contract import (
    load_frontmatter_metadata,
)
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.dto import MessageDTO
from app.database.models import Chat, Message
from app.database.repositories.chat_repo import ChatRepository
from app.services.wiki.chat_compound_service import (
    ChatCompoundServiceError,
    build_trust_context,
    resolve_preceding_user_question,
    stage_chat_compound_from_message,
)
from app.services.wiki.memory_to_wiki import MemoryToWikiArchiver


def _make_message(
    chat_id: str,
    role: str,
    content: str,
    *,
    msg_id: str,
    created_at: datetime,
    extra_data: dict[str, object] | None = None,
) -> MessageDTO:
    return MessageDTO(
        id=msg_id,
        chat_id=chat_id,
        role=role,
        content=content,
        sent_at=created_at,
        sent_timezone="UTC",
        created_at=created_at,
        extra_data=extra_data,
    )


@pytest.fixture
def wiki_archiver(tmp_path) -> MemoryToWikiArchiver:
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=AIMessage(content="[]"))
    return MemoryToWikiArchiver(llm=llm, wiki_dir=str(tmp_path / "wiki"))


@pytest.fixture
async def seeded_compound_chat(db_session: AsyncSession) -> tuple[str, str]:
    chat_id = "compound-chat-1"
    db_session.add(Chat(id=chat_id, title="Compound Chat", source="web"))
    await db_session.flush()

    base = datetime(2026, 8, 1, 12, 0, 0)
    messages = [
        _make_message(
            chat_id,
            "user",
            "What is continuous integration?",
            msg_id="user-1",
            created_at=base,
        ),
        _make_message(
            chat_id,
            "assistant",
            "Continuous integration automates testing on every change.",
            msg_id="asst-1",
            created_at=base + timedelta(seconds=1),
            extra_data={
                "sources": [
                    {
                        "type": "knowledge",
                        "snapshot_status": "verified",
                        "title": "CI Guide",
                    }
                ]
            },
        ),
    ]
    await ChatRepository.add_messages(db_session, messages)
    await db_session.commit()
    return chat_id, "asst-1"


def test_build_trust_context_marks_verified_knowledge() -> None:
    trust = build_trust_context(
        {
            "sources": [
                {"type": "knowledge", "snapshot_status": "verified"},
                {"type": "web_search", "url": "https://example.com"},
            ]
        }
    )
    assert trust.has_knowledge_sources is True
    assert trust.has_verified_snapshot is True


def test_build_trust_context_without_sources() -> None:
    trust = build_trust_context(None)
    assert trust.has_knowledge_sources is False
    assert trust.has_verified_snapshot is False


def test_resolve_preceding_user_question_walks_back() -> None:
    base = datetime(2026, 8, 1, 12, 0, 0)
    messages = [
        _make_message("chat", "user", "First question", msg_id="u1", created_at=base),
        _make_message(
            "chat",
            "assistant",
            "First answer",
            msg_id="a1",
            created_at=base + timedelta(seconds=1),
        ),
        _make_message(
            "chat",
            "user",
            "Follow-up question",
            msg_id="u2",
            created_at=base + timedelta(seconds=2),
        ),
        _make_message(
            "chat",
            "assistant",
            "Follow-up answer",
            msg_id="a2",
            created_at=base + timedelta(seconds=3),
        ),
    ]
    assert resolve_preceding_user_question(messages, "a2") == "Follow-up question"


@pytest.mark.asyncio
async def test_stage_chat_compound_from_message_uses_db_content(
    wiki_archiver: MemoryToWikiArchiver,
    seeded_compound_chat: tuple[str, str],
) -> None:
    chat_id, assistant_id = seeded_compound_chat
    result = await stage_chat_compound_from_message(
        wiki_archiver,
        concept_name="ChatCompounds/2026-08/ci-note",
        source_chat=chat_id,
        source_message=assistant_id,
    )

    assert result.pending_edit_id > 0
    pending = wiki_archiver._pending_mgr.get_pending_edits(limit=10)
    draft = next(item for item in pending if item["id"] == result.pending_edit_id)
    metadata, body = load_frontmatter_metadata(str(draft["proposed_content"]))
    assert metadata["source_chat"] == chat_id
    assert metadata["source_message"] == assistant_id
    assert "What is continuous integration?" in body
    assert "Continuous integration automates testing on every change." in body
    claims = parse_claims_from_content(str(draft["proposed_content"]))
    assert claims
    assert claims[0].status == "supported"


@pytest.mark.asyncio
async def test_stage_chat_compound_from_message_rejects_missing_message(
    wiki_archiver: MemoryToWikiArchiver,
) -> None:
    with pytest.raises(ChatCompoundServiceError) as exc_info:
        await stage_chat_compound_from_message(
            wiki_archiver,
            concept_name="ChatCompounds/2026-08/missing",
            source_chat="missing-chat",
            source_message="missing-message",
        )
    assert exc_info.value.code == "message_not_found"


@pytest.mark.asyncio
async def test_stage_chat_compound_from_message_rejects_user_role(
    db_session: AsyncSession,
    wiki_archiver: MemoryToWikiArchiver,
) -> None:
    chat_id = "compound-chat-user-role"
    db_session.add(Chat(id=chat_id, title="User Role", source="web"))
    await db_session.flush()
    base = datetime(2026, 8, 1, 12, 0, 0)
    await ChatRepository.add_messages(
        db_session,
        [
            _make_message(
                chat_id,
                "user",
                "Not an assistant message",
                msg_id="user-only",
                created_at=base,
            )
        ],
    )
    await db_session.commit()

    with pytest.raises(ChatCompoundServiceError) as exc_info:
        await stage_chat_compound_from_message(
            wiki_archiver,
            concept_name="ChatCompounds/2026-08/bad-role",
            source_chat=chat_id,
            source_message="user-only",
        )
    assert exc_info.value.code == "invalid_role"


@pytest.mark.asyncio
async def test_stage_chat_compound_from_message_rejects_inactive_assistant(
    db_session: AsyncSession,
    wiki_archiver: MemoryToWikiArchiver,
    seeded_compound_chat: tuple[str, str],
) -> None:
    chat_id, assistant_id = seeded_compound_chat
    await db_session.execute(
        update(Message)
        .where(Message.chat_id == chat_id, Message.id == assistant_id)
        .values(is_active=False)
    )
    await db_session.commit()

    with pytest.raises(ChatCompoundServiceError) as exc_info:
        await stage_chat_compound_from_message(
            wiki_archiver,
            concept_name="ChatCompounds/2026-08/inactive",
            source_chat=chat_id,
            source_message=assistant_id,
        )
    assert exc_info.value.code == "message_not_found"


@pytest.mark.asyncio
async def test_stage_chat_compound_from_message_rejects_incognito_chat(
    db_session: AsyncSession,
    wiki_archiver: MemoryToWikiArchiver,
) -> None:
    chat_id = "compound-chat-incognito"
    db_session.add(
        Chat(id=chat_id, title="Incognito Chat", source="web", is_incognito=True)
    )
    await db_session.flush()
    base = datetime(2026, 8, 1, 12, 0, 0)
    await ChatRepository.add_messages(
        db_session,
        [
            _make_message(
                chat_id,
                "user",
                "Secret question",
                msg_id="user-incognito",
                created_at=base,
            ),
            _make_message(
                chat_id,
                "assistant",
                "Secret answer",
                msg_id="asst-incognito",
                created_at=base + timedelta(seconds=1),
            ),
        ],
    )
    await db_session.commit()

    with pytest.raises(ChatCompoundServiceError) as exc_info:
        await stage_chat_compound_from_message(
            wiki_archiver,
            concept_name="ChatCompounds/2026-08/secret",
            source_chat=chat_id,
            source_message="asst-incognito",
        )
    assert exc_info.value.code == "incognito_forbidden"


@pytest.mark.asyncio
async def test_stage_chat_compound_from_message_dedupes_source_message(
    wiki_archiver: MemoryToWikiArchiver,
    seeded_compound_chat: tuple[str, str],
) -> None:
    chat_id, assistant_id = seeded_compound_chat
    await stage_chat_compound_from_message(
        wiki_archiver,
        concept_name="ChatCompounds/2026-08/first",
        source_chat=chat_id,
        source_message=assistant_id,
    )
    with pytest.raises(ChatCompoundServiceError) as exc_info:
        await stage_chat_compound_from_message(
            wiki_archiver,
            concept_name="ChatCompounds/2026-08/second",
            source_chat=chat_id,
            source_message=assistant_id,
        )
    assert exc_info.value.code == "already_staged"
