"""
[INPUT]
- app.api.skills.test_fixtures_evolution::(seed_evolution_proposal, SeedEvolutionProposalRequest) (POS: Dev-only fixture for the evolution proposal review Chrome E2E; gated by is_local_mode())
- app.services.skills.evolution_reviews::(get_evolution_review_record, list_evolution_review_records) (POS: 以 ApprovalRecord 为唯一事实源的 evolution 审核生命周期服务)
- app.services.skills.evolution_review.disk_content::apply_content_update (POS: Evolution 全量内容落盘与回滚)
[OUTPUT]
- Tests that the route answers 404 outside local mode and for a skill that is not on disk without recording anything,
  and that the proposal it records is a pending one for the skill as it is on disk, which applies to that file.
[POS]
The proposal the Chrome E2E approves is pinned here in-process: what the route records, and that the production apply
accepts it, without the browser stack.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import delete

import app.api.skills.test_fixtures_evolution as fixtures
from app.core.skills.providers.local import compute_local_skill_id
from app.database.connection import get_session
from app.database.models import ApprovalRecord, Base, ExperienceLedgerEvent
from app.platform_utils import get_database_engine
from app.services.skills.evolution_review.disk_content import apply_content_update
from app.services.skills.evolution_review.persistence import load_approval_record
from app.services.skills.evolution_review.types import approval_payload
from app.services.skills.evolution_reviews import (
    EvolutionApplyStatus,
    EvolutionGrowthStatus,
    get_evolution_review_record,
    list_evolution_review_records,
)

_SKILL_MD = "---\nname: report-builder\ndescription: Build the weekly report.\n---\n\n## Steps\n1. first-step\n"
_REQUEST = fixtures.SeedEvolutionProposalRequest(dir_name="report-builder", marker="added-step")


@pytest.fixture(autouse=True)
async def ensure_tables() -> AsyncIterator[None]:
    engine = get_database_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with get_session() as db:
        await db.execute(delete(ExperienceLedgerEvent))
        await db.execute(delete(ApprovalRecord))
        await db.commit()


@pytest.fixture
def skills_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "skills"
    directory.mkdir()
    monkeypatch.setattr(fixtures, "LOCAL_SKILLS_DIR", directory)
    monkeypatch.setattr(fixtures, "is_local_mode", lambda: True)
    return directory


@pytest.fixture
def skill_md(skills_dir: Path) -> Path:
    path = skills_dir / "report-builder" / "SKILL.md"
    path.parent.mkdir()
    path.write_text(_SKILL_MD, encoding="utf-8")
    return path


@pytest.fixture
def snapshot() -> Iterator[AsyncMock]:
    """The version-snapshot service is not what the apply here is for."""
    with patch("app.services.skills.write_orchestrator.persist_skill_md_snapshot", new=AsyncMock()) as persist:
        yield persist


async def test_the_route_does_not_exist_outside_local_mode(skill_md: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fixtures, "is_local_mode", lambda: False)

    with pytest.raises(HTTPException) as refused:
        await fixtures.seed_evolution_proposal(_REQUEST)

    assert refused.value.status_code == 404
    assert await list_evolution_review_records() == []


async def test_a_skill_that_is_not_on_disk_is_answered_with_404_and_records_nothing(skills_dir: Path) -> None:
    with pytest.raises(HTTPException) as refused:
        await fixtures.seed_evolution_proposal(_REQUEST)

    assert refused.value.status_code == 404
    assert await list_evolution_review_records() == []


async def test_the_recorded_proposal_is_pending_for_the_file_on_disk_and_applies_to_it(
    skills_dir: Path, skill_md: Path, snapshot: AsyncMock
) -> None:
    answer = await fixtures.seed_evolution_proposal(_REQUEST)

    record = await get_evolution_review_record(answer["evolution_id"])
    assert record is not None
    assert answer["skill_id"] == record.skill_id == compute_local_skill_id(skills_dir / "report-builder")
    assert (record.status, record.apply_status) == (EvolutionGrowthStatus.PENDING_REVIEW, EvolutionApplyStatus.NOT_APPLIED)
    assert (record.skill_name, record.skill_path, record.original_content) == ("report-builder", str(skill_md), _SKILL_MD)

    approval = await load_approval_record(record.id)
    assert approval is not None
    payload = approval_payload(approval)
    assert payload is not None
    store = MagicMock()
    store.get_skill.return_value = None
    store.save_skill = AsyncMock()

    await apply_content_update(payload, store)

    applied = skill_md.read_text(encoding="utf-8")
    assert "1. first-step" in applied and applied.rstrip().endswith("2. added-step")
