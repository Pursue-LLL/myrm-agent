"""apply_content_update: what it refuses before writing, and how it undoes its file write when recording fails."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.agent.skills.evolution.core.types import (
    EnvironmentFingerprint,
    EvolutionType,
    SkillLineage,
    SkillRecord,
)

from app.services.skills.evolution_review import disk_content
from app.services.skills.evolution_review.disk_content import apply_content_update, skill_file_hash
from app.services.skills.evolution_review.types import (
    REASON_SKILL_MD_UNLOADABLE,
    REASON_STALE_BASE,
    EvolutionApplyError,
    EvolutionApprovalPayload,
)

_UNSUPPORTED_TYPE = "optimize_description"
_ORIGINAL = "---\nname: demo-skill\ndescription: The skill as the user has it.\n---\n\n# Demo\n"
_EVOLVED = "---\nname: demo-skill\ndescription: The skill after the evolution.\n---\n\n# Demo, fixed\n"
_UNDECODABLE = b"\xff\xfe not UTF-8 \x80"


def _payload(
    skill_file: Path,
    evolution_type: str = "fix",
    evolved_content: str = _EVOLVED,
    base_content_hash: str | None = None,
) -> EvolutionApprovalPayload:
    return EvolutionApprovalPayload(
        skill_id="skill-1",
        skill_name="demo-skill",
        skill_path=str(skill_file),
        evolution_type=evolution_type,
        reason="apply test",
        original_content=_ORIGINAL,
        evolved_content=evolved_content,
        base_content_hash=base_content_hash,
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
async def test_the_store_keeps_the_text_written_for_an_agent_scoped_skill(skill_file: Path) -> None:
    store = _store()

    await apply_content_update(_payload(skill_file, EvolutionType.CAPTURED.value), store, agent_id="agent-1")

    written = skill_file.read_text(encoding="utf-8")
    assert "scope_agent_id: agent-1" in written
    saved: SkillRecord = store.save_skill.await_args.args[0]
    assert saved.content == written


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

    with pytest.raises(EvolutionApplyError, match="cannot be loaded") as refused:
        await apply_content_update(_payload(skill_file, evolved_content=evolved_content), store)

    assert refused.value.code == REASON_SKILL_MD_UNLOADABLE
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
    real_write = disk_content.atomic_write
    writes: list[Path] = []

    def write_once(path: Path, data: bytes) -> None:
        writes.append(path)
        if len(writes) > 1:
            raise OSError("disk is full")
        real_write(path, data)

    monkeypatch.setattr(disk_content, "atomic_write", write_once)
    store = _store(save_error=RuntimeError("database is locked"))

    with caplog.at_level(logging.ERROR), pytest.raises(RuntimeError, match="database is locked"):
        await apply_content_update(_payload(skill_file), store)

    assert "Could not restore" in caplog.text
    assert skill_file.read_text(encoding="utf-8") == _EVOLVED


def _edited_by_the_user(skill_file: Path) -> str:
    edited = _ORIGINAL + "\nA paragraph the user added by hand.\n"
    skill_file.write_text(edited, encoding="utf-8")
    return edited


@pytest.mark.asyncio
async def test_a_skill_edited_after_the_proposal_was_created_is_not_overwritten(skill_file: Path, snapshot: AsyncMock) -> None:
    payload = _payload(skill_file, base_content_hash=skill_file_hash(skill_file))
    edited = _edited_by_the_user(skill_file)
    store = _store()

    with pytest.raises(EvolutionApplyError, match="changed after this proposal") as refused:
        await apply_content_update(payload, store)

    assert refused.value.code == REASON_STALE_BASE
    assert skill_file.read_text(encoding="utf-8") == edited
    assert list(skill_file.parent.iterdir()) == [skill_file]
    store.save_skill.assert_not_awaited()
    snapshot.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_skill_deleted_after_the_proposal_was_created_is_not_recreated(skill_file: Path) -> None:
    payload = _payload(skill_file, base_content_hash=skill_file_hash(skill_file))
    skill_file.unlink()

    with pytest.raises(EvolutionApplyError) as refused:
        await apply_content_update(payload, _store())

    assert refused.value.code == REASON_STALE_BASE
    assert not skill_file.exists()


@pytest.mark.asyncio
async def test_a_skill_that_still_matches_its_base_is_applied(skill_file: Path) -> None:
    payload = _payload(skill_file, base_content_hash=skill_file_hash(skill_file))

    await apply_content_update(payload, _store())

    assert skill_file.read_text(encoding="utf-8") == _EVOLVED


@pytest.mark.asyncio
async def test_a_base_that_only_changed_its_line_endings_is_not_stale(skill_file: Path) -> None:
    payload = _payload(skill_file, base_content_hash=skill_file_hash(skill_file))
    skill_file.write_bytes(_ORIGINAL.replace("\n", "\r\n").encode("utf-8"))

    await apply_content_update(payload, _store())

    assert skill_file.read_text(encoding="utf-8") == _EVOLVED


@pytest.mark.asyncio
async def test_applying_the_same_proposal_twice_is_not_stale(skill_file: Path) -> None:
    payload = _payload(skill_file, base_content_hash=skill_file_hash(skill_file))

    await apply_content_update(payload, _store())
    await apply_content_update(payload, _store())

    assert skill_file.read_text(encoding="utf-8") == _EVOLVED


@pytest.mark.asyncio
async def test_a_proposal_without_a_base_hash_is_applied_over_an_edited_skill(skill_file: Path) -> None:
    _edited_by_the_user(skill_file)

    await apply_content_update(_payload(skill_file), _store())

    assert skill_file.read_text(encoding="utf-8") == _EVOLVED


def test_the_hash_of_a_missing_or_undecodable_file_is_defined(tmp_path: Path) -> None:
    undecodable = tmp_path / "SKILL.md"
    undecodable.write_bytes(_UNDECODABLE)

    assert skill_file_hash(tmp_path / "missing" / "SKILL.md") is None
    assert skill_file_hash(undecodable) == skill_file_hash(undecodable)


def _forking_store() -> MagicMock:
    """A store whose skill belongs to another agent, so applying for a different agent forks it."""
    store = _store()
    store.get_skill.return_value = SkillRecord(
        skill_id="skill-1",
        name="demo-skill",
        description="Owned by another agent",
        content=_ORIGINAL,
        path="",
        lineage=SkillLineage(evolution_type=EvolutionType.FIX),
        environment=EnvironmentFingerprint(custom_tags={"scope_agent_id": "owner-agent"}),
    )
    return store


@pytest.fixture
def no_agent_bindings() -> Iterator[None]:
    """The fork rewrites the agent's skill bindings in the database; there is no agent in these tests."""

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncMock]:
        db = AsyncMock()
        db.get.return_value = None
        yield db

    with patch("app.database.connection.get_session", session):
        yield


