"""Bundle files shipped next to a seed's SKILL.md reach storage byte for byte, text and binary alike."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend
from myrm_agent_harness.toolkits.storage.paths import get_skill_file_path
from myrm_agent_harness.toolkits.storage.types import SkillType

from app.core.skills import prebuilt_sync

SKILL_MD = "---\nname: bundle-probe\ndescription: Probe seed with bundled files\n---\n# bundle-probe\n"
PNG_BYTES = b"\x89PNG\r\n\x1a\n\x00\x01\x02\xff"


@pytest.fixture(autouse=True)
def _fresh_prebuilt_sync() -> Iterator[None]:
    prebuilt_sync._synced = False  # noqa: SLF001
    yield
    prebuilt_sync._synced = False  # noqa: SLF001


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
