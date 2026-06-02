"""Integration tests for skill draft notification and patching logic."""

from pathlib import Path
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
