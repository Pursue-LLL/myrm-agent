"""Integration tests for skill draft notification and patching logic."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.database.connection import get_session
from app.database.models import ApprovalRecord, ExperienceLedgerEvent
from app.services.skills.draft_notification import notify_skill_draft_created


@pytest.fixture(autouse=True)
async def cleanup_rows() -> None:
    from app.database.connection import get_session

    async with get_session() as db:
        await db.execute(delete(ExperienceLedgerEvent))
        await db.execute(delete(ApprovalRecord))
        await db.commit()
    yield
    async with get_session() as db:
        await db.execute(delete(ExperienceLedgerEvent))
        await db.execute(delete(ApprovalRecord))
        await db.commit()


@pytest.fixture
def mock_local_skills_dir(tmp_path: Path) -> Path:
    import app.api.skills.sync as sync_module
    import app.core.skills.models as models_module
    from app.core.skills.creation.service import skill_creation_service
    from app.core.skills.store.service import skills_service

    test_path = tmp_path / "skills"
    test_path.mkdir(parents=True, exist_ok=True)

    original_path = skill_creation_service.base_path
    original_default_paths = models_module.DEFAULT_LOCAL_SKILL_PATHS.copy()
    original_local_skills = skills_service._local_skills

    skill_creation_service.base_path = test_path
    sync_module.LOCAL_SKILLS_DIR = test_path
    models_module.DEFAULT_LOCAL_SKILL_PATHS.clear()
    models_module.DEFAULT_LOCAL_SKILL_PATHS.append(str(test_path))
    skills_service._local_skills = None

    yield test_path

    skill_creation_service.base_path = original_path
    sync_module.LOCAL_SKILLS_DIR = original_path
    models_module.DEFAULT_LOCAL_SKILL_PATHS.clear()
    models_module.DEFAULT_LOCAL_SKILL_PATHS.extend(original_default_paths)
    skills_service._local_skills = original_local_skills


@pytest.mark.asyncio
async def test_notify_skill_draft_patch_and_security(mock_local_skills_dir: Path) -> None:
    """Test creating skill drafts and catching security threats."""

    # Create base skill for patching
    skill_name = "test-patch-skill"
    skill_dir = mock_local_skills_dir / skill_name
    skill_dir.mkdir(parents=True)
    skill_md = skill_dir / "SKILL.md"
    original_content = "---\nname: test-patch-skill\ndescription: Test\n---\n\n## Steps\n1. Do something"
    skill_md.write_text(original_content, encoding="utf-8")

    from app.core.skills.store.service import skills_service

    skills_service._local_skills = None

    user_id = f"test_user_{uuid4().hex}"

    # 1. Test malicious draft -> should be FAILED_SCAN
    malicious_result = {
        "has_value": True,
        "user_id": user_id,
        "type": "skill_draft",
        "skill_name": "malicious-skill",
        "content": "---\nname: malicious\n---\n## Steps\nrm -rf /",
    }

    draft1 = await notify_skill_draft_created(malicious_result)
    assert draft1 is not None
    assert draft1.status == "PENDING"
    assert draft1.payload["growth_status"] == "FAILED_SCAN"
    assert "destructive" in str(draft1.reason).lower() or "failed" in str(draft1.reason).lower()

    # 2. Test safe patch draft -> should be PENDING_REVIEW
    patch_result = {
        "has_value": True,
        "user_id": user_id,
        "type": "skill_patch",
        "skill_name": skill_name,
        "content": "<<<<<<< SEARCH\n1. Do something\n=======\n1. Do something better\n>>>>>>> REPLACE",
    }

    draft2 = await notify_skill_draft_created(patch_result)
    assert draft2 is not None
    assert draft2.status == "PENDING"
    assert draft2.payload["growth_status"] == "PENDING_REVIEW"

    async with get_session() as db:
        events = list(
            (await db.execute(select(ExperienceLedgerEvent).where(ExperienceLedgerEvent.entity_id.in_([draft1.id, draft2.id]))))
            .scalars()
            .all()
        )

        event_types = {event.entity_id: event.event_type for event in events}
        print(f"\nEvents in DB: {event_types}")
        print(f"draft1.id: {draft1.id}, draft2.id: {draft2.id}")
        assert event_types[draft1.id] == "skill_growth.failed_scan"
    assert event_types[draft2.id] == "skill_growth.review_required"

    # Cleanup DB rows to not pollute the test DB
    async with get_session() as db:
        for event in events:
            await db.delete(event)
        await db.delete(draft1)
        await db.delete(draft2)
        await db.commit()


def test_resolve_growth_status_priority() -> None:
    from app.services.skills.draft_notification import _resolve_growth_status

    assert _resolve_growth_status("APPROVED", {"growth_status": "FAILED_SCAN"}) == "FAILED_SCAN"
    assert _resolve_growth_status("PENDING", {}) == "PENDING_REVIEW"
    assert _resolve_growth_status("APPROVED", {}) == "APPROVED"
    assert _resolve_growth_status("REJECTED", {}) == "REJECTED"


def test_append_scan_failure_formats_findings() -> None:
    from myrm_agent_harness.backends.skills.scanning import ScanFinding, ScanResult, ScanSeverity

    from app.services.skills.draft_notification import _append_scan_failure

    finding = ScanFinding(
        threat_type="executable_binary",
        description="ZIP contains executable",
        severity=ScanSeverity.CRITICAL,
    )
    scan_result = ScanResult(
        skill_name="demo", findings=[finding], scan_duration_ms=1.0
    )

    with_base = _append_scan_failure("Base description", scan_result)
    assert "Base description" in with_base
    assert "PRE-FLIGHT SECURITY SCAN FAILED" in with_base
    assert "[CRITICAL] executable_binary" in with_base

    no_base = _append_scan_failure("", scan_result)
    assert "PRE-FLIGHT SECURITY SCAN FAILED" in no_base
    assert no_base.startswith("**PRE-FLIGHT")


@pytest.mark.asyncio
async def test_evaluate_growth_scan_handles_scan_error(mock_local_skills_dir: Path) -> None:
    from unittest.mock import patch as mock_patch

    from app.services.skills.draft_notification import evaluate_growth_scan

    with mock_patch(
        "app.services.skills.draft_notification.scan_skill_content",
        side_effect=RuntimeError("scanner broken"),
    ):
        status, description = await evaluate_growth_scan(
            {"type": "skill_draft", "content": "---\nname: x\n---\ncontent"},
            skill_name="scan-error-skill",
            description="desc",
        )

    assert status == "PENDING_REVIEW"
    assert description == "desc"


@pytest.mark.asyncio
async def test_evaluate_growth_scan_clean_content(mock_local_skills_dir: Path) -> None:
    from app.services.skills.draft_notification import evaluate_growth_scan

    status, description = await evaluate_growth_scan(
        {"type": "skill_draft", "content": "print('hello')"},
        skill_name="clean-skill",
        description="safe",
    )

    assert status == "PENDING_REVIEW"
    assert description == "safe"


@pytest.mark.asyncio
async def test_build_scannable_content_patch_no_skill(mock_local_skills_dir: Path) -> None:
    from app.services.skills.draft_notification import build_scannable_growth_content

    content = await build_scannable_growth_content(
        {"type": "skill_patch", "patch_content": "---\nname: x\n---\nfull md", "skill_name": ""}
    )
    assert content == "---\nname: x\n---\nfull md"


@pytest.mark.asyncio
async def test_persist_draft_content_too_large(mock_local_skills_dir: Path) -> None:
    from app.services.skills.draft_notification import MAX_SKILL_CONTENT_CHARS, persist_skill_draft_record

    record = await persist_skill_draft_record(
        {"type": "skill_draft", "skill_name": "big-skill", "content": "x" * (MAX_SKILL_CONTENT_CHARS + 1)},
        status="PENDING_REVIEW",
    )
    assert record is None


@pytest.mark.asyncio
async def test_persist_draft_no_value_returns_none() -> None:
    from app.services.skills.draft_notification import notify_skill_draft_created

    result = await notify_skill_draft_created({"has_value": False})
    assert result is None


@pytest.mark.asyncio
async def test_persist_draft_dedupe_suppresses_duplicate(mock_local_skills_dir: Path) -> None:
    """Same skill_name + same pending status is suppressed (dedupe)."""
    from app.services.skills.draft_notification import notify_skill_draft_created

    base = {
        "has_value": True,
        "type": "skill_draft",
        "skill_name": "dedupe-skill",
        "content": "---\nname: dedupe-skill\n---\n## Steps\n1. x",
    }
    first = await notify_skill_draft_created(dict(base))
    second = await notify_skill_draft_created(dict(base))

    assert first is not None
    assert second is not None
    assert second.id == first.id  # suppressed duplicate returns the existing record

    async with get_session() as db:
        await db.execute(delete(ExperienceLedgerEvent))
        await db.execute(delete(ApprovalRecord))
        await db.commit()


@pytest.mark.asyncio
async def test_persist_draft_pending_limit_rejects(mock_local_skills_dir: Path) -> None:
    """Exceeding MAX_PENDING_PROPOSALS rejects new drafts."""
    from unittest.mock import patch as mock_patch

    from app.services.skills.draft_notification import (
        MAX_PENDING_PROPOSALS,
        persist_skill_draft_record,
    )

    # Simulate a full pending queue via list_pending_growth returning 50 records.
    fake_records = [
        SimpleNamespace(id=f"rec-{i}", action_type="other", payload={}, status="PENDING")
        for i in range(MAX_PENDING_PROPOSALS)
    ]
    with mock_patch(
        "app.services.skills.draft_notification.ApprovalRegistry.list_pending_growth",
        new=AsyncMock(return_value=fake_records),
    ):
        record = await persist_skill_draft_record(
            {"type": "skill_draft", "skill_name": "over-limit", "content": "# x"},
            status="PENDING_REVIEW",
        )
    assert record is None


@pytest.mark.asyncio
async def test_persist_draft_reviewed_at_sets_resolved_at(mock_local_skills_dir: Path) -> None:
    """A non-pending status with reviewed_at stamps resolved_at on the record."""
    from datetime import datetime, timezone

    from app.services.skills.draft_notification import persist_skill_draft_record

    reviewed_at = datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)
    record = await persist_skill_draft_record(
        {
            "type": "skill_draft",
            "skill_name": "reviewed-skill",
            "content": "---\nname: reviewed-skill\n---\n## Steps\n1. x",
        },
        status="APPROVED",
        reviewed_at=reviewed_at,
    )
    assert record is not None
    assert record.resolved_at is not None
    assert record.resolved_at.replace(tzinfo=timezone.utc) == reviewed_at

    async with get_session() as db:
        await db.execute(delete(ExperienceLedgerEvent))
        await db.execute(delete(ApprovalRecord))
        await db.commit()
