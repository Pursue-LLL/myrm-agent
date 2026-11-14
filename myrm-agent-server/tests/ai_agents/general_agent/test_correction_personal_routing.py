"""Routing of correction proposals into the memory approval queue (deterministic, no LLM)."""

import inspect

import pytest


class _RecordingMemoryManager:
    """Stand-in capturing `submit_pending` calls.

    Arguments are bound against the real ``MemoryManager.submit_pending`` signature:
    the producer swallows submission errors by design, so a drifted keyword would
    otherwise pass here while queueing nothing in production.
    """

    def __init__(self) -> None:
        self.submitted: list[tuple[object, dict[str, object]]] = []

    async def submit_pending(self, memory: object, **kwargs: object) -> str:
        from myrm_agent_harness.toolkits.memory import MemoryManager

        inspect.signature(MemoryManager.submit_pending).bind(self, memory, **kwargs)
        self.submitted.append((memory, kwargs))
        return "pending-1"


class TestPersonalMemoryRouting:
    """Deterministic (no-LLM) coverage for harness approval-queue routing."""

    @pytest.mark.asyncio
    async def test_add_proposal_queues_store_action(self) -> None:
        from myrm_agent_harness.toolkits.memory.strategies.implicit_feedback import (
            CorrectionAction,
            CorrectionProposal,
        )
        from myrm_agent_harness.toolkits.memory.types import PendingResolutionAction

        from app.ai_agents.general_agent.correction_propagation import _route_proposals_to_personal_memory

        manager = _RecordingMemoryManager()
        proposal = CorrectionProposal(
            action=CorrectionAction.ADD,
            memory_type="semantic",
            content="User works at Google",
            confidence=0.9,
            reasoning="User stated it",
        )

        await _route_proposals_to_personal_memory(
            [proposal],
            agent_id="agent-1",
            chat_id="chat-1",
            memory_manager=manager,  # type: ignore[arg-type]
        )

        assert len(manager.submitted) == 1
        _, kwargs = manager.submitted[0]
        assert kwargs["resolution_action"] == PendingResolutionAction.STORE
        assert kwargs["target_memory_id"] is None

    @pytest.mark.asyncio
    async def test_update_proposal_resolves_target_and_corrects(self) -> None:
        from myrm_agent_harness.toolkits.memory.strategies.implicit_feedback import (
            CorrectionAction,
            CorrectionProposal,
        )
        from myrm_agent_harness.toolkits.memory.types import PendingResolutionAction

        from app.ai_agents.general_agent.correction_propagation import _route_proposals_to_personal_memory

        manager = _RecordingMemoryManager()
        proposal = CorrectionProposal(
            action=CorrectionAction.UPDATE,
            memory_type="semantic",
            content="User works at Google",
            confidence=0.9,
            reasoning="User moved",
            old_content="User works at ByteDance",
        )

        await _route_proposals_to_personal_memory(
            [proposal],
            agent_id="agent-1",
            chat_id="chat-1",
            memory_manager=manager,  # type: ignore[arg-type]
            recalled={"mem-old": "The user works at ByteDance as an engineer"},
        )

        assert len(manager.submitted) == 1
        _, kwargs = manager.submitted[0]
        assert kwargs["resolution_action"] == PendingResolutionAction.CORRECT
        assert kwargs["target_memory_id"] == "mem-old"

    @pytest.mark.asyncio
    async def test_update_without_target_is_skipped(self) -> None:
        from myrm_agent_harness.toolkits.memory.strategies.implicit_feedback import (
            CorrectionAction,
            CorrectionProposal,
        )

        from app.ai_agents.general_agent.correction_propagation import _route_proposals_to_personal_memory

        manager = _RecordingMemoryManager()
        proposal = CorrectionProposal(
            action=CorrectionAction.UPDATE,
            memory_type="semantic",
            content="User works at Google",
            confidence=0.9,
            reasoning="User moved",
            old_content="User works at ByteDance",
        )

        await _route_proposals_to_personal_memory(
            [proposal],
            agent_id="agent-1",
            chat_id="chat-1",
            memory_manager=manager,  # type: ignore[arg-type]
            recalled={},
        )

        assert manager.submitted == []

    @pytest.mark.asyncio
    async def test_delete_proposal_routes_delete_action(self) -> None:
        from myrm_agent_harness.toolkits.memory.strategies.implicit_feedback import (
            CorrectionAction,
            CorrectionProposal,
        )
        from myrm_agent_harness.toolkits.memory.types import PendingResolutionAction

        from app.ai_agents.general_agent.correction_propagation import _route_proposals_to_personal_memory

        manager = _RecordingMemoryManager()
        proposal = CorrectionProposal(
            action=CorrectionAction.DELETE,
            memory_type="semantic",
            content="User no longer lives in Berlin",
            confidence=0.9,
            reasoning="Obsolete fact",
            target_memory_id="mem-berlin",
        )

        await _route_proposals_to_personal_memory(
            [proposal],
            agent_id="agent-1",
            chat_id="chat-1",
            memory_manager=manager,  # type: ignore[arg-type]
            recalled={"mem-berlin": "User lives in Berlin"},
        )

        assert len(manager.submitted) == 1
        _, kwargs = manager.submitted[0]
        assert kwargs["resolution_action"] == PendingResolutionAction.DELETE
        assert kwargs["target_memory_id"] == "mem-berlin"

    @pytest.mark.asyncio
    async def test_update_with_ambiguous_old_content_is_skipped(self) -> None:
        from myrm_agent_harness.toolkits.memory.strategies.implicit_feedback import (
            CorrectionAction,
            CorrectionProposal,
        )

        from app.ai_agents.general_agent.correction_propagation import _route_proposals_to_personal_memory

        manager = _RecordingMemoryManager()
        proposal = CorrectionProposal(
            action=CorrectionAction.UPDATE,
            memory_type="semantic",
            content="User works at Google",
            confidence=0.9,
            reasoning="User moved",
            old_content="User",
        )

        await _route_proposals_to_personal_memory(
            [proposal],
            agent_id="agent-1",
            chat_id="chat-1",
            memory_manager=manager,  # type: ignore[arg-type]
            recalled={"mem-a": "User works at ByteDance", "mem-b": "User lives in Berlin"},
        )

        assert manager.submitted == []

    @pytest.mark.asyncio
    async def test_update_exact_old_content_match_wins(self) -> None:
        from myrm_agent_harness.toolkits.memory.strategies.implicit_feedback import (
            CorrectionAction,
            CorrectionProposal,
        )
        from myrm_agent_harness.toolkits.memory.types import PendingResolutionAction

        from app.ai_agents.general_agent.correction_propagation import _route_proposals_to_personal_memory

        manager = _RecordingMemoryManager()
        proposal = CorrectionProposal(
            action=CorrectionAction.UPDATE,
            memory_type="semantic",
            content="User works at Google",
            confidence=0.9,
            reasoning="User moved",
            old_content="User works at ByteDance",
        )

        await _route_proposals_to_personal_memory(
            [proposal],
            agent_id="agent-1",
            chat_id="chat-1",
            memory_manager=manager,  # type: ignore[arg-type]
            recalled={"mem-a": "User works at ByteDance", "mem-b": "User works at ByteDance as an engineer"},
        )

        assert len(manager.submitted) == 1
        _, kwargs = manager.submitted[0]
        assert kwargs["resolution_action"] == PendingResolutionAction.CORRECT
        assert kwargs["target_memory_id"] == "mem-a"

    @pytest.mark.asyncio
    async def test_hallucinated_explicit_id_falls_back_to_content_match(self) -> None:
        """An explicit id outside the recalled set must not shadow the content match."""
        from myrm_agent_harness.toolkits.memory.strategies.implicit_feedback import (
            CorrectionAction,
            CorrectionProposal,
        )
        from myrm_agent_harness.toolkits.memory.types import PendingResolutionAction

        from app.ai_agents.general_agent.correction_propagation import _route_proposals_to_personal_memory

        manager = _RecordingMemoryManager()
        proposal = CorrectionProposal(
            action=CorrectionAction.UPDATE,
            memory_type="semantic",
            content="Company uses Paddle",
            confidence=0.9,
            reasoning="User switched billing provider",
            target_memory_id="11111111-2222-3333-4444-555555555555",
            old_content="Company uses Stripe",
        )

        await _route_proposals_to_personal_memory(
            [proposal],
            agent_id="agent-1",
            chat_id="chat-1",
            memory_manager=manager,  # type: ignore[arg-type]
            recalled={"mem-stripe": "Company uses Stripe"},
        )

        assert len(manager.submitted) == 1
        _, kwargs = manager.submitted[0]
        assert kwargs["resolution_action"] == PendingResolutionAction.CORRECT
        # Resolved via the reliable content match, not the hallucinated id.
        assert kwargs["target_memory_id"] == "mem-stripe"

    @pytest.mark.asyncio
    async def test_hallucinated_explicit_id_without_content_match_is_skipped(self) -> None:
        """An id outside the candidate set with no fallback must not be trusted."""
        from myrm_agent_harness.toolkits.memory.strategies.implicit_feedback import (
            CorrectionAction,
            CorrectionProposal,
        )

        from app.ai_agents.general_agent.correction_propagation import _route_proposals_to_personal_memory

        manager = _RecordingMemoryManager()
        proposal = CorrectionProposal(
            action=CorrectionAction.UPDATE,
            memory_type="semantic",
            content="Company uses Paddle",
            confidence=0.9,
            reasoning="User switched billing provider",
            target_memory_id="11111111-2222-3333-4444-555555555555",
            old_content=None,
        )

        await _route_proposals_to_personal_memory(
            [proposal],
            agent_id="agent-1",
            chat_id="chat-1",
            memory_manager=manager,  # type: ignore[arg-type]
            recalled={"mem-stripe": "Company uses Stripe"},
        )

        assert manager.submitted == []

    @pytest.mark.asyncio
    async def test_failed_submission_does_not_abort_remaining_proposals(self) -> None:
        from myrm_agent_harness.toolkits.memory.strategies.implicit_feedback import (
            CorrectionAction,
            CorrectionProposal,
        )

        from app.ai_agents.general_agent.correction_propagation import _route_proposals_to_personal_memory

        class _FlakyManager:
            def __init__(self) -> None:
                self.calls = 0

            async def submit_pending(self, memory: object, **kwargs: object) -> str:
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("queue unavailable")
                return "pending-2"

        manager = _FlakyManager()
        proposals = [
            CorrectionProposal(
                action=CorrectionAction.ADD,
                memory_type="semantic",
                content="first",
                confidence=0.9,
                reasoning="r",
            ),
            CorrectionProposal(
                action=CorrectionAction.ADD,
                memory_type="semantic",
                content="second",
                confidence=0.9,
                reasoning="r",
            ),
        ]

        await _route_proposals_to_personal_memory(
            proposals,
            agent_id="agent-1",
            chat_id="chat-1",
            memory_manager=manager,  # type: ignore[arg-type]
        )

        assert manager.calls == 2

    @pytest.mark.asyncio
    async def test_recall_candidate_memories_gives_planner_targets(self) -> None:
        from myrm_agent_harness.toolkits.memory.types import MemorySearchResult, MemoryType, SemanticMemory

        from app.ai_agents.general_agent.correction_propagation import _recall_candidate_memories

        memory = SemanticMemory(id="mem-1", content="User works at ByteDance")

        class _SearchManager:
            async def search(self, query: str, **kwargs: object) -> list[MemorySearchResult]:
                assert kwargs.get("track_access") is False
                return [MemorySearchResult(memory=memory, memory_type=MemoryType.SEMANTIC)]

        recalled = await _recall_candidate_memories(
            [{"role": "user", "content": "其实我上个月离开字节跳动了"}],
            _SearchManager(),  # type: ignore[arg-type]
        )

        assert recalled == {"mem-1": "User works at ByteDance"}

    @pytest.mark.asyncio
    async def test_recall_returns_empty_without_manager(self) -> None:
        from app.ai_agents.general_agent.correction_propagation import _recall_candidate_memories

        recalled = await _recall_candidate_memories(
            [{"role": "user", "content": "hello"}],
            None,
        )

        assert recalled == {}
