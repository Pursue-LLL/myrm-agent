"""apply_content_update: what it refuses before writing, and how it undoes its file write when recording fails."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.agent.skills.evolution.core.types import EvolutionType, SkillRecord

from app.services.skills.evolution_review import disk_content
from app.services.skills.evolution_review.disk_content import apply_content_update
from app.services.skills.evolution_review.types import EvolutionApplyError, EvolutionApprovalPayload

_UNSUPPORTED_TYPE = "optimize_description"
_ORIGINAL = "---\nname: demo-skill\ndescription: The skill as the user has it.\n---\n\n# Demo\n"
_EVOLVED = "---\nname: demo-skill\ndescription: The skill after the evolution.\n---\n\n# Demo, fixed\n"
_UNDECODABLE = b"\xff\xfe not UTF-8 \x80"


def _payload(skill_file: Path, evolution_type: str = "fix", evolved_content: str = _EVOLVED) -> EvolutionApprovalPayload:
    return EvolutionApprovalPayload(
        skill_id="skill-1",
        skill_name="demo-skill",
        skill_path=str(skill_file),
        evolution_type=evolution_type,
        reason="apply test",
        original_content=_ORIGINAL,
        evolved_content=evolved_content,
        confidence=0.9,
        test_passed=True,
    )


def _store(save_error: Exception | None = None) -> MagicMock:
    store = MagicMock()
    store.get_skill.return_value = None
    store.save_skill = AsyncMock(side_effect=save_error)
    return store


@pytest.fixture
def skill_file(tmp_path: Path) -> Path:
    path = tmp_path / "demo-skill" / "SKILL.md"
    path.parent.mkdir()
    path.write_text(_ORIGINAL, encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def snapshot() -> Iterator[AsyncMock]:
    """The version-snapshot service needs the database; it is not what these tests exercise."""
    with patch("app.services.skills.write_orchestrator.persist_skill_md_snapshot", new=AsyncMock()) as persist:
        yield persist


@pytest.mark.asyncio
@pytest.mark.parametrize("evolution_type", [EvolutionType.FIX, EvolutionType.DERIVED, EvolutionType.CAPTURED])
async def test_applying_a_supported_type_writes_the_evolved_content(skill_file: Path, evolution_type: EvolutionType) -> None:
    store = _store()

    await apply_content_update(_payload(skill_file, evolution_type.value), store)

    assert skill_file.read_text(encoding="utf-8") == _EVOLVED
    saved: SkillRecord = store.save_skill.await_args.args[0]
    assert saved.lineage.evolution_type is evolution_type


@pytest.mark.asyncio
async def test_applying_an_unsupported_type_is_refused_before_the_skill_file_is_touched(skill_file: Path) -> None:
    store = _store()

    with pytest.raises(EvolutionApplyError, match=_UNSUPPORTED_TYPE):
        await apply_content_update(_payload(skill_file, _UNSUPPORTED_TYPE), store)

    assert skill_file.read_text(encoding="utf-8") == _ORIGINAL
    assert list(skill_file.parent.iterdir()) == [skill_file]
    store.save_skill.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "evolved_content",
    [
        pytest.param("evolved", id="no-frontmatter"),
        pytest.param("---\nname: demo-skill\ndescription: Never closed.\n", id="unclosed-frontmatter"),
        pytest.param("---\nname: demo-skill\ndescription: Use when: a colon breaks the YAML\n---\nbody\n", id="invalid-yaml"),
        pytest.param("---\nname: demo-skill\n---\nbody\n", id="no-description"),
        pytest.param(f"Here is the updated skill:\n{_EVOLVED}", id="text-before-frontmatter"),
    ],
)
async def test_content_the_loader_would_skip_is_refused_before_the_skill_file_is_touched(
    skill_file: Path, evolved_content: str, snapshot: AsyncMock
) -> None:
    store = _store()

    with pytest.raises(EvolutionApplyError, match="cannot be loaded"):
        await apply_content_update(_payload(skill_file, evolved_content=evolved_content), store)

    assert skill_file.read_text(encoding="utf-8") == _ORIGINAL
    assert list(skill_file.parent.iterdir()) == [skill_file]
    store.save_skill.assert_not_awaited()
    snapshot.assert_not_awaited()


@pytest.mark.asyncio
async def test_unloadable_content_does_not_create_the_skill_directory(tmp_path: Path) -> None:
    new_file = tmp_path / "new-skill" / "SKILL.md"

    with pytest.raises(EvolutionApplyError, match="cannot be loaded"):
        await apply_content_update(_payload(new_file, "captured", evolved_content="not a skill"), _store())

    assert not new_file.parent.exists()


@pytest.mark.asyncio
async def test_a_skill_without_a_name_in_its_frontmatter_is_applied(skill_file: Path) -> None:
    nameless = "---\ndescription: The loader falls back to the directory name.\n---\nbody\n"

    await apply_content_update(_payload(skill_file, evolved_content=nameless), _store())

    assert skill_file.read_text(encoding="utf-8") == nameless


@pytest.mark.asyncio
@pytest.mark.parametrize("original", [_ORIGINAL.encode(), _UNDECODABLE], ids=["utf8", "undecodable"])
async def test_a_failing_record_save_puts_the_earlier_file_back(skill_file: Path, original: bytes) -> None:
    skill_file.write_bytes(original)
    store = _store(save_error=RuntimeError("database is locked"))

    with pytest.raises(RuntimeError, match="database is locked"):
        await apply_content_update(_payload(skill_file), store)

    assert skill_file.read_bytes() == original
    assert list(skill_file.parent.iterdir()) == [skill_file]


@pytest.mark.asyncio
async def test_a_failing_snapshot_puts_the_earlier_file_back(skill_file: Path, snapshot: AsyncMock) -> None:
    snapshot.side_effect = RuntimeError("snapshot store is down")
    store = _store()

    with pytest.raises(RuntimeError, match="snapshot store is down"):
        await apply_content_update(_payload(skill_file), store)

    store.save_skill.assert_awaited_once()
    assert skill_file.read_text(encoding="utf-8") == _ORIGINAL
    assert list(skill_file.parent.iterdir()) == [skill_file]


@pytest.mark.asyncio
async def test_a_failed_apply_of_a_new_skill_removes_its_file_and_empty_directory(tmp_path: Path) -> None:
    new_file = tmp_path / "new-skill" / "SKILL.md"
    store = _store(save_error=RuntimeError("database is locked"))

    with pytest.raises(RuntimeError, match="database is locked"):
        await apply_content_update(_payload(new_file, "captured"), store)

    assert not new_file.parent.exists()


@pytest.mark.asyncio
async def test_a_failed_apply_keeps_a_directory_that_holds_other_files(tmp_path: Path) -> None:
    skill_dir = tmp_path / "new-skill"
    skill_dir.mkdir()
    (skill_dir / "notes.txt").write_text("keep me", encoding="utf-8")
    store = _store(save_error=RuntimeError("database is locked"))

    with pytest.raises(RuntimeError, match="database is locked"):
        await apply_content_update(_payload(skill_dir / "SKILL.md", "captured"), store)

    assert [path.name for path in skill_dir.iterdir()] == ["notes.txt"]


@pytest.mark.asyncio
async def test_the_original_error_is_raised_when_the_earlier_file_cannot_be_put_back(
    skill_file: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    real_write = disk_content._write_atomic
    writes: list[Path] = []

    def write_once(path: Path, data: bytes) -> None:
        writes.append(path)
        if len(writes) > 1:
            raise OSError("disk is full")
        real_write(path, data)

    monkeypatch.setattr(disk_content, "_write_atomic", write_once)
    store = _store(save_error=RuntimeError("database is locked"))

    with caplog.at_level(logging.ERROR), pytest.raises(RuntimeError, match="database is locked"):
        await apply_content_update(_payload(skill_file), store)

    assert "Could not restore" in caplog.text
    assert skill_file.read_text(encoding="utf-8") == _EVOLVED