@pytest.mark.asyncio
async def test_the_store_keeps_the_text_written_over_an_existing_scoped_skill(skill_file: Path) -> None:
    store = _forking_store()

    await apply_content_update(_payload(skill_file), store, agent_id="owner-agent")

    written = skill_file.read_text(encoding="utf-8")
    assert "scope_agent_id: owner-agent" in written
    saved: SkillRecord = store.save_skill.await_args.args[0]
    assert saved.content == written


@pytest.mark.asyncio
async def test_a_refused_fork_leaves_the_proposal_as_it_was_reviewed(skill_file: Path) -> None:
    payload = _payload(skill_file, evolved_content="not a skill")

    with pytest.raises(EvolutionApplyError):
        await apply_content_update(payload, _forking_store(), agent_id="other-agent")

    assert (payload.skill_id, payload.skill_name, payload.skill_path) == ("skill-1", "demo-skill", str(skill_file))
    assert payload.original_content == _ORIGINAL
    assert not (skill_file.parent.parent / "demo-skill-fork").exists()


@pytest.mark.asyncio
@pytest.mark.usefixtures("no_agent_bindings")
async def test_an_applied_fork_gives_the_payload_the_fork_identity(skill_file: Path) -> None:
    payload = _payload(skill_file, base_content_hash=skill_file_hash(skill_file))
    store = _forking_store()

    await apply_content_update(payload, store, agent_id="other-agent")

    fork_file = skill_file.parent.parent / "demo-skill-fork" / "SKILL.md"
    assert fork_file.is_file()
    assert skill_file.read_text(encoding="utf-8") == _ORIGINAL
    assert payload.skill_id.startswith("fork_")
    assert payload.skill_name == "demo-skill-fork"
    assert payload.skill_path == str(fork_file)
    assert payload.original_content == ""
    saved: SkillRecord = store.save_skill.await_args.args[0]
    assert (saved.skill_id, saved.name) == (payload.skill_id, payload.skill_name)
    assert saved.content == fork_file.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_a_fork_checks_the_skill_it_was_forked_from_for_changes(skill_file: Path) -> None:
    payload = _payload(skill_file, base_content_hash=skill_file_hash(skill_file))
    _edited_by_the_user(skill_file)

    with pytest.raises(EvolutionApplyError) as refused:
        await apply_content_update(payload, _forking_store(), agent_id="other-agent")

    assert refused.value.code == REASON_STALE_BASE
    assert payload.skill_id == "skill-1"
