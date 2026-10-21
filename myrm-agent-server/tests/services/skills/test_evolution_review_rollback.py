"""rollback_content_update: forks are removed, edited skills get their original content back."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from myrm_agent_harness.agent.skills.evolution.core.types import (
    EnvironmentFingerprint,
    EvolutionType,
    SkillLineage,
    SkillRecord,
)

from app.services.skills.evolution_review.disk_content import rollback_content_update
from app.services.skills.evolution_review.types import EvolutionApprovalPayload

_FORK_ID = "fork_ab12cd34"


def _payload(skill_path: Path, *, evolution_type: EvolutionType, original_content: str) -> EvolutionApprovalPayload:
    return EvolutionApprovalPayload(
        skill_id=_FORK_ID,
        skill_name="demo-skill-fork",
        skill_path=str(skill_path),
        evolution_type=evolution_type.value,
        reason="rollback test",
        original_content=original_content,
        evolved_content="evolved",
        confidence=0.9,
        test_passed=True,
    )


def _fork_record(skill_path: Path) -> SkillRecord:
    return SkillRecord(
        skill_id=_FORK_ID,
        name="demo-skill-fork",
        description="",
        content="evolved",
        path=str(skill_path),
        lineage=SkillLineage(evolution_type=EvolutionType.DERIVED, parent_id=_FORK_ID),
        environment=EnvironmentFingerprint(custom_tags={"scope_agent_id": "agent-1"}),
    )


def _store(record: SkillRecord | None = None) -> MagicMock:
    store = MagicMock()
    store.get_skill.return_value = record
    store.delete_skill = AsyncMock()
    store.save_skill = AsyncMock()
    return store


@pytest.mark.asyncio
async def test_rolling_back_a_fork_removes_its_files_and_record_without_errors(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    skill_dir = tmp_path / "demo-skill-fork"
    skill_dir.mkdir()
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text("evolved", encoding="utf-8")
    store = _store(_fork_record(skill_file))

    with caplog.at_level(logging.ERROR):
        await rollback_content_update(_payload(skill_file, evolution_type=EvolutionType.DERIVED, original_content=""), store)

    assert not skill_dir.exists()
    store.delete_skill.assert_awaited_once_with(_FORK_ID)
    assert not caplog.records


@pytest.mark.asyncio
async def test_rolling_back_an_edit_restores_the_original_content(tmp_path: Path) -> None:
    skill_file = tmp_path / "demo-skill" / "SKILL.md"
    skill_file.parent.mkdir()
    skill_file.write_text("evolved", encoding="utf-8")
    store = _store()

    await rollback_content_update(_payload(skill_file, evolution_type=EvolutionType.FIX, original_content="original"), store)

    assert skill_file.read_text(encoding="utf-8") == "original"
    saved: SkillRecord = store.save_skill.await_args.args[0]
    assert saved.content == "original"
    assert saved.lineage.change_summary == "Rolled back"
    store.delete_skill.assert_not_awaited()
