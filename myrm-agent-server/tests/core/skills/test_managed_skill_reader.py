"""ManagedSkillSnapshotReader reads from the root the creation service writes into."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.skills.creation.managed_skill_reader import ManagedSkillSnapshotReader
from app.core.skills.creation.service import SkillCreationService

SKILL_MD = "---\nname: demo\ndescription: demo\n---\n# Demo\nbody\n"


def _install(root: Path, name: str = "demo") -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")
    return skill_dir


@pytest.fixture
def service(tmp_path: Path) -> SkillCreationService:
    return SkillCreationService(base_path=tmp_path)


@pytest.fixture
def reader(service: SkillCreationService) -> ManagedSkillSnapshotReader:
    return ManagedSkillSnapshotReader(service)


async def test_reads_skill_md_from_the_service_root(reader: ManagedSkillSnapshotReader, tmp_path: Path) -> None:
    _install(tmp_path)

    assert await reader.get_skill_content("demo") == SKILL_MD


async def test_a_skill_missing_from_the_root_raises_like_a_missing_skill(reader: ManagedSkillSnapshotReader) -> None:
    with pytest.raises(FileNotFoundError):
        await reader.get_skill_content("never-saved")


async def test_reads_a_resource_as_raw_bytes(reader: ManagedSkillSnapshotReader, tmp_path: Path) -> None:
    skill_dir = _install(tmp_path)
    (skill_dir / "assets").mkdir()
    (skill_dir / "assets" / "logo.bin").write_bytes(b"\x00\xff\x10")

    assert await reader.get_skill_resources("demo", "assets/logo.bin") == b"\x00\xff\x10"


async def test_a_missing_resource_raises(reader: ManagedSkillSnapshotReader, tmp_path: Path) -> None:
    _install(tmp_path)

    with pytest.raises(FileNotFoundError):
        await reader.get_skill_resources("demo", "references/absent.md")


async def test_the_root_is_read_on_every_call(
    reader: ManagedSkillSnapshotReader, service: SkillCreationService, tmp_path: Path
) -> None:
    moved_root = tmp_path / "moved"
    _install(moved_root)
    service.base_path = moved_root

    assert await reader.get_skill_content("demo") == SKILL_MD


@pytest.mark.parametrize("hostile_name", ["../outside", "/etc", "demo/../../outside"])
async def test_a_skill_name_leaving_the_root_is_rejected(reader: ManagedSkillSnapshotReader, hostile_name: str) -> None:
    with pytest.raises(ValueError):
        await reader.get_skill_content(hostile_name)


@pytest.mark.parametrize("hostile_path", ["../SKILL.md", "/etc/passwd", "references/../../other/SKILL.md"])
async def test_a_resource_path_leaving_the_skill_is_rejected(
    reader: ManagedSkillSnapshotReader, tmp_path: Path, hostile_path: str
) -> None:
    _install(tmp_path)

    with pytest.raises(ValueError):
        await reader.get_skill_resources("demo", hostile_path)
