"""Unit tests for migration readiness stream preflight."""

from __future__ import annotations

from app.schemas.memory.archive import MemoryImportReadiness, MemoryImportReadinessIssue
from app.services.agent.params.models import MigrationReadinessAnchorRequest
from app.services.agent.stream_session.entitlement_gap_preflight import (
    reset_capability_gap_emission_tracker,
)
from app.services.agent.stream_session.migration_readiness_preflight import (
    build_migration_readiness_gap_sse_event,
    build_migration_readiness_gap_sse_event_from_readiness,
)


def test_migration_readiness_gap_none_without_anchor() -> None:
    reset_capability_gap_emission_tracker()
    assert (
        build_migration_readiness_gap_sse_event(
            message_id="msg-1",
            migration_readiness_anchor=None,
            chat_id="chat-1",
            locale="en",
        )
        is None
    )


def test_migration_readiness_gap_none_for_ready_anchor() -> None:
    reset_capability_gap_emission_tracker()
    event = build_migration_readiness_gap_sse_event(
        message_id="msg-1",
        migration_readiness_anchor=MigrationReadinessAnchorRequest(
            import_batch_id="batch-ready",
            readiness_status="ready",
        ),
        chat_id="chat-1",
        locale="en",
    )
    assert event is None


def test_migration_readiness_gap_emits_for_warning_anchor() -> None:
    reset_capability_gap_emission_tracker()
    event = build_migration_readiness_gap_sse_event(
        message_id="msg-1",
        migration_readiness_anchor=MigrationReadinessAnchorRequest(
            import_batch_id="batch-warning",
            readiness_status="warning",
        ),
        chat_id="chat-1",
        locale="en",
    )
    assert event is not None
    data = event["data"]
    assert isinstance(data, dict)
    assert data.get("reason") == "migration_readiness_warning"


def test_migration_readiness_gap_emits_for_critical_anchor() -> None:
    reset_capability_gap_emission_tracker()
    event = build_migration_readiness_gap_sse_event(
        message_id="msg-1",
        migration_readiness_anchor=MigrationReadinessAnchorRequest(
            import_batch_id="batch-critical",
            readiness_status="critical",
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
    anchor = MigrationReadinessAnchorRequest(
        import_batch_id="batch-dedup",
        readiness_status="critical",
    )
    first = build_migration_readiness_gap_sse_event(
        message_id="msg-1",
        migration_readiness_anchor=anchor,
        chat_id="chat-dedup",
        locale="zh",
    )
    second = build_migration_readiness_gap_sse_event(
        message_id="msg-2",
        migration_readiness_anchor=anchor,
        chat_id="chat-dedup",
        locale="zh",
    )
    assert first is not None
    assert second is None


def test_migration_readiness_gap_accepts_camel_case_anchor_dict() -> None:
    """AgentRequest JSON may arrive as camelCase dict before pydantic normalization."""
    reset_capability_gap_emission_tracker()
    event = build_migration_readiness_gap_sse_event(
        message_id="msg-1",
        migration_readiness_anchor={
            "importBatchId": "batch-resume",
            "readinessStatus": "critical",
        },
        chat_id="chat-1",
        locale="en",
    )
    assert event is not None
    data = event["data"]
    assert isinstance(data, dict)
    assert data.get("import_batch_id") == "batch-resume"
