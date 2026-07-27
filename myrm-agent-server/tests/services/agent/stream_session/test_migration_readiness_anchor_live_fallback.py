"""Tests for migration readiness first-turn live fallback."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.memory.archive import MemoryImportReadiness
from app.services.agent.params import AgentRequest
from app.services.agent.params.models import MigrationReadinessAnchorRequest
from app.services.agent.stream_session.migration_readiness_anchor import (
    record_migration_first_turn_outcome,
)


@pytest.mark.asyncio
async def test_record_migration_first_turn_outcome_live_resolves_when_preflight_missing() -> None:
    request = AgentRequest(
        query="hello",
        chat_id="chat-1",
        message_id="msg-1",
        migration_readiness_anchor=MigrationReadinessAnchorRequest(
            import_batch_id="batch-fallback",
            readiness_status="critical",
        ),
    )
    live_readiness = MemoryImportReadiness(status="ready", issues=[])

    mock_db = AsyncMock()
    mock_session_factory = MagicMock()
    mock_session_factory.return_value.__aenter__.return_value = mock_db
    mock_session_factory.return_value.__aexit__.return_value = None

    with (
        patch(
            "app.services.agent.stream_session.migration_readiness_anchor.get_session_factory",
            return_value=mock_session_factory,
        ),
        patch(
            "app.services.agent.stream_session.migration_readiness_anchor.MemoryImportSessionService"
        ) as mock_service_cls,
    ):
        mock_service = mock_service_cls.return_value
        mock_service.resolve_live_import_readiness = AsyncMock(return_value=live_readiness)
        mock_service.save_post_import_first_turn_outcome = AsyncMock()
        await record_migration_first_turn_outcome(
            request=request,
            had_fatal_error=False,
            has_assistant_content=True,
            live_readiness_status=None,
        )

    mock_service.resolve_live_import_readiness.assert_awaited_once_with("batch-fallback")
    mock_service.save_post_import_first_turn_outcome.assert_awaited_once_with(
        import_batch_id="batch-fallback",
        readiness_status="ready",
        outcome="success",
        had_fatal_error=False,
        chat_id="chat-1",
        message_id="msg-1",
    )


@pytest.mark.asyncio
async def test_record_migration_first_turn_outcome_skips_when_live_resolve_fails() -> None:
    request = AgentRequest(
        query="hello",
        chat_id="chat-1",
        message_id="msg-1",
        migration_readiness_anchor=MigrationReadinessAnchorRequest(
            import_batch_id="batch-fail",
            readiness_status="critical",
        ),
    )

    mock_db = AsyncMock()
    mock_session_factory = MagicMock()
    mock_session_factory.return_value.__aenter__.return_value = mock_db
    mock_session_factory.return_value.__aexit__.return_value = None

    with (
        patch(
            "app.services.agent.stream_session.migration_readiness_anchor.get_session_factory",
            return_value=mock_session_factory,
        ),
        patch(
            "app.services.agent.stream_session.migration_readiness_anchor.MemoryImportSessionService"
        ) as mock_service_cls,
    ):
        mock_service = mock_service_cls.return_value
        mock_service.resolve_live_import_readiness = AsyncMock(side_effect=RuntimeError("db down"))
        mock_service.save_post_import_first_turn_outcome = AsyncMock()
        await record_migration_first_turn_outcome(
            request=request,
            had_fatal_error=False,
            has_assistant_content=True,
            live_readiness_status=None,
        )

    mock_service.save_post_import_first_turn_outcome.assert_not_awaited()
