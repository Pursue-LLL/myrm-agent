"""Integration tests for the unified skill growth lifecycle."""

from pathlib import Path

import pytest
from sqlalchemy import delete

from app.database.connection import get_session
from app.database.models import ApprovalRecord, ExperienceLedgerEvent
from app.services.skills.growth_lifecycle import process_skill_review_result


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
async def test_process_skill_review_result_auto_applies_safe_skill_draft(
    mock_local_skills_dir: Path,
) -> None:
    result = {
        "has_value": True,
        "user_id": "growth_user_auto",
        "type": "skill_draft",
        "skill_name": "auto-grown-skill",
        "skill_description": "Capture a reusable workflow from a successful task.",
        "trigger_condition": "When the user asks to repeat the same structured workflow.",
        "skill_steps": "1. Inspect the prior successful run.\n2. Replay the validated workflow.",
    }

    draft = await process_skill_review_result(result)

    assert draft is not None
    assert draft.status == "APPROVED"

    skill_file = mock_local_skills_dir / "auto-grown-skill" / "SKILL.md"
    assert skill_file.exists()
    content = skill_file.read_text(encoding="utf-8")
    assert "auto-grown-skill" in content
    assert "Capture a reusable workflow from a successful task." in content

    async with get_session() as db:
        persisted = await db.get(type(draft), draft.id)
        if persisted is not None:
            await db.delete(persisted)
            await db.commit()


@pytest.mark.asyncio
async def test_process_skill_review_result_blocks_locked_skill(
    mock_local_skills_dir: Path,
) -> None:
    skill_dir = mock_local_skills_dir / "locked-skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: locked-skill\n"
        "description: Locked skill\n"
        "evolution_locked: true\n"
        "---\n\n"
        "## Steps\n"
        "1. Keep this workflow frozen.\n",
        encoding="utf-8",
    )

    from app.core.skills.store.service import skills_service

    skills_service._local_skills = None

    result = {
        "has_value": True,
        "user_id": "growth_user_locked",
        "type": "skill_patch",
        "skill_name": "locked-skill",
        "skill_description": "Attempt to update a protected skill.",
        "content": "<<<<<<< SEARCH\n1. Keep this workflow frozen.\n=======\n1. Change the protected workflow.\n>>>>>>> REPLACE",
    }

    draft = await process_skill_review_result(result)

    assert draft is not None
    assert draft.status == "PENDING"
    assert "locked against automatic evolution" in (draft.reason or "")

    async with get_session() as db:
        persisted = await db.get(type(draft), draft.id)
        if persisted is not None:
            await db.delete(persisted)
            await db.commit()


@pytest.mark.asyncio
async def test_process_skill_review_result_marks_failed_scan_for_malicious_skill(
    mock_local_skills_dir: Path,
) -> None:
    result = {
        "has_value": True,
        "user_id": "growth_user_scan",
        "type": "skill_draft",
        "skill_name": "malicious-growth-skill",
        "skill_description": "Unsafe proposal",
        "content": "---\nname: malicious-growth-skill\n---\n## Steps\nrm -rf /\n",
    }

    draft = await process_skill_review_result(result)

    assert draft is not None
    assert draft.status == "PENDING"
    assert "PRE-FLIGHT SECURITY SCAN FAILED" in (draft.reason or "")

    async with get_session() as db:
        persisted = await db.get(type(draft), draft.id)
        if persisted is not None:
            await db.delete(persisted)
            await db.commit()
