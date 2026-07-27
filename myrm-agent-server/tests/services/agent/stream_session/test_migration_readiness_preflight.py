"""Unit tests for migration readiness stream preflight."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.memory.archive import MemoryImportReadiness, MemoryImportReadinessIssue
from app.services.agent.params.models import MigrationReadinessAnchorRequest
from app.services.agent.stream_session.entitlement_gap_preflight import (
    reset_capability_gap_emission_tracker,
)
from app.services.agent.stream_session.migration_readiness_preflight import (
    build_migration_readiness_gap_sse_event_from_readiness,
    resolve_and_build_migration_readiness_gap_sse_event,
)


def test_migration_readiness_gap_from_readiness_none_for_ready() -> None:
    reset_capability_gap_emission_tracker()
    assert (
        build_migration_readiness_gap_sse_event_from_readiness(
            message_id="msg-1",
            import_batch_id="batch-ready",
            readiness=MemoryImportReadiness(status="ready", issues=[]),
            chat_id="chat-1",
            locale="en",
        )
        is None
    )


def test_migration_readiness_gap_from_readiness_emits_for_warning() -> None:
    reset_capability_gap_emission_tracker()
    event = build_migration_readiness_gap_sse_event_from_readiness(
        message_id="msg-1",
        import_batch_id="batch-warning",
        readiness=MemoryImportReadiness(
            status="warning",
            issues=[
                MemoryImportReadinessIssue(
                    code="workspace_rules_skipped",
                    severity="warning",
                    params={"count": 1},
                    settings_path="/settings/memory?sub=migration",
                )
            ],
        ),
        chat_id="chat-1",
        locale="en",
    )
    assert event is not None
    data = event["data"]
    assert isinstance(data, dict)
    assert data.get("reason") == "migration_readiness_warning"


def test_migration_readiness_gap_from_readiness_emits_for_critical() -> None:
    reset_capability_gap_emission_tracker()
    event = build_migration_readiness_gap_sse_event_from_readiness(
        message_id="msg-1",
        import_batch_id="batch-critical",
        readiness=MemoryImportReadiness(
            status="critical",
            issues=[
                MemoryImportReadinessIssue(
                    code="providers_not_configured",
                    severity="critical",
                    settings_path="/settings/models",
                )
            ],
        ),
        chat_id="chat-1",
        locale="en",
    )
    assert event is not None
    assert event["type"] == "capability_gap"
    data = event["data"]
    assert isinstance(data, dict)
    assert data.get("tool_id") == "migration_import"
    assert data.get("reason") == "migration_readiness_critical"
    assert data.get("settings_path") == "/settings/models"
    assert data.get("import_batch_id") == "batch-critical"
    assert isinstance(data.get("display_message"), str)


def test_migration_readiness_gap_from_readiness_uses_issue_settings_path() -> None:
    reset_capability_gap_emission_tracker()
    event = build_migration_readiness_gap_sse_event_from_readiness(
        message_id="msg-1",
        import_batch_id="batch-mcp",
        readiness=MemoryImportReadiness(
            status="warning",
            issues=[
                MemoryImportReadinessIssue(
                    code="mcp_servers_imported_disabled",
                    severity="warning",
                    params={"count": 2},
                    settings_path="/settings/mcp",
                )
            ],
        ),
        chat_id="chat-mcp",
        locale="en",
    )
    assert event is not None
    data = event["data"]
    assert isinstance(data, dict)
    assert data.get("settings_path") == "/settings/mcp"
    assert data.get("reason") == "migration_readiness_warning"


def test_migration_readiness_gap_dedup_within_cooldown() -> None:
    reset_capability_gap_emission_tracker()
    readiness = MemoryImportReadiness(
        status="critical",
        issues=[
            MemoryImportReadinessIssue(
                code="providers_not_configured",
                severity="critical",
                settings_path="/settings/models",
            )
        ],
    )
    first = build_migration_readiness_gap_sse_event_from_readiness(
        message_id="msg-1",
        import_batch_id="batch-dedup",
        readiness=readiness,
        chat_id="chat-dedup",
        locale="zh",
    )
    second = build_migration_readiness_gap_sse_event_from_readiness(
        message_id="msg-2",
        import_batch_id="batch-dedup",
        readiness=readiness,
        chat_id="chat-dedup",
        locale="zh",
    )
    assert first is not None
    assert second is None


@pytest.mark.asyncio
async def test_resolve_and_build_migration_readiness_gap_live_warning_mcp_path() -> (
    None
):
    reset_capability_gap_emission_tracker()
    readiness = MemoryImportReadiness(
        status="warning",
        issues=[
            MemoryImportReadinessIssue(
                code="mcp_servers_imported_disabled",
                severity="warning",
                params={"count": 2},
                settings_path="/settings/mcp",
            )
        ],
    )
    mock_db = AsyncMock()
    mock_session_factory = MagicMock()
    mock_session_factory.return_value.__aenter__.return_value = mock_db
    mock_session_factory.return_value.__aexit__.return_value = None

    with (
        patch(
            "app.services.agent.stream_session.migration_readiness_preflight.get_session_factory",
            return_value=mock_session_factory,
        ),
        patch(
            "app.services.agent.stream_session.migration_readiness_preflight.MemoryImportSessionService"
        ) as mock_service_cls,
    ):
        mock_service = mock_service_cls.return_value
        mock_service.resolve_live_import_readiness = AsyncMock(return_value=readiness)
        event, status = await resolve_and_build_migration_readiness_gap_sse_event(
            message_id="msg-live",
            migration_readiness_anchor=MigrationReadinessAnchorRequest(
                import_batch_id="batch-live-mcp",
                readiness_status="ready",
            ),
            chat_id="chat-live",
            locale="en",
        )

    assert status == "warning"
    assert event is not None
    data = event["data"]
    assert isinstance(data, dict)
    assert data.get("settings_path") == "/settings/mcp"
    assert data.get("reason") == "migration_readiness_warning"
    mock_service.resolve_live_import_readiness.assert_awaited_once_with(
        "batch-live-mcp"
    )


@pytest.mark.asyncio
async def test_resolve_and_build_migration_readiness_gap_none_without_anchor() -> None:
    reset_capability_gap_emission_tracker()
    event, status = await resolve_and_build_migration_readiness_gap_sse_event(
        message_id="msg-1",
        migration_readiness_anchor=None,
        chat_id="chat-1",
        locale="en",
    )
    assert event is None
    assert status is None
