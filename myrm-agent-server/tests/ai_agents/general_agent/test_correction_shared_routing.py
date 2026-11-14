"""Routing of correction proposals to SharedContexts (deterministic, no LLM)."""

import pytest


class TestSharedContextRouting:
    """Deterministic coverage for routing correction proposals to SharedContexts.

    The routing function imports its collaborators lazily, so tests patch the
    origin modules rather than the wrapper.
    """

    _RESOLVE = "app.services.memory.shared_context.shared_context.resolve_shared_context_ids"
    _SERVICE = "app.services.memory.shared_context.shared_context.SharedContextService"
    _MATERIALIZER = "app.services.memory.shared_context.shared_context_materializer.SharedContextProposalMaterializer"
    _SESSION = "app.database.connection.get_session"

    @staticmethod
    def _proposal(content: str = "User now works at Google", memory_type: str = "semantic"):
        from myrm_agent_harness.toolkits.memory.strategies.implicit_feedback import (
            CorrectionAction,
            CorrectionProposal,
        )

        return CorrectionProposal(
            action=CorrectionAction.ADD,
            memory_type=memory_type,
            content=content,
            confidence=0.9,
            reasoning="user stated it",
        )

    @pytest.mark.asyncio
    async def test_no_bound_context_is_a_noop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from contextlib import asynccontextmanager

        from app.ai_agents.general_agent import correction_propagation as mod

        async def _no_contexts(*, agent_id: str) -> list[str]:
            assert agent_id == "agent-1"
            return []

        @asynccontextmanager
        async def _session():  # pragma: no cover - must not be reached
            raise AssertionError("session must not open when no contexts are bound")
            yield

        monkeypatch.setattr(self._RESOLVE, _no_contexts)
        monkeypatch.setattr(self._SESSION, _session)

        await mod._route_proposals_to_shared_contexts([self._proposal()], agent_id="agent-1", chat_id="chat-1")

    @pytest.mark.asyncio
    async def test_delete_only_proposals_open_no_session(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from contextlib import asynccontextmanager

        from myrm_agent_harness.toolkits.memory.strategies.implicit_feedback import (
            CorrectionAction,
            CorrectionProposal,
        )

        from app.ai_agents.general_agent import correction_propagation as mod

        async def _one_context(*, agent_id: str) -> list[str]:
            return ["ctx-1"]

        @asynccontextmanager
        async def _session():  # pragma: no cover - must not be reached
            raise AssertionError("session must not open when only DELETE proposals exist")
            yield

        monkeypatch.setattr(self._RESOLVE, _one_context)
        monkeypatch.setattr(self._SESSION, _session)

        delete_proposal = CorrectionProposal(
            action=CorrectionAction.DELETE,
            memory_type="semantic",
            content="obsolete",
            confidence=0.9,
            reasoning="r",
            target_memory_id="mem-1",
        )

        await mod._route_proposals_to_shared_contexts([delete_proposal], agent_id="agent-1", chat_id="chat-1")

    @pytest.mark.asyncio
    async def test_proposal_is_materialised_when_auto_approve(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from contextlib import asynccontextmanager
        from types import SimpleNamespace

        from app.ai_agents.general_agent import correction_propagation as mod

        async def _one_context(*, agent_id: str) -> list[str]:
            return ["ctx-1"]

        created: list[dict[str, object]] = []
        approved: list[str] = []

        class _FakeService:
            def __init__(self, session: object) -> None:
                pass

            async def get_context(self, context_id: str) -> object:
                return SimpleNamespace(status="active", policy={}, name="Team KB")

            async def create_write_proposal(self, **kwargs: object) -> object:
                created.append(kwargs)
                return SimpleNamespace(id="prop-1", status="pending")

        class _FakeMaterializer:
            def __init__(self, session: object) -> None:
                pass

            async def approve_write_proposal(self, proposal_id: str) -> None:
                approved.append(proposal_id)

        @asynccontextmanager
        async def _session():
            yield object()

        monkeypatch.setattr(self._RESOLVE, _one_context)
        monkeypatch.setattr(self._SERVICE, _FakeService)
        monkeypatch.setattr(self._MATERIALIZER, _FakeMaterializer)
        monkeypatch.setattr(self._SESSION, _session)

        await mod._route_proposals_to_shared_contexts([self._proposal()], agent_id="agent-1", chat_id="chat-1")

        assert len(created) == 1
        assert created[0]["content"] == "User now works at Google"
        assert created[0]["source_type"] == "implicit_feedback"
        assert approved == ["prop-1"]

    @pytest.mark.asyncio
    async def test_memory_type_a_context_cannot_hold_is_skipped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A planner-emitted procedural proposal must not abort routing of the proposals after it."""
        from contextlib import asynccontextmanager
        from types import SimpleNamespace

        from app.ai_agents.general_agent import correction_propagation as mod

        async def _one_context(*, agent_id: str) -> list[str]:
            return ["ctx-1"]

        created: list[dict[str, object]] = []

        class _FakeService:
            def __init__(self, session: object) -> None:
                pass

            async def get_context(self, context_id: str) -> object:
                return SimpleNamespace(status="active", policy={"correction_auto_approve": False}, name="KB")

            async def create_write_proposal(self, **kwargs: object) -> object:
                created.append(kwargs)
                return SimpleNamespace(id="prop-3", status="pending")

        class _FakeMaterializer:
            def __init__(self, session: object) -> None:
                pass

        @asynccontextmanager
        async def _session():
            yield object()

        monkeypatch.setattr(self._RESOLVE, _one_context)
        monkeypatch.setattr(self._SERVICE, _FakeService)
        monkeypatch.setattr(self._MATERIALIZER, _FakeMaterializer)
        monkeypatch.setattr(self._SESSION, _session)

        await mod._route_proposals_to_shared_contexts(
            [self._proposal("Always run lint first", memory_type="procedural"), self._proposal()],
            agent_id="agent-1",
            chat_id="chat-1",
        )

        assert [(c["memory_type"], c["content"]) for c in created] == [("semantic", "User now works at Google")]

    @pytest.mark.asyncio
    async def test_auto_approve_disabled_leaves_proposal_pending(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from contextlib import asynccontextmanager
        from types import SimpleNamespace

        from app.ai_agents.general_agent import correction_propagation as mod

        async def _one_context(*, agent_id: str) -> list[str]:
            return ["ctx-1"]

        approved: list[str] = []

        class _FakeService:
            def __init__(self, session: object) -> None:
                pass

            async def get_context(self, context_id: str) -> object:
                return SimpleNamespace(status="active", policy={"correction_auto_approve": False}, name="KB")

            async def create_write_proposal(self, **kwargs: object) -> object:
                return SimpleNamespace(id="prop-2", status="pending")

        class _FakeMaterializer:
            def __init__(self, session: object) -> None:
                pass

            async def approve_write_proposal(self, proposal_id: str) -> None:  # pragma: no cover
                approved.append(proposal_id)

        @asynccontextmanager
        async def _session():
            yield object()

        monkeypatch.setattr(self._RESOLVE, _one_context)
        monkeypatch.setattr(self._SERVICE, _FakeService)
        monkeypatch.setattr(self._MATERIALIZER, _FakeMaterializer)
        monkeypatch.setattr(self._SESSION, _session)

        await mod._route_proposals_to_shared_contexts([self._proposal()], agent_id="agent-1", chat_id="chat-1")

        assert approved == []

    @pytest.mark.asyncio
    async def test_inactive_context_is_skipped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from contextlib import asynccontextmanager
        from types import SimpleNamespace

        from app.ai_agents.general_agent import correction_propagation as mod

        async def _one_context(*, agent_id: str) -> list[str]:
            return ["ctx-1"]

        created: list[dict[str, object]] = []

        class _FakeService:
            def __init__(self, session: object) -> None:
                pass

            async def get_context(self, context_id: str) -> object:
                return SimpleNamespace(status="archived", policy={}, name="KB")

            async def create_write_proposal(self, **kwargs: object) -> object:  # pragma: no cover
                created.append(kwargs)
                return SimpleNamespace(id="prop-x", status="pending")

        @asynccontextmanager
        async def _session():
            yield object()

        monkeypatch.setattr(self._RESOLVE, _one_context)
        monkeypatch.setattr(self._SERVICE, _FakeService)
        monkeypatch.setattr(self._SESSION, _session)

        await mod._route_proposals_to_shared_contexts([self._proposal()], agent_id="agent-1", chat_id="chat-1")

        assert created == []

    @pytest.mark.asyncio
    async def test_already_resolved_proposal_is_skipped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from contextlib import asynccontextmanager
        from types import SimpleNamespace

        from app.ai_agents.general_agent import correction_propagation as mod

        async def _one_context(*, agent_id: str) -> list[str]:
            return ["ctx-1"]

        approved: list[str] = []

        class _FakeService:
            def __init__(self, session: object) -> None:
                pass

            async def get_context(self, context_id: str) -> object:
                return SimpleNamespace(status="active", policy={}, name="KB")

            async def create_write_proposal(self, **kwargs: object) -> object:
                # Idempotent replay: the proposal was already approved earlier.
                return SimpleNamespace(id="prop-3", status="approved")

        class _FakeMaterializer:
            def __init__(self, session: object) -> None:
                pass

            async def approve_write_proposal(self, proposal_id: str) -> None:  # pragma: no cover
                approved.append(proposal_id)

        @asynccontextmanager
        async def _session():
            yield object()

        monkeypatch.setattr(self._RESOLVE, _one_context)
        monkeypatch.setattr(self._SERVICE, _FakeService)
        monkeypatch.setattr(self._MATERIALIZER, _FakeMaterializer)
        monkeypatch.setattr(self._SESSION, _session)

        await mod._route_proposals_to_shared_contexts([self._proposal()], agent_id="agent-1", chat_id="chat-1")

        assert approved == []
