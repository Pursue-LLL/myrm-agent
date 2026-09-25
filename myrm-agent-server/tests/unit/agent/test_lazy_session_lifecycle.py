"""Lifecycle tests for deferred session persistence and orphan protection."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.agent.security import user_credentials_ctx

from app.core.infra.health.session_diagnostics import (
    OrphanSessionDiagnostic,
    purge_orphan_empty_sessions,
)
from app.services.agent.params import AgentRequest
from app.services.agent.stream_session.chat_history_bootstrap import (
    BootstrappedMessageId,
    persist_user_message,
)
from app.services.agent.stream_session.lazy_session_gate import PendingSessionDraft
from app.services.agent.stream_session.stream_finalize import (
    finalize_agent_stream_session,
)
from app.services.agent.stream_session.stream_session_types import AgentStreamSession


@pytest.mark.asyncio
async def test_bootstrap_new_chat_defers_persistence():
    """Verify that a brand new chat does not persist to database immediately."""
    req = AgentRequest(
        query="Explain quantum computing",
        chat_id="chat-brand-new-999",
        message_id="msg-req-1",
        action_mode="fast",
        user_id="user-1",
        timezone="UTC",
    )

    with patch("app.services.chat.chat_service.ChatService.get_chat_metadata", new_callable=AsyncMock) as mock_meta:
        mock_meta.return_value = None  # Chat does not exist in DB

        outcome = await persist_user_message(req, text_content="Explain quantum computing")

        assert isinstance(outcome, BootstrappedMessageId)
        assert outcome.pending_draft is not None
        assert outcome.pending_draft.chat_id == "chat-brand-new-999"
        assert outcome.pending_draft.user_content == "Explain quantum computing"
        assert outcome.pending_draft.message_id == "msg-req-1"
        assert outcome.pending_draft.committed is False


@pytest.mark.asyncio
async def test_bootstrap_existing_chat_persists_immediately():
    """Verify that an existing chat persists the user message immediately."""
    req = AgentRequest(
        query="Continue the discussion",
        chat_id="chat-existing-111",
        message_id="msg-req-2",
        action_mode="fast",
        user_id="user-1",
        timezone="UTC",
    )

    existing_chat = MagicMock()
    existing_chat.id = "chat-existing-111"
    fake_msg = MagicMock()
    fake_msg.id = "msg-req-2"

    with (
        patch("app.services.chat.chat_service.ChatService.get_chat_metadata", new_callable=AsyncMock) as mock_meta,
        patch("app.services.chat.chat_service.ChatService.ensure_chat_and_append_user_message", new_callable=AsyncMock) as mock_append,
    ):
        mock_meta.return_value = existing_chat
        mock_append.return_value = fake_msg

        outcome = await persist_user_message(req, text_content="Continue the discussion")

        assert outcome == "msg-req-2"
        mock_append.assert_awaited_once()


@pytest.mark.asyncio
async def test_finalize_discards_draft_when_cancelled_before_first_token():
    """Verify that if stream is aborted before first token, draft is discarded with 0 writes."""
    req = AgentRequest(
        query="Aborted question",
        chat_id="chat-abort-000",
        message_id="msg-abort-1",
        action_mode="fast",
        user_id="user-1",
        timezone="UTC",
    )

    draft = PendingSessionDraft(
        chat_id="chat-abort-000",
        user_content="Aborted question",
        sent_at=datetime.now(UTC),
        sent_timezone="UTC",
        message_id="msg-abort-1",
        action_mode="fast",
        agent_id="general",
    )

    collector = MagicMock()
    collector.has_persistable_turn = True
    collector.has_active_generation = False  # No authentic model generation
    collector.has_content = False  # No assistant content produced!
    collector.content = ""
    collector.extra_data = {"cancelled": True}
    collector.sibling_group_id = None

    session = MagicMock(spec=AgentStreamSession)
    session.request = req
    session.collector = collector
    session.pending_session_draft = draft
    session.had_fatal_error = False
    session.stream_ttft_ms = None
    session.extra_context = {}
    session.migration_live_readiness_status = None
    session.params = MagicMock(enable_skill_manage=False)
    session.monitor = AsyncMock()
    # cancel_token has no dataclass default, so spec-mocks don't expose it;
    # production requires it (stream_session_types.py:30).
    session.cancel_token = MagicMock()
    session.cancel_token.is_cancelled = False

    token_ctx = user_credentials_ctx.set(None)
    approval = MagicMock()
    clarification = MagicMock()
    clarification.pending = False

    with (
        patch("app.services.chat.chat_service.ChatService.persist_assistant_message_safe", new_callable=AsyncMock) as mock_persist_asst,
        patch("app.services.chat.chat_service.ChatService.ensure_chat_and_append_user_message", new_callable=AsyncMock) as mock_commit_chat,
    ):
        await finalize_agent_stream_session(session, token_ctx, approval, clarification)

        assert draft.committed is False
        mock_commit_chat.assert_not_called()
        mock_persist_asst.assert_not_called()


@pytest.mark.asyncio
async def test_finalize_commits_draft_when_tool_step_present_without_text():
    """Verify that if tool calls occurred without plain text, draft is committed safely."""
    req = AgentRequest(
        query="Run inspection",
        chat_id="chat-tool-step-888",
        message_id="msg-tool-1",
        action_mode="fast",
        user_id="user-1",
        timezone="UTC",
    )

    draft = PendingSessionDraft(
        chat_id="chat-tool-step-888",
        user_content="Run inspection",
        sent_at=datetime.now(UTC),
        sent_timezone="UTC",
        message_id="msg-tool-1",
        action_mode="fast",
        agent_id="general",
    )

    collector = MagicMock()
    collector.has_persistable_turn = True
    collector.has_active_generation = True  # Tool step generated!
    collector.has_content = False  # Text content is empty
    collector.content = ""
    collector.extra_data = {"progressSteps": [{"tool_name": "list_files"}]}
    collector.sibling_group_id = None

    session = MagicMock(spec=AgentStreamSession)
    session.request = req
    session.collector = collector
    session.pending_session_draft = draft
    session.had_fatal_error = False
    session.stream_ttft_ms = 85
    session.extra_context = {}
    session.migration_live_readiness_status = None
    session.monitor = AsyncMock()
    session.cancel_token = MagicMock()
    session.cancel_token.is_cancelled = False
    session.params = MagicMock(enable_skill_manage=False)

    token_ctx = user_credentials_ctx.set(None)
    approval = MagicMock()
    clarification = MagicMock()
    clarification.pending = False

    with (
        patch("app.services.chat.chat_service.ChatService.persist_assistant_message_safe", new_callable=AsyncMock) as mock_persist_asst,
        patch("app.services.chat.chat_service.ChatService.ensure_chat_and_append_user_message", new_callable=AsyncMock) as mock_commit_chat,
        patch("app.services.agent.params.workspace_resolve.materialize_default_chat_workspace_dir", new_callable=AsyncMock) as mock_mat,
    ):
        await finalize_agent_stream_session(session, token_ctx, approval, clarification)

        assert draft.committed is True
        mock_commit_chat.assert_awaited_once()
        mock_persist_asst.assert_awaited_once()
        mock_mat.assert_awaited_once_with("chat-tool-step-888")


@pytest.mark.asyncio
async def test_finalize_commits_draft_when_assistant_content_present():
    """Verify that if assistant content was collected, draft is safely committed before assistant persistence."""
    req = AgentRequest(
        query="Valid question",
        chat_id="chat-success-123",
        message_id="msg-succ-1",
        action_mode="fast",
        user_id="user-1",
        timezone="UTC",
    )

    draft = PendingSessionDraft(
        chat_id="chat-success-123",
        user_content="Valid question",
        sent_at=datetime.now(UTC),
        sent_timezone="UTC",
        message_id="msg-succ-1",
        action_mode="fast",
        agent_id="general",
    )

    collector = MagicMock()
    collector.has_persistable_turn = True
    collector.has_content = True  # Assistant produced content!
    collector.content = "Here is the answer."
    collector.extra_data = {}
    collector.sibling_group_id = None

    session = MagicMock(spec=AgentStreamSession)
    session.request = req
    session.collector = collector
    session.pending_session_draft = draft
    session.had_fatal_error = False
    session.stream_ttft_ms = 120
    session.extra_context = {}
    session.migration_live_readiness_status = None
    session.monitor = AsyncMock()
    # cancel_token has no dataclass default, so spec-mocks don't expose it;
    # production requires it (stream_session_types.py:30).
    session.cancel_token = MagicMock()
    session.cancel_token.is_cancelled = False
    # Keep skill-evolution branch off: this test targets draft commit ordering.
    session.params = MagicMock(enable_skill_manage=False)

    token_ctx = user_credentials_ctx.set(None)
    approval = MagicMock()
    clarification = MagicMock()
    clarification.pending = False

    with (
        patch("app.services.chat.chat_service.ChatService.persist_assistant_message_safe", new_callable=AsyncMock) as mock_persist_asst,
        patch("app.services.chat.chat_service.ChatService.ensure_chat_and_append_user_message", new_callable=AsyncMock) as mock_commit_chat,
        patch("app.services.agent.params.workspace_resolve.materialize_default_chat_workspace_dir", new_callable=AsyncMock) as mock_mat,
    ):
        await finalize_agent_stream_session(session, token_ctx, approval, clarification)

        assert draft.committed is True
        mock_commit_chat.assert_awaited_once()
        mock_mat.assert_awaited_once_with("chat-success-123")
        mock_persist_asst.assert_awaited_once()


@pytest.mark.asyncio
async def test_orphan_session_diagnostic_probe():
    """Verify OrphanSessionDiagnostic reports correctly."""
    probe = OrphanSessionDiagnostic()
    with patch("app.core.infra.health.session_diagnostics.count_orphan_empty_sessions", new_callable=AsyncMock) as mock_count:
        mock_count.return_value = 0
        report = await probe.check_health()
        assert report.status == "pass"
        assert report.code == "OK_NO_ORPHAN_SESSIONS"

        mock_count.return_value = 5
        report = await probe.check_health()
        assert report.status == "pass"
        assert report.code == "INFO_ORPHAN_SESSIONS_DETECTED"
        assert report.meta_data.get("orphan_session_count") == 5


class _FakeSessionDiagnosticsUoW:
    def __init__(self, orphan_ids: list[str]) -> None:
        self._orphan_ids = orphan_ids
        mock_result = MagicMock()
        mock_result.all.return_value = [(oid,) for oid in orphan_ids]
        mock_sess = AsyncMock()
        mock_sess.execute.return_value = mock_result
        self.session = mock_sess

    async def __aenter__(self) -> _FakeSessionDiagnosticsUoW:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None


@pytest.mark.asyncio
async def test_purge_orphan_empty_sessions_when_empty():
    """Verify purge_orphan_empty_sessions returns 0 when no orphan chats exist."""
    fake_uow = _FakeSessionDiagnosticsUoW([])
    with patch("app.core.infra.health.session_diagnostics.UnitOfWork", return_value=fake_uow):
        count = await purge_orphan_empty_sessions(older_than_minutes=15)
        assert count == 0


@pytest.mark.asyncio
async def test_purge_orphan_empty_sessions_soft_then_permanently_deletes():
    """Verify purge_orphan_empty_sessions soft-deletes then permanently deletes each orphan chat."""
    fake_uow = _FakeSessionDiagnosticsUoW(["chat-orphan-1", "chat-orphan-2"])
    with (
        patch("app.core.infra.health.session_diagnostics.UnitOfWork", return_value=fake_uow),
        patch("app.services.chat.chat_service.ChatService.delete_chat", new_callable=AsyncMock) as mock_soft,
        patch("app.services.chat.chat_service.ChatService.permanently_delete_chat", new_callable=AsyncMock) as mock_perm,
    ):
        mock_soft.return_value = True
        mock_perm.return_value = True

        count = await purge_orphan_empty_sessions(older_than_minutes=15)

        assert count == 2
        assert mock_soft.await_count == 2
        assert mock_perm.await_count == 2
        mock_soft.assert_any_await("chat-orphan-1")
        mock_soft.assert_any_await("chat-orphan-2")
        mock_perm.assert_any_await("chat-orphan-1")
        mock_perm.assert_any_await("chat-orphan-2")


@pytest.mark.asyncio
async def test_purge_orphan_empty_sessions_handles_individual_failures():
    """Verify purge_orphan_empty_sessions gracefully handles errors on individual sessions."""
    fake_uow = _FakeSessionDiagnosticsUoW(["chat-fail-soft", "chat-fail-perm", "chat-success"])
    with (
        patch("app.core.infra.health.session_diagnostics.UnitOfWork", return_value=fake_uow),
        patch("app.services.chat.chat_service.ChatService.delete_chat", new_callable=AsyncMock) as mock_soft,
        patch("app.services.chat.chat_service.ChatService.permanently_delete_chat", new_callable=AsyncMock) as mock_perm,
    ):
        async def side_effect_soft(cid: str) -> bool:
            if cid == "chat-fail-soft":
                return False
            return True

        async def side_effect_perm(cid: str) -> bool:
            if cid == "chat-fail-perm":
                raise RuntimeError("disk IO error")
            return True

        mock_soft.side_effect = side_effect_soft
        mock_perm.side_effect = side_effect_perm

        count = await purge_orphan_empty_sessions(older_than_minutes=15)

        assert count == 1
        assert mock_soft.await_count == 3
        assert mock_perm.await_count == 2

