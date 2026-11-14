"""Bundle files shipped next to a seed's SKILL.md reach storage byte for byte, text and binary alike.

The shipped seeds carry scripts and references of their own, and those reach storage too.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend

from app.core.skills import prebuilt_sync
from app.core.storage.paths import get_skill_file_path
from app.core.storage.types import SkillType

SKILL_MD = "---\nname: bundle-probe\ndescription: Probe seed with bundled files\n---\n# bundle-probe\n"
PNG_BYTES = b"\x89PNG\r\n\x1a\n\x00\x01\x02\xff"


@pytest.fixture(autouse=True)
def _fresh_prebuilt_sync() -> Iterator[None]:
    prebuilt_sync._synced = False  # noqa: SLF001
    yield
    prebuilt_sync._synced = False  # noqa: SLF001


@pytest.fixture
def storage(tmp_path: Path) -> LocalStorageBackend:
    return LocalStorageBackend(str(tmp_path))


@pytest.mark.asyncio
async def test_sync_stores_text_and_binary_bundle_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seed = tmp_path / "seeds" / "bundle-probe"
    (seed / "scripts").mkdir(parents=True)
    (seed / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")
    (seed / "scripts" / "run.sh").write_text("echo ok\n", encoding="utf-8")
    (seed / "logo.png").write_bytes(PNG_BYTES)
    monkeypatch.setattr(prebuilt_sync, "SEEDS_DIR", tmp_path / "seeds")
    storage = LocalStorageBackend(str(tmp_path / "storage"))

    await prebuilt_sync.sync_prebuilt_seeds(storage)

    assert await storage.read_text(get_skill_file_path(SkillType.PREBUILT, "bundle-probe", "scripts/run.sh")) == "echo ok\n"
    assert await storage.read(get_skill_file_path(SkillType.PREBUILT, "bundle-probe", "logo.png")) == PNG_BYTES


@pytest.mark.asyncio
async def test_sync_copies_skill_bundle_scripts(storage: LocalStorageBackend) -> None:
    """Bundled seed files (e.g. google-workspace/scripts/google_api.py) must sync to storage."""
    result = await prebuilt_sync.sync_prebuilt_seeds(storage)
    assert "google-workspace" in result.skill_ids

    script_storage_path = get_skill_file_path(SkillType.PREBUILT, "google-workspace", "scripts/google_api.py")
    stored = await storage.read_text(script_storage_path)

    seed_script = (
        Path(prebuilt_sync.__file__).resolve().parents[3]
        / "assets"
        / "prebuilt_skills"
        / "google-workspace"
        / "scripts"
        / "google_api.py"
    )
    assert stored == seed_script.read_text(encoding="utf-8")
    assert "calendar-today" in stored

    # google_api.py imports this sibling module, so a skill copy without it cannot run.
    sibling_path = get_skill_file_path(SkillType.PREBUILT, "google-workspace", "scripts/calendar_overlaps.py")
    assert "def find_conflicts" in await storage.read_text(sibling_path)


@pytest.mark.asyncio
async def test_sync_copies_references_directory(storage: LocalStorageBackend) -> None:
    """Skills with references/ subdirectory should have all .md files synced."""
    result = await prebuilt_sync.sync_prebuilt_seeds(storage)
    assert "unreal-mcp" in result.skill_ids

    ref_path = get_skill_file_path(SkillType.PREBUILT, "unreal-mcp", "references/tool-surface.md")
    stored = await storage.read_text(ref_path)
    assert "ProgrammaticToolset" in stored or "toolset" in stored.lower()


@pytest.mark.asyncio
async def test_sync_copies_blender_references(storage: LocalStorageBackend) -> None:
    """Blender skill references should be synced."""
    result = await prebuilt_sync.sync_prebuilt_seeds(storage)
    assert "blender-mcp" in result.skill_ids

    ref_path = get_skill_file_path(SkillType.PREBUILT, "blender-mcp", "references/bpy-patterns.md")
    stored = await storage.read_text(ref_path)
    assert "bpy" in stored
