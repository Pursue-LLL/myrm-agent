"""Unit tests for the Memory Command Center action dispatchers.

These exercise the GUI governance actions directly (no HTTP layer): pending
approve/reject/edit, shared-proposal actions, conflict arbitration delegation,
and the generic memory actions (correct / pin / unpin / forget).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from myrm_agent_harness.toolkits.memory import MemoryOperationKind

from app.api.memory.operations import command_center_actions as actions
from app.schemas.memory.command_center import MemoryCommandActionRequest


def _body(**overrides: object) -> MemoryCommandActionRequest:
    base: dict[str, object] = {
        "target_kind": "conflict_pair",
        "target_id": "conflict:c-1",
        "action": "keep_new",
    }
    base.update(overrides)
    return MemoryCommandActionRequest.model_validate(base)


class TestRunConflictAction:
    @pytest.mark.asyncio
    async def test_delegates_to_conflict_resolver(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[tuple[str, str]] = []

        async def _resolve(conflict_id, request, manager):  # type: ignore[no-untyped-def]
            calls.append((conflict_id, request.resolution))

        monkeypatch.setattr("app.api.memory.operations.conflicts.resolve_conflict", _resolve)

        await actions.run_conflict_action(_body(action="keep_new"), AsyncMock(), AsyncMock())

        # The "conflict:" prefix is stripped before hitting the resolver.
        assert calls == [("c-1", "keep_new")]

    @pytest.mark.asyncio
    async def test_coexist_maps_through(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[str] = []

        async def _resolve(conflict_id, request, manager):  # type: ignore[no-untyped-def]
            calls.append(request.resolution)

        monkeypatch.setattr("app.api.memory.operations.conflicts.resolve_conflict", _resolve)

        await actions.run_conflict_action(_body(action="coexist"), AsyncMock(), AsyncMock())

        assert calls == ["coexist"]

    @pytest.mark.asyncio
    async def test_unsupported_action_raises_400(self) -> None:
        with pytest.raises(HTTPException) as exc:
            await actions.run_conflict_action(_body(action="approve"), AsyncMock(), AsyncMock())

        assert exc.value.status_code == 400


class TestRunPendingAction:
    @pytest.mark.asyncio
    async def test_approve(self) -> None:
        db = AsyncMock()
        db.get = AsyncMock(return_value=SimpleNamespace())
        manager = AsyncMock()

        await actions.run_pending_action(_body(target_kind="pending_memory", target_id="p-1", action="approve"), db, manager)

        manager.approve.assert_awaited_once_with("p-1")

    @pytest.mark.asyncio
    async def test_reject(self) -> None:
        db = AsyncMock()
        db.get = AsyncMock(return_value=SimpleNamespace())
        manager = AsyncMock()

        await actions.run_pending_action(_body(target_kind="pending_memory", target_id="p-1", action="reject"), db, manager)

        manager.reject.assert_awaited_once_with("p-1")

    @pytest.mark.asyncio
    async def test_edit_updates_content(self) -> None:
        pending = SimpleNamespace(content="old")
        db = AsyncMock()
        db.get = AsyncMock(return_value=pending)

        await actions.run_pending_action(
            _body(target_kind="pending_memory", target_id="p-1", action="edit", content=" new "),
            db,
            AsyncMock(),
        )

        assert pending.content == "new"
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_missing_pending_raises_404(self) -> None:
        db = AsyncMock()
        db.get = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc:
            await actions.run_pending_action(
                _body(target_kind="pending_memory", target_id="gone", action="approve"), db, AsyncMock()
            )

        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_blank_edit_raises_400(self) -> None:
        db = AsyncMock()
        db.get = AsyncMock(return_value=SimpleNamespace())

        with pytest.raises(HTTPException) as exc:
            await actions.run_pending_action(
                _body(target_kind="pending_memory", target_id="p-1", action="edit", content="   "),
                db,
                AsyncMock(),
            )

        assert exc.value.status_code == 400


class TestRunSharedProposalAction:
    @pytest.mark.asyncio
    async def test_missing_proposal_raises_404(self, monkeypatch: pytest.MonkeyPatch) -> None:
        service = AsyncMock()
        service.get_write_proposal = AsyncMock(return_value=None)
        monkeypatch.setattr(actions, "SharedContextService", lambda db: service)

        with pytest.raises(HTTPException) as exc:
            await actions.run_shared_proposal_action(
                _body(target_kind="shared_context_proposal", target_id="sp-1", action="approve"),
                AsyncMock(),
            )

        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_reject_sets_status(self, monkeypatch: pytest.MonkeyPatch) -> None:
        service = AsyncMock()
        service.get_write_proposal = AsyncMock(return_value=SimpleNamespace())
        monkeypatch.setattr(actions, "SharedContextService", lambda db: service)

        await actions.run_shared_proposal_action(
            _body(target_kind="shared_context_proposal", target_id="sp-1", action="reject"),
            AsyncMock(),
        )

        service.set_write_proposal_status.assert_awaited_once_with("sp-1", "rejected")

    @pytest.mark.asyncio
    async def test_edit_updates_content(self, monkeypatch: pytest.MonkeyPatch) -> None:
        service = AsyncMock()
        service.get_write_proposal = AsyncMock(return_value=SimpleNamespace())
        monkeypatch.setattr(actions, "SharedContextService", lambda db: service)

        await actions.run_shared_proposal_action(
            _body(
                target_kind="shared_context_proposal",
                target_id="sp-1",
                action="edit",
                content=" refined ",
            ),
            AsyncMock(),
        )

        service.update_write_proposal.assert_awaited_once_with("sp-1", content="refined")

    @pytest.mark.asyncio
    async def test_blank_edit_raises_400(self, monkeypatch: pytest.MonkeyPatch) -> None:
        service = AsyncMock()
        service.get_write_proposal = AsyncMock(return_value=SimpleNamespace())
        monkeypatch.setattr(actions, "SharedContextService", lambda db: service)

        with pytest.raises(HTTPException) as exc:
            await actions.run_shared_proposal_action(
                _body(
                    target_kind="shared_context_proposal",
                    target_id="sp-1",
                    action="edit",
                    content="  ",
                ),
                AsyncMock(),
            )

        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_unsupported_action_raises_400(self, monkeypatch: pytest.MonkeyPatch) -> None:
        service = AsyncMock()
        service.get_write_proposal = AsyncMock(return_value=SimpleNamespace())
        monkeypatch.setattr(actions, "SharedContextService", lambda db: service)

        with pytest.raises(HTTPException) as exc:
            await actions.run_shared_proposal_action(
                _body(target_kind="shared_context_proposal", target_id="sp-1", action="pin"),
                AsyncMock(),
            )

        assert exc.value.status_code == 400


class TestRunMemoryAction:
    @pytest.mark.asyncio
    async def test_correct_delegates(self) -> None:
        manager = AsyncMock()

        await actions.run_memory_action(_body(target_kind="memory", target_id="m-1", action="correct", content="fixed"), manager)

        manager.correct_memory.assert_awaited_once_with("m-1", "fixed")

    @pytest.mark.asyncio
    async def test_correct_and_lock_pins(self) -> None:
        manager = AsyncMock()

        await actions.run_memory_action(
            _body(target_kind="memory", target_id="m-1", action="correct_and_lock", content="fixed"),
            manager,
        )

        manager.correct_memory.assert_awaited_once_with("m-1", "fixed")
        manager.pin_memory.assert_awaited_once_with("m-1")

    @pytest.mark.asyncio
    async def test_forget_procedural_deletes_rule(self) -> None:
        manager = AsyncMock()

        await actions.run_memory_action(
            _body(
                target_kind="memory",
                target_id="r-1",
                action="forget",
                memory_type="procedural",
            ),
            manager,
        )

        manager.delete_rule.assert_awaited_once_with("r-1")

    @pytest.mark.asyncio
    async def test_forget_semantic_archives(self) -> None:
        manager = AsyncMock()

        await actions.run_memory_action(
            _body(target_kind="memory", target_id="m-1", action="forget", memory_type="semantic"),
            manager,
        )

        manager.update_memory.assert_awaited_once()
        assert manager.update_memory.await_args.args[0] == "m-1"

    @pytest.mark.asyncio
    async def test_pin_and_unpin(self) -> None:
        manager = AsyncMock()

        await actions.run_memory_action(_body(target_kind="memory", target_id="m-1", action="pin"), manager)
        await actions.run_memory_action(_body(target_kind="memory", target_id="m-1", action="unpin"), manager)

        manager.pin_memory.assert_awaited_once_with("m-1")
        manager.unpin_memory.assert_awaited_once_with("m-1")

    @pytest.mark.asyncio
    async def test_unsupported_action_raises_400(self) -> None:
        with pytest.raises(HTTPException) as exc:
            await actions.run_memory_action(_body(target_kind="memory", target_id="m-1", action="approve"), AsyncMock())

        assert exc.value.status_code == 400


class TestActionToOperation:
    def test_maps_known_actions(self) -> None:
        assert actions.action_to_operation("approve") == MemoryOperationKind.APPROVE
        assert actions.action_to_operation("reject") == MemoryOperationKind.REJECT
        assert actions.action_to_operation("correct") == MemoryOperationKind.CORRECT
        assert actions.action_to_operation("forget") == MemoryOperationKind.FORGET

    def test_unknown_action_is_observe(self) -> None:
        assert actions.action_to_operation("nonsense") == MemoryOperationKind.OBSERVE
