"""Producer -> real approval queue -> approve round trip for implicit-feedback proposals.

The producer's fake-manager tests prove what it submits; these prove the harness
queue (real SQLite) preserves it and that approving dispatches to the right
memory operation, including the reviewer's edit and the archive-not-delete forget.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.toolkits.memory import InvalidPendingEditError, MemoryManager
from myrm_agent_harness.toolkits.memory.config import MemoryConfig
from myrm_agent_harness.toolkits.memory.relational.sqlite_store import SQLiteRelationalStore
from myrm_agent_harness.toolkits.memory.strategies.implicit_feedback import CorrectionAction, CorrectionProposal
from myrm_agent_harness.toolkits.memory.types import MemoryStatus, PendingResolutionAction, SemanticMemory

from app.ai_agents.general_agent.correction_propagation import _route_proposals_to_personal_memory

_RECALLED = {"mem-old": "The user works at ByteDance as an engineer"}


@pytest.fixture
async def manager(tmp_path: Path) -> AsyncIterator[MemoryManager]:
    store = SQLiteRelationalStore(db_path=str(tmp_path / "memory.db"))
    await store._get_connection()
    try:
        yield MemoryManager(
            MemoryConfig(embedding_model="test"),
            user_id="u1",
            relational=store,
            approval_required=True,
        )
    finally:
        await store.close()


def _proposal(action: CorrectionAction, content: str) -> CorrectionProposal:
    return CorrectionProposal(
        action=action,
        memory_type="semantic",
        content=content,
        confidence=0.9,
        reasoning="User said so",
        target_memory_id="mem-old" if action != CorrectionAction.ADD else None,
    )


async def _queue(manager: MemoryManager, proposal: CorrectionProposal) -> str:
    await _route_proposals_to_personal_memory(
        [proposal], agent_id="agent-1", chat_id="chat-1", memory_manager=manager, recalled=_RECALLED
    )
    pending = await manager.list_pending()
    assert len(pending) == 1
    return pending[0].id


@pytest.mark.asyncio
async def test_correct_proposal_keeps_target_through_queue_and_applies_edit(manager: MemoryManager) -> None:
    pending_id = await _queue(manager, _proposal(CorrectionAction.UPDATE, "User works at Google"))

    queued = (await manager.list_pending())[0]
    assert queued.resolution_action == PendingResolutionAction.CORRECT
    assert queued.target_memory_id == "mem-old"
    assert queued.target_content == _RECALLED["mem-old"]

    corrected = SemanticMemory(content="User works at Google DeepMind")
    with patch.object(manager, "correct_memory", AsyncMock(return_value=corrected)) as correct:
        result = await manager.approve(pending_id, edited_content="User works at Google DeepMind")

    assert result is corrected
    correct.assert_awaited_once_with("mem-old", "User works at Google DeepMind")
    assert await manager.count_pending() == 0


@pytest.mark.asyncio
async def test_forget_proposal_archives_target_on_approval(manager: MemoryManager) -> None:
    pending_id = await _queue(manager, _proposal(CorrectionAction.DELETE, "User no longer works at ByteDance"))

    queued = (await manager.list_pending())[0]
    assert queued.resolution_action == PendingResolutionAction.DELETE

    with (
        patch.object(manager, "update_memory", AsyncMock(return_value=SemanticMemory(content="x"))) as update,
        patch.object(manager, "delete_memory_by_id", AsyncMock()) as hard_delete,
    ):
        await manager.approve(pending_id)

    update.assert_awaited_once_with("mem-old", status=MemoryStatus.ARCHIVED)
    hard_delete.assert_not_called()
    assert await manager.count_pending() == 0


@pytest.mark.asyncio
async def test_forget_proposal_rejects_an_edit_and_stays_reviewable(manager: MemoryManager) -> None:
    pending_id = await _queue(manager, _proposal(CorrectionAction.DELETE, "User no longer works at ByteDance"))

    with pytest.raises(InvalidPendingEditError, match="no editable content"):
        await manager.approve(pending_id, edited_content="reworded")

    assert await manager.count_pending() == 1
