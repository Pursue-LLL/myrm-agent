from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from myrm_agent_harness.toolkits.memory.types import (
    EpisodicMemory,
    MemorySearchResult,
    MemoryType,
    SemanticMemory,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.memory.operations.shared_context_history import (
    create_shared_context_proposal_from_history,
)
from app.api.memory.shared_context_schemas import (
    CreateSharedContextProposalFromHistoryRequest,
)
from app.database.models import Base, Chat, Message
from app.services.memory.shared_context import (
    LEGACY_TEAM_CONTEXT_ID,
    SharedContextService,
    shared_context_namespaces,
)
from app.services.memory.shared_context_history import (
    SharedContextHistoryService,
)
from app.services.memory.shared_context_materializer import (
    SharedContextProposalMaterializer,
)


class _FakeSharedMemoryManager:
    def __init__(self, existing_results: list[MemorySearchResult] | None = None) -> None:
        self.existing_results = existing_results or []
        self.stored: list[tuple[SemanticMemory | EpisodicMemory, bool]] = []

    async def search(
        self,
        query: str,
        *,
        memory_types: list[MemoryType] | None = None,
        limit: int = 10,
        use_rrf: bool = True,
    ) -> list[MemorySearchResult]:
        _ = (query, memory_types, limit, use_rrf)
        return self.existing_results

    async def store(
        self,
        memory: SemanticMemory | EpisodicMemory,
        *,
        _bypass_approval: bool = False,
    ) -> SemanticMemory | EpisodicMemory:
        self.stored.append((memory, _bypass_approval))
        return memory


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        from app.database.migrations import ensure_raw_sql_schema

        await ensure_raw_sql_schema(engine)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.mark.asyncio
async def test_shared_context_bindings_resolve_active_contexts_in_target_priority(
    db_session: AsyncSession,
) -> None:
    service = SharedContextService(db_session)
    agent_context = await service.create_context(name="Customer A")
    channel_context = await service.create_context(name="Telegram Ops")

    await service.bind_context(context_id=channel_context.id, target_type="channel", target_id="telegram")
    await service.bind_context(context_id=agent_context.id, target_type="agent", target_id="planner")
    await service.bind_context(context_id=agent_context.id, target_type="channel", target_id="telegram")

    resolved = await service.resolve_active_context_ids([("agent", "planner"), ("channel", "telegram")])

    assert resolved == [agent_context.id, channel_context.id]
    assert shared_context_namespaces(resolved) == [
        f"shared:{agent_context.id}",
        f"shared:{channel_context.id}",
    ]


@pytest.mark.asyncio
async def test_archived_shared_context_is_not_resolved(
    db_session: AsyncSession,
) -> None:
    service = SharedContextService(db_session)
    context = await service.create_context(name="Old Project")
    await service.bind_context(context_id=context.id, target_type="agent", target_id="planner")
    await service.archive_context(context.id)

    resolved = await service.resolve_active_context_ids([("agent", "planner")])

    assert resolved == []


@pytest.mark.asyncio
async def test_shared_context_bindings_can_be_listed_by_target(
    db_session: AsyncSession,
) -> None:
    service = SharedContextService(db_session)
    agent_context = await service.create_context(name="Agent Playbook")
    channel_context = await service.create_context(name="Channel Playbook")
    await service.bind_context(context_id=agent_context.id, target_type="agent", target_id="planner")
    await service.bind_context(context_id=channel_context.id, target_type="channel", target_id="telegram")

    bindings = await service.list_bindings_for_target(target_type="agent", target_id="planner")

    assert [binding.context_id for binding in bindings] == [agent_context.id]


@pytest.mark.asyncio
async def test_archived_shared_context_rejects_write_proposals(
    db_session: AsyncSession,
) -> None:
    service = SharedContextService(db_session)
    context = await service.create_context(name="Archived Customer")
    await service.archive_context(context.id)

    with pytest.raises(ValueError, match="Shared context is not active"):
        await service.create_write_proposal(
            context_id=context.id,
            memory_type="semantic",
            content="Archived contexts cannot receive new proposals.",
        )


@pytest.mark.asyncio
async def test_shared_context_write_proposal_lifecycle(
    db_session: AsyncSession,
) -> None:
    service = SharedContextService(db_session)
    context = await service.create_context(name="Customer A")

    proposal = await service.create_write_proposal(
        context_id=context.id,
        memory_type="semantic",
        content="Customer A prefers concise weekly reports.",
        metadata={"importance": 0.9, "tags": ["customer-a"]},
        source_type="agent",
        source_id="planner",
    )

    assert proposal is not None
    assert proposal.status == "pending"

    approved = await service.set_write_proposal_status(proposal.id, "approved")

    assert approved is not None
    assert approved.status == "approved"
    assert approved.resolved_at is not None


@pytest.mark.asyncio
async def test_shared_context_write_proposal_can_be_edited_before_approval(
    db_session: AsyncSession,
) -> None:
    service = SharedContextService(db_session)
    context = await service.create_context(name="Customer A")
    proposal = await service.create_write_proposal(
        context_id=context.id,
        memory_type="semantic",
        content="Original memory candidate.",
        metadata={"importance": 0.5},
    )
    assert proposal is not None

    updated = await service.update_write_proposal(
        proposal.id,
        content="Edited memory candidate.",
        metadata={"importance": 0.8, "tags": ["edited"]},
    )

    assert updated is not None
    assert updated.content == "Edited memory candidate."
    assert updated.metadata_json == {"importance": 0.8, "tags": ["edited"]}

    await service.set_write_proposal_status(proposal.id, "approved")
    with pytest.raises(ValueError, match="Shared context write proposal is not pending"):
        await service.update_write_proposal(proposal.id, content="Too late.")


@pytest.mark.asyncio
async def test_shared_context_proposal_materializer_writes_audited_semantic_memory(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = SharedContextService(db_session)
    context = await service.create_context(name="Customer A")
    proposal = await service.create_write_proposal(
        context_id=context.id,
        memory_type="semantic",
        content="Customer A prefers concise weekly reports.",
        metadata={
            "importance": 0.9,
            "tags": ["customer-a", "reports"],
            "source_chat_id": "chat-1",
            "source_message_id": "msg-1",
            "nested": {"ignored": True},
        },
        source_type="chat_history",
        source_id="msg-1",
    )
    assert proposal is not None
    manager = _FakeSharedMemoryManager()

    async def fake_create_memory_manager(
        self: SharedContextProposalMaterializer,
        namespace: str,
    ) -> _FakeSharedMemoryManager:
        _ = self
        assert namespace == context.namespace
        return manager

    monkeypatch.setattr(
        SharedContextProposalMaterializer,
        "_create_memory_manager",
        fake_create_memory_manager,
    )

    approved = await SharedContextProposalMaterializer(db_session).approve_write_proposal(proposal.id)

    assert approved is not None
    assert approved.status == "approved"
    assert len(manager.stored) == 1
    memory, bypass_approval = manager.stored[0]
    assert bypass_approval is True
    assert isinstance(memory, SemanticMemory)
    assert memory.content == proposal.content
    assert memory.importance == 0.9
    assert memory.tags == ["customer-a", "reports"]
    assert memory.source_chat_id == "chat-1"
    assert memory.source_message_id == "msg-1"
    assert memory.metadata["shared_context_id"] == context.id
    assert memory.metadata["shared_context_proposal_id"] == proposal.id
    assert memory.metadata["shared_context_source_type"] == "chat_history"
    assert "nested" not in memory.metadata


@pytest.mark.asyncio
async def test_shared_context_proposal_materializer_is_idempotent_when_memory_exists(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = SharedContextService(db_session)
    context = await service.create_context(name="Customer A")
    proposal = await service.create_write_proposal(
        context_id=context.id,
        memory_type="semantic",
        content="Customer A prefers concise weekly reports.",
    )
    assert proposal is not None
    existing_memory = SemanticMemory(
        content=proposal.content,
        metadata={"shared_context_proposal_id": proposal.id},
    )
    manager = _FakeSharedMemoryManager(
        [
            MemorySearchResult(
                memory=existing_memory,
                score=1.0,
                memory_type=MemoryType.SEMANTIC,
            )
        ]
    )

    async def fake_create_memory_manager(
        self: SharedContextProposalMaterializer,
        namespace: str,
    ) -> _FakeSharedMemoryManager:
        _ = self
        assert namespace == context.namespace
        return manager

    monkeypatch.setattr(
        SharedContextProposalMaterializer,
        "_create_memory_manager",
        fake_create_memory_manager,
    )

    approved = await SharedContextProposalMaterializer(db_session).approve_write_proposal(proposal.id)

    assert approved is not None
    assert approved.status == "approved"
    assert manager.stored == []


@pytest.mark.asyncio
async def test_get_or_create_legacy_team_context_is_deterministic(
    db_session: AsyncSession,
) -> None:
    service = SharedContextService(db_session)

    first = await service.get_or_create_legacy_team_context()
    second = await service.get_or_create_legacy_team_context()

    assert first.id == LEGACY_TEAM_CONTEXT_ID
    assert first.namespace == "shared:legacy-team"
    assert second.id == first.id


@pytest.mark.asyncio
async def test_goal_completion_proposal_is_idempotent_by_source(
    db_session: AsyncSession,
) -> None:
    service = SharedContextService(db_session)
    context = await service.create_context(name="Team Memory")

    first = await service.create_write_proposal(
        context_id=context.id,
        memory_type="semantic",
        content="Use PostgreSQL for persistence.",
        source_type="goal_completion",
        source_id="goal-1",
    )
    second = await service.create_write_proposal(
        context_id=context.id,
        memory_type="semantic",
        content="Different content should not create duplicate.",
        source_type="goal_completion",
        source_id="goal-1",
    )

    assert first is not None
    assert second is not None
    assert first.id == second.id
    assert first.content == "Use PostgreSQL for persistence."


@pytest.mark.asyncio
async def test_correction_proposal_is_idempotent_by_source(
    db_session: AsyncSession,
) -> None:
    service = SharedContextService(db_session)
    context = await service.create_context(name="Team Memory")

    first = await service.create_write_proposal(
        context_id=context.id,
        memory_type="semantic",
        content="API version is v3, not v2.",
        source_type="correction_propagation",
        source_id="chat-1:abc123deadbeef01",
    )
    second = await service.create_write_proposal(
        context_id=context.id,
        memory_type="semantic",
        content="Should not replace existing proposal content.",
        source_type="correction_propagation",
        source_id="chat-1:abc123deadbeef01",
    )

    assert first is not None
    assert second is not None
    assert first.id == second.id
    assert first.content == "API version is v3, not v2."


@pytest.mark.asyncio
async def test_history_message_can_be_promoted_to_audited_write_proposal(
    db_session: AsyncSession,
) -> None:
    sent_at = datetime(2026, 4, 28, 10, 30, tzinfo=UTC)
    db_session.add(
        Chat(
            id="chat-1",
            agent_id="planner",
            title="Customer A planning",
            source="web",
            action_mode="agent",
        )
    )
    db_session.add(
        Message(
            id="msg-1",
            chat_id="chat-1",
            role="assistant",
            content="Customer A wants weekly reports every Friday.",
            sent_at=sent_at,
            sent_timezone="UTC",
        )
    )
    await db_session.commit()

    source = await SharedContextHistoryService(db_session).get_message("msg-1")

    assert source is not None
    context = await SharedContextService(db_session).create_context(name="Customer A")
    proposal = await create_shared_context_proposal_from_history(
        context.id,
        CreateSharedContextProposalFromHistoryRequest(
            message_id=source.message_id,
            memory_type="semantic",
            content=None,
            metadata={"importance": 0.8, "source_message_id": "client-supplied"},
        ),
        db_session,
    )

    assert proposal.content == "Customer A wants weekly reports every Friday."
    assert proposal.metadata["promoted_from_history"] is True
    assert proposal.metadata["source_message_id"] == "msg-1"
    assert proposal.metadata["source_chat_id"] == "chat-1"
    assert proposal.metadata["source_content_truncated"] is False
    assert proposal.source_type == "chat_history"
    assert proposal.source_id == "msg-1"
