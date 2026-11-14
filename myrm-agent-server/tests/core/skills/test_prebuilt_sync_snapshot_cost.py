"""A seed's snapshot, and the tokens counted for it, are rebuilt only when the seed is installed or changes.

Counting tokens for every bundled SKILL.md on every start delays the server's first listen, so the
sync skips it for seeds that already match their stored copy.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend

from app.core.skills import prebuilt_sync
from app.core.storage.paths import get_skill_metadata_path
from app.core.storage.types import SkillType

SEED_NAMES = ("seed-a", "seed-b")
COUNT_TARGET = "app.core.skills.prebuilt_sync.get_token_count"


def _skill_md(name: str, release: str) -> str:
    return f"---\nname: {name}\ndescription: Probe seed {name}\ntags: [probe, {name}]\n---\n# {name}\n{release}\n"


@pytest.fixture(autouse=True)
def _fresh_prebuilt_sync() -> Iterator[None]:
    prebuilt_sync._synced = False  # noqa: SLF001
    yield
    prebuilt_sync._synced = False  # noqa: SLF001


@pytest.fixture
def seeds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    seeds_dir = tmp_path / "seeds"
    for name in SEED_NAMES:
        (seeds_dir / name).mkdir(parents=True)
        (seeds_dir / name / "SKILL.md").write_text(_skill_md(name, "first release"), encoding="utf-8")
    monkeypatch.setattr(prebuilt_sync, "SEEDS_DIR", seeds_dir)
    return seeds_dir


@pytest.fixture
def storage(tmp_path: Path) -> LocalStorageBackend:
    return LocalStorageBackend(str(tmp_path / "storage"))


async def _snapshot(storage: LocalStorageBackend, name: str) -> dict[str, object]:
    snapshot: dict[str, object] = json.loads(await storage.read_text(get_skill_metadata_path(SkillType.PREBUILT, name)))
    return snapshot


@pytest.mark.asyncio
async def test_first_start_counts_tokens_for_every_seed(seeds: Path, storage: LocalStorageBackend) -> None:
    with patch(COUNT_TARGET, return_value=7) as count:
        result = await prebuilt_sync.sync_prebuilt_seeds(storage)

    assert result.synced_count == len(SEED_NAMES)
    assert count.call_count == len(SEED_NAMES)
    for name in SEED_NAMES:
        snapshot = await _snapshot(storage, name)
        assert snapshot["token_cost"] == 7
        assert snapshot["tags"] == ["probe", name]


@pytest.mark.asyncio
async def test_later_start_with_unchanged_seeds_counts_no_tokens(seeds: Path, storage: LocalStorageBackend) -> None:
    await prebuilt_sync.sync_prebuilt_seeds(storage)
    prebuilt_sync._synced = False  # noqa: SLF001

    with patch(COUNT_TARGET) as count:
        result = await prebuilt_sync.sync_prebuilt_seeds(storage)

    assert result.synced_count == 0
    count.assert_not_called()


@pytest.mark.asyncio
async def test_changed_seed_is_the_only_one_counted_again(seeds: Path, storage: LocalStorageBackend) -> None:
    with patch(COUNT_TARGET, return_value=7):
        await prebuilt_sync.sync_prebuilt_seeds(storage)
    prebuilt_sync._synced = False  # noqa: SLF001
    changed = _skill_md("seed-a", "second release")
    (seeds / "seed-a" / "SKILL.md").write_text(changed, encoding="utf-8")

    with patch(COUNT_TARGET, return_value=9) as count:
        result = await prebuilt_sync.sync_prebuilt_seeds(storage)

    assert result.synced_count == 1
    count.assert_called_once_with(changed)
    assert (await _snapshot(storage, "seed-a"))["token_cost"] == 9
    assert (await _snapshot(storage, "seed-b"))["token_cost"] == 7
