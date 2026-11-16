"""A start whose seeds are those of the last complete sync reuses it; the reconciliation follows after the first screen.

[INPUT]
- app.core.skills.prebuilt_sync (POS: the seed synchronizer under test)
- app.core.skills.prebuilt_sync_state (POS: the record of the last complete sync)

[OUTPUT]
- Coverage that a reusing start returns the last sync's skill ids without parsing or writing anything, that every other
  start (first run, changed seeds, a missing stored copy, an unusable record, a failed listing) reconciles in full and
  records the seeds, that a call without the flag never touches the record, that the verification repairs what changed
  in storage since the last sync, and that the record is written only after a reconciliation completed

[POS]
Server tests for the boot fast path of the prebuilt skill sync: the first start after an install or an update must
leave storage exactly as before, and later starts must not spend the pre-listen time on a reconciliation that changes
nothing.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend

from app.core.skills import prebuilt_sync
from app.core.skills.prebuilt_sync import PrebuiltSyncResult
from app.core.skills.prebuilt_sync_state import seeds_fingerprint
from app.core.skills.store.reader import list_prebuilt_skills
from app.core.storage.paths import get_skill_file_path, get_skill_metadata_path
from app.core.storage.types import SkillType

SEED_NAMES = ("seed-a", "seed-b", "seed-c")
STATE_KEY = "skills/prebuilt/.seed-sync-state.json"
PARSE_TARGET = "app.core.skills.prebuilt_sync.parse_skill_frontmatter"


def _skill_md(name: str, release: str = "first release", env: str = "PROBE_KEY") -> str:
    return f"---\nname: {name}\ndescription: Probe seed {name}\nrequires:\n  env: [{env}]\n---\n# {name}\n{release}\n"


class _RecordingStorage(LocalStorageBackend):
    """Local storage that records every write and can be made to fail a listing or the write of one key."""

    def __init__(self, base_path: str) -> None:
        super().__init__(base_path)
        self.written: list[str] = []
        self.listing_error: Exception | None = None
        self.unwritable_key: str | None = None

    def _record(self, key: str) -> None:
        if key == self.unwritable_key:
            raise OSError(f"cannot write {key}")
        self.written.append(key)

    async def write(self, key: str, content: bytes, content_type: str | None = None) -> None:
        self._record(key)
        await super().write(key, content, content_type)

    async def write_text(self, key: str, content: str, encoding: str = "utf-8", content_type: str | None = None) -> None:
        self._record(key)
        await super().write_text(key, content, encoding, content_type)

    async def list(self, prefix: str = "", recursive: bool = True) -> list[str]:
        if self.listing_error is not None:
            raise self.listing_error
        return await super().list(prefix, recursive)


@pytest.fixture(autouse=True)
def _fresh_prebuilt_sync() -> Iterator[None]:
    prebuilt_sync._synced = False  # noqa: SLF001
    prebuilt_sync._reused_fingerprint = None  # noqa: SLF001
    yield
    prebuilt_sync._synced = False  # noqa: SLF001
    prebuilt_sync._reused_fingerprint = None  # noqa: SLF001


@pytest.fixture
def seeds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    seeds_dir = tmp_path / "seeds"
    for name in SEED_NAMES:
        (seeds_dir / name / "scripts").mkdir(parents=True)
        (seeds_dir / name / "SKILL.md").write_text(_skill_md(name), encoding="utf-8")
        (seeds_dir / name / "scripts" / "run.sh").write_text(f"echo {name}\n", encoding="utf-8")
    monkeypatch.setattr(prebuilt_sync, "SEEDS_DIR", seeds_dir)
    return seeds_dir


@pytest.fixture
def storage(tmp_path: Path) -> _RecordingStorage:
    return _RecordingStorage(str(tmp_path / "storage"))


async def _boot(storage: _RecordingStorage) -> PrebuiltSyncResult:
    """One start of a fresh process, asking for reuse as the lifespan does in local mode."""
    prebuilt_sync._synced = False  # noqa: SLF001
    prebuilt_sync._reused_fingerprint = None  # noqa: SLF001
    return await prebuilt_sync.sync_prebuilt_seeds(storage, reuse_unchanged=True)


async def _record(storage: _RecordingStorage) -> dict[str, object]:
    record: dict[str, object] = json.loads(await storage.read_text(STATE_KEY))
    return record


async def _snapshot(storage: _RecordingStorage, name: str) -> dict[str, object]:
    snapshot: dict[str, object] = json.loads(await storage.read_text(get_skill_metadata_path(SkillType.PREBUILT, name)))
    return snapshot


def _seed_key(name: str, filename: str) -> str:
    return get_skill_file_path(SkillType.PREBUILT, name, filename)


@pytest.mark.asyncio
async def test_first_start_reconciles_in_full_and_records_the_seeds(seeds: Path, storage: _RecordingStorage) -> None:
    with patch(PARSE_TARGET, wraps=prebuilt_sync.parse_skill_frontmatter) as parse:
        result = await _boot(storage)

    assert result == PrebuiltSyncResult(synced_count=len(SEED_NAMES), skill_ids=SEED_NAMES)
    assert parse.call_count == len(SEED_NAMES)
    record = await _record(storage)
    assert record["fingerprint"] == seeds_fingerprint(seeds)
    assert record["skill_ids"] == list(SEED_NAMES)
    assert prebuilt_sync._reused_fingerprint is None  # noqa: SLF001


@pytest.mark.asyncio
async def test_next_start_with_unchanged_seeds_reuses_the_last_sync(seeds: Path, storage: _RecordingStorage) -> None:
    first = await _boot(storage)
    storage.written.clear()

    with patch(PARSE_TARGET, side_effect=AssertionError("a reusing start must not parse a seed")):
        second = await _boot(storage)

    assert second == PrebuiltSyncResult(synced_count=0, skill_ids=first.skill_ids)
    assert storage.written == []
    assert prebuilt_sync._reused_fingerprint is not None  # noqa: SLF001


@pytest.mark.asyncio
async def test_a_call_without_the_flag_never_reads_or_writes_the_record(seeds: Path, storage: _RecordingStorage) -> None:
    await prebuilt_sync.sync_prebuilt_seeds(storage)
    assert not await storage.exists(STATE_KEY)

    await _boot(storage)
    prebuilt_sync._synced = False  # noqa: SLF001
    with patch(PARSE_TARGET, wraps=prebuilt_sync.parse_skill_frontmatter) as parse:
        await prebuilt_sync.sync_prebuilt_seeds(storage)

    assert parse.call_count == len(SEED_NAMES)
    assert prebuilt_sync._reused_fingerprint is None  # noqa: SLF001


async def _change_a_seed_skill_md(seeds: Path, _storage: _RecordingStorage) -> None:
    (seeds / "seed-a" / "SKILL.md").write_text(_skill_md("seed-a", "second release"), encoding="utf-8")


async def _change_a_seed_bundle_file(seeds: Path, _storage: _RecordingStorage) -> None:
    (seeds / "seed-b" / "scripts" / "run.sh").write_text("echo changed\n", encoding="utf-8")


async def _add_a_seed_bundle_file(seeds: Path, _storage: _RecordingStorage) -> None:
    (seeds / "seed-b" / "scripts" / "extra.sh").write_text("echo extra\n", encoding="utf-8")


async def _remove_a_seed_bundle_file(seeds: Path, _storage: _RecordingStorage) -> None:
    (seeds / "seed-b" / "scripts" / "run.sh").unlink()


async def _add_a_seed(seeds: Path, _storage: _RecordingStorage) -> None:
    (seeds / "seed-d").mkdir()
    (seeds / "seed-d" / "SKILL.md").write_text(_skill_md("seed-d"), encoding="utf-8")


async def _remove_a_seed(seeds: Path, _storage: _RecordingStorage) -> None:
    (seeds / "seed-c" / "scripts" / "run.sh").unlink()
    (seeds / "seed-c" / "scripts").rmdir()
    (seeds / "seed-c" / "SKILL.md").unlink()
    (seeds / "seed-c").rmdir()


async def _lose_a_stored_skill_md(_seeds: Path, storage: _RecordingStorage) -> None:
    await storage.delete(_seed_key("seed-b", "SKILL.md"))


async def _lose_a_stored_snapshot(_seeds: Path, storage: _RecordingStorage) -> None:
    await storage.delete(get_skill_metadata_path(SkillType.PREBUILT, "seed-b"))


async def _lose_a_stored_skill(_seeds: Path, storage: _RecordingStorage) -> None:
    await storage.delete("skills/prebuilt/seed-c")


async def _garble_the_record(_seeds: Path, storage: _RecordingStorage) -> None:
    await storage.write_text(STATE_KEY, "{not json")


async def _non_text_record(_seeds: Path, storage: _RecordingStorage) -> None:
    await storage.write(STATE_KEY, b"\xff\xfe\x00")


async def _record_of_another_format(_seeds: Path, storage: _RecordingStorage) -> None:
    await storage.write_text(STATE_KEY, json.dumps({**await _record(storage), "format": 0}))


async def _record_of_other_seeds(_seeds: Path, storage: _RecordingStorage) -> None:
    await storage.write_text(STATE_KEY, json.dumps({**await _record(storage), "fingerprint": "0" * 64}))


async def _record_without_skills(_seeds: Path, storage: _RecordingStorage) -> None:
    await storage.write_text(STATE_KEY, json.dumps({**await _record(storage), "skill_ids": []}))


async def _record_with_a_foreign_skill(_seeds: Path, storage: _RecordingStorage) -> None:
    record = await _record(storage)
    skill_ids = record["skill_ids"]
    assert isinstance(skill_ids, list)
    await storage.write_text(STATE_KEY, json.dumps({**record, "skill_ids": [*skill_ids, "never-synced"]}))


async def _record_that_is_not_an_object(_seeds: Path, storage: _RecordingStorage) -> None:
    await storage.write_text(STATE_KEY, json.dumps(["seed-a"]))


FALLBACKS: dict[str, Callable[[Path, _RecordingStorage], Awaitable[None]]] = {
    "seed SKILL.md changed": _change_a_seed_skill_md,
    "seed bundle file changed": _change_a_seed_bundle_file,
    "seed bundle file added": _add_a_seed_bundle_file,
    "seed bundle file removed": _remove_a_seed_bundle_file,
    "seed added": _add_a_seed,
    "seed removed": _remove_a_seed,
    "stored SKILL.md lost": _lose_a_stored_skill_md,
    "stored snapshot lost": _lose_a_stored_snapshot,
    "stored skill lost": _lose_a_stored_skill,
    "record unreadable": _garble_the_record,
    "record not text": _non_text_record,
    "record of another format": _record_of_another_format,
    "record of other seeds": _record_of_other_seeds,
    "record without skills": _record_without_skills,
    "record naming a skill that was never stored": _record_with_a_foreign_skill,
    "record that is not an object": _record_that_is_not_an_object,
}


@pytest.mark.asyncio
@pytest.mark.parametrize("tamper", FALLBACKS.values(), ids=FALLBACKS.keys())
async def test_every_other_start_reconciles_in_full_and_records_the_seeds(
    tamper: Callable[[Path, _RecordingStorage], Awaitable[None]], seeds: Path, storage: _RecordingStorage
) -> None:
    await _boot(storage)
    await tamper(seeds, storage)

    with patch(PARSE_TARGET, wraps=prebuilt_sync.parse_skill_frontmatter) as parse:
        result = await _boot(storage)

    # Every seed is parsed (a changed seed's unmodified stored copy is parsed once more for its requirements).
    assert parse.call_count >= len(result.skill_ids)
    assert prebuilt_sync._reused_fingerprint is None  # noqa: SLF001
    for name in result.skill_ids:
        assert await storage.exists(_seed_key(name, "SKILL.md")), name
        assert await storage.exists(get_skill_metadata_path(SkillType.PREBUILT, name)), name
    record = await _record(storage)
    assert record["fingerprint"] == seeds_fingerprint(seeds)
    assert record["skill_ids"] == list(result.skill_ids)


@pytest.mark.asyncio
async def test_a_failed_listing_reconciles_in_full(
    seeds: Path, storage: _RecordingStorage, caplog: pytest.LogCaptureFixture
) -> None:
    await _boot(storage)
    storage.listing_error = OSError("disk unavailable")

    with patch(PARSE_TARGET, wraps=prebuilt_sync.parse_skill_frontmatter) as parse, caplog.at_level("WARNING"):
        result = await _boot(storage)

    assert parse.call_count == len(SEED_NAMES)
    assert result.skill_ids == SEED_NAMES
    assert prebuilt_sync._reused_fingerprint is None  # noqa: SLF001
    assert "Failed to list prebuilt skills, reconciling in full" in caplog.text


@pytest.mark.asyncio
async def test_a_changed_seed_is_updated_before_the_start_returns(seeds: Path, storage: _RecordingStorage) -> None:
    await _boot(storage)
    await _change_a_seed_skill_md(seeds, storage)

    result = await _boot(storage)

    assert result.synced_count == 1
    assert "second release" in await storage.read_text(_seed_key("seed-a", "SKILL.md"))


@pytest.mark.asyncio
async def test_verification_repairs_what_changed_in_storage_since_the_last_sync(seeds: Path, storage: _RecordingStorage) -> None:
    await _boot(storage)
    bundle_key = _seed_key("seed-a", "scripts/run.sh")
    await storage.delete(bundle_key)
    # A SKILL.md edited through the files API: its snapshot is refreshed at the next reconciliation.
    skill_md_key = _seed_key("seed-b", "SKILL.md")
    edited = (await storage.read_text(skill_md_key)).replace("PROBE_KEY", "EDITED_KEY")
    await storage.write_text(skill_md_key, edited)
    stale_snapshot = await _snapshot(storage, "seed-b")

    reused = await _boot(storage)

    assert reused.synced_count == 0
    assert not await storage.exists(bundle_key)
    assert await _snapshot(storage, "seed-b") == stale_snapshot

    verified = await prebuilt_sync.verify_reused_sync(storage)

    assert verified is not None
    assert verified.skill_ids == reused.skill_ids
    assert await storage.read_text(bundle_key) == "echo seed-a\n"
    assert (await _snapshot(storage, "seed-b"))["requires"] == {"bins": [], "env": ["EDITED_KEY"], "config": []}
    assert await storage.read_text(skill_md_key) == edited
    assert prebuilt_sync._reused_fingerprint is None  # noqa: SLF001
    assert await prebuilt_sync.verify_reused_sync(storage) is None


@pytest.mark.asyncio
async def test_verification_removes_a_stale_entry_left_in_storage(seeds: Path, storage: _RecordingStorage) -> None:
    await _boot(storage)
    stale_md = _seed_key("removed-seed", "SKILL.md")
    stale_snapshot = get_skill_metadata_path(SkillType.PREBUILT, "removed-seed")
    await storage.write_text(stale_md, _skill_md("removed-seed"))
    await storage.write_text(stale_snapshot, "{}")

    await _boot(storage)
    assert await storage.exists(stale_snapshot)

    await prebuilt_sync.verify_reused_sync(storage)

    assert not await storage.exists(stale_snapshot)
    assert not await storage.exists(stale_md)


@pytest.mark.asyncio
async def test_verification_does_nothing_when_the_start_reconciled_in_full(seeds: Path, storage: _RecordingStorage) -> None:
    await _boot(storage)
    storage.written.clear()

    with patch(PARSE_TARGET, side_effect=AssertionError("nothing was reused, so nothing is left to reconcile")):
        assert await prebuilt_sync.verify_reused_sync(storage) is None

    assert storage.written == []


@pytest.mark.asyncio
async def test_the_record_is_written_only_after_the_reconciliation_completed(seeds: Path, storage: _RecordingStorage) -> None:
    parsed: list[str] = []
    real_parse = prebuilt_sync.parse_skill_frontmatter

    def parse_then_fail_on_the_second_seed(content: str, name: str) -> object:
        parsed.append(name)
        if len(parsed) == 2:
            raise RuntimeError("storage went away")
        return real_parse(content, name)

    with patch(PARSE_TARGET, side_effect=parse_then_fail_on_the_second_seed), pytest.raises(RuntimeError):
        await _boot(storage)

    assert not await storage.exists(STATE_KEY)


@pytest.mark.asyncio
async def test_a_failed_verification_leaves_the_record_as_it_was(seeds: Path, storage: _RecordingStorage) -> None:
    await _boot(storage)
    recorded = await storage.read_text(STATE_KEY)
    await _boot(storage)

    with patch(PARSE_TARGET, side_effect=RuntimeError("storage went away")), pytest.raises(RuntimeError):
        await prebuilt_sync.verify_reused_sync(storage)

    assert await storage.read_text(STATE_KEY) == recorded
    assert prebuilt_sync._reused_fingerprint is None  # noqa: SLF001


@pytest.mark.asyncio
async def test_a_record_that_cannot_be_written_does_not_fail_the_start(
    seeds: Path, storage: _RecordingStorage, caplog: pytest.LogCaptureFixture
) -> None:
    storage.unwritable_key = STATE_KEY

    with caplog.at_level("WARNING"):
        result = await _boot(storage)

    assert result.skill_ids == SEED_NAMES
    assert "Failed to record the prebuilt skill sync state" in caplog.text
    assert not await storage.exists(STATE_KEY)
    # With no record the next start reconciles in full again.
    with patch(PARSE_TARGET, wraps=prebuilt_sync.parse_skill_frontmatter) as parse:
        await _boot(storage)
    assert parse.call_count == len(SEED_NAMES)


@pytest.mark.asyncio
async def test_the_record_is_not_rewritten_while_it_is_current(seeds: Path, storage: _RecordingStorage) -> None:
    await _boot(storage)
    await _boot(storage)
    storage.written.clear()

    await prebuilt_sync.verify_reused_sync(storage)

    assert STATE_KEY not in storage.written


@pytest.mark.asyncio
async def test_the_record_does_not_appear_as_a_skill(seeds: Path, storage: _RecordingStorage) -> None:
    await _boot(storage)

    assert sorted(skill.id for skill in await list_prebuilt_skills(storage)) == list(SEED_NAMES)
