"""User operations: connect, library choice, sync control, retry and scoped compile."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import pytest
from langchain_core.language_models import BaseChatModel
from myrm_agent_harness.toolkits.wiki import WikiStructure
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.services.wiki.agent_scope import DEFAULT_AGENT_SCOPE
from app.services.wiki.source_sync.ima import operations
from app.services.wiki.source_sync.ima.errors import ImaAuthError
from app.services.wiki.source_sync.ima.ledger import ImaLedger, InventoryItem
from app.services.wiki.source_sync.ima.models import ImaCredentials
from app.services.wiki.source_sync.ima.operations import ImaOperationError
from app.services.wiki.source_sync.ima.schemas import ImaLibrary
from app.services.wiki.source_sync.ima.state import (
    ImaKbSelection,
    ImaSyncConfig,
    ImaSyncState,
    load_ima_config,
    load_ima_state,
    save_ima_config,
    save_ima_state,
)

CREDENTIALS = ImaCredentials(client_id="cid", api_key="key")
# The model is only handed to the (faked) archiver factory, never invoked.
LLM = cast(BaseChatModel, object())


@dataclass
class Recorder:
    saved: list[ImaCredentials] = field(default_factory=list)
    triggered: list[str | None] = field(default_factory=list)
    started: list[tuple[str | None, str]] = field(default_factory=list)
    verified: list[ImaCredentials] = field(default_factory=list)
    reject: bool = False
    stored: ImaCredentials | None = CREDENTIALS
    cleared: bool = False
    stopped: bool = False
    paused_exists: bool = True


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    rec = Recorder()

    async def verify(credentials: ImaCredentials) -> None:
        rec.verified.append(credentials)
        if rec.reject:
            raise ImaAuthError("rejected")

    async def load() -> ImaCredentials | None:
        return rec.stored

    async def save(credentials: ImaCredentials) -> None:
        rec.saved.append(credentials)
        rec.stored = credentials

    async def clear() -> bool:
        rec.cleared = True
        rec.stored = None
        return True

    async def stop_all() -> int:
        rec.stopped = True
        return 1

    async def trigger(agent_id: str | None) -> None:
        rec.triggered.append(agent_id)

    async def start(agent_id: str | None, *, locale: str) -> None:
        rec.started.append((agent_id, locale))

    async def pause(agent_id: str | None) -> bool:
        return rec.paused_exists

    monkeypatch.setattr(operations, "_verify", verify)
    monkeypatch.setattr(operations, "load_credentials", load)
    monkeypatch.setattr(operations, "save_credentials", save)
    monkeypatch.setattr(operations, "clear_credentials", clear)
    monkeypatch.setattr(operations, "stop_all_jobs", stop_all)
    monkeypatch.setattr(operations, "trigger_if_active", trigger)
    monkeypatch.setattr(operations, "start_job", start)
    monkeypatch.setattr(operations, "pause_job", pause)
    monkeypatch.setattr(operations, "resume_job", pause)
    return rec


async def test_connect_validates_before_storing_and_trims_input(
    recorder: Recorder, ima_db: async_sessionmaker[AsyncSession]
) -> None:
    recorder.stored = None
    await operations.connect(client_id="  cid ", api_key=" key\n", agent_id=None)

    assert recorder.verified == [CREDENTIALS] and recorder.saved == [CREDENTIALS]
    assert recorder.triggered == [None]


async def test_rejected_credentials_are_never_stored(recorder: Recorder, ima_db: async_sessionmaker[AsyncSession]) -> None:
    recorder.reject, recorder.stored = True, None

    with pytest.raises(ImaAuthError):
        await operations.connect(client_id="cid", api_key="bad", agent_id=None)

    assert recorder.saved == [] and recorder.stored is None


@pytest.mark.parametrize(("client_id", "api_key"), [("", "key"), ("cid", "  ")])
async def test_blank_credentials_fail_before_any_network_call(recorder: Recorder, client_id: str, api_key: str) -> None:
    with pytest.raises(ImaOperationError) as caught:
        await operations.connect(client_id=client_id, api_key=api_key, agent_id=None)
    assert caught.value.code == "ima_credentials_missing" and recorder.verified == []


async def test_reconnecting_clears_the_reauth_flag_of_the_agent(
    recorder: Recorder, ima_db: async_sessionmaker[AsyncSession]
) -> None:
    async with ima_db() as db:
        await save_ima_state(db, ImaSyncState(needs_reauth=True, last_error_kind="auth"), agent_id=None)

    await operations.connect(client_id="cid", api_key="key", agent_id=None)

    async with ima_db() as db:
        state = await load_ima_state(db, agent_id=None)
    assert state.needs_reauth is False and state.last_error_kind == ""


async def test_disconnect_removes_credentials_and_every_job(recorder: Recorder) -> None:
    await operations.disconnect()
    assert recorder.cleared and recorder.stopped


async def test_operations_require_a_connection(recorder: Recorder) -> None:
    recorder.stored = None
    with pytest.raises(ImaOperationError) as caught:
        await operations.list_libraries()
    assert caught.value.code == "ima_not_connected"


async def test_selection_takes_names_from_ima_drops_unknown_ids_and_dedupes(
    recorder: Recorder, ima_db: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def libraries() -> list[ImaLibrary]:
        return [ImaLibrary(id="a", name="Alpha"), ImaLibrary(id="b", name="Beta")]

    monkeypatch.setattr(operations, "list_libraries", libraries)

    saved = await operations.save_selection(library_ids=["b", "zzz", "b", "a"], include_notes=False, agent_id=None)

    assert saved == ImaSyncConfig(
        knowledge_bases=[ImaKbSelection(id="b", name="Beta"), ImaKbSelection(id="a", name="Alpha")], include_notes=False
    )
    async with ima_db() as db:
        assert await load_ima_config(db, agent_id=None) == saved


async def test_selection_is_capped(
    recorder: Recorder, ima_db: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    everything = [ImaLibrary(id=f"kb{index}", name=f"Library {index}") for index in range(80)]

    async def libraries() -> list[ImaLibrary]:
        return everything

    monkeypatch.setattr(operations, "list_libraries", libraries)

    saved = await operations.save_selection(library_ids=[library.id for library in everything], include_notes=True, agent_id=None)
    assert len(saved.knowledge_bases) == 50


async def test_start_requires_credentials_and_something_to_import(
    recorder: Recorder, ima_db: async_sessionmaker[AsyncSession]
) -> None:
    recorder.stored = None
    with pytest.raises(ImaOperationError) as caught:
        await operations.start_sync(agent_id=None, locale="en")
    assert caught.value.code == "ima_not_connected"

    recorder.stored = CREDENTIALS
    async with ima_db() as db:
        await save_ima_config(db, ImaSyncConfig(knowledge_bases=[], include_notes=False), agent_id=None)
    with pytest.raises(ImaOperationError) as caught:
        await operations.start_sync(agent_id=None, locale="en")
    assert caught.value.code == "ima_no_selection"
    assert recorder.started == []

    async with ima_db() as db:
        await save_ima_config(db, ImaSyncConfig(knowledge_bases=[], include_notes=True), agent_id=None)
    await operations.start_sync(agent_id="agent-1", locale="zh")
    assert recorder.started == [("agent-1", "zh")]


async def test_pause_and_resume_fail_clearly_when_sync_was_never_started(recorder: Recorder) -> None:
    recorder.paused_exists = False
    for call in (operations.pause_sync(agent_id=None), operations.resume_sync(agent_id=None)):
        with pytest.raises(ImaOperationError) as caught:
            await call
        assert caught.value.code == "ima_sync_not_started"


def inventory_item(key: str) -> InventoryItem:
    return InventoryItem(
        item_key=key,
        container_id="kb1",
        container_name="Lib",
        remote_id=key,
        title=key,
        folder_path="",
        media_type=7,
        remote_version="v1",
    )


async def test_retry_failed_triggers_the_job_only_when_something_was_reset(
    recorder: Recorder, ima_db: async_sessionmaker[AsyncSession]
) -> None:
    assert await operations.retry_failed(agent_id=None) == 0
    assert recorder.triggered == []

    ledger = ImaLedger(DEFAULT_AGENT_SCOPE)
    async with ima_db() as db:
        await ledger.upsert_inventory(db, [inventory_item("a")], generation=1, raw_exists=lambda _path: True)
        await db.commit()
    async with ima_db() as db:
        row = (await ledger.list_rows(db))[0]
        await ledger.record_failure(db, row, kind="permanent", final=True)
        await db.commit()

    assert await operations.retry_failed(agent_id=None) == 1
    assert recorder.triggered == [None]


@dataclass
class FakeQueue:
    added: list[Path] = field(default_factory=list)
    processing: list[str] = field(default_factory=list)

    def add_batch(self, paths: list[Path]) -> None:
        self.added.extend(paths)

    def list_processing_file_paths(self) -> list[str]:
        return self.processing


@dataclass
class FakeCompiler:
    started: int = 0

    def start_background_worker(self) -> None:
        self.started += 1


class FakeArchiver:
    def __init__(self, root: Path) -> None:
        self._structure = WikiStructure(base_dir=root)
        self._queue = FakeQueue()
        self._compiler = FakeCompiler()


@pytest.fixture
def archiver(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FakeArchiver:
    fake = FakeArchiver(tmp_path)
    monkeypatch.setattr(operations, "get_wiki_archiver", lambda llm, agent_id=None: fake)
    monkeypatch.setattr("app.services.wiki.dedup_runner.wiki_dedup_blocks_compile", lambda *, agent_id=None: False)
    return fake


async def _synced(
    ima_db: async_sessionmaker[AsyncSession], archiver: FakeArchiver, names: list[str], *, write: bool = True
) -> None:
    ledger = ImaLedger(DEFAULT_AGENT_SCOPE)
    async with ima_db() as db:
        await ledger.upsert_inventory(db, [inventory_item(name) for name in names], generation=1, raw_exists=lambda _path: True)
        await db.commit()
    async with ima_db() as db:
        rows = await ledger.list_rows(db)
    async with ima_db() as db:
        for row in rows:
            relative = f"ima/Lib/{row.title}.md"
            if write:
                target = archiver._structure.get_raw_file_path(relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("body", encoding="utf-8")
            await ledger.record_synced(db, row, raw_path=relative, fidelity="full", notes=[], char_count=4)
        await db.commit()


async def test_compile_queues_only_imported_documents_and_wakes_the_worker(
    archiver: FakeArchiver, ima_db: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    other = archiver._structure.get_raw_file_path("notes/unrelated.md")
    other.parent.mkdir(parents=True, exist_ok=True)
    other.write_text("not from ima", encoding="utf-8")
    await _synced(ima_db, archiver, ["a", "b"])

    queued = await operations.compile_imported(llm=LLM, agent_id=None)

    assert queued == 2
    assert sorted(path.name for path in archiver._queue.added) == ["a.md", "b.md"]
    assert archiver._compiler.started == 1


async def test_compile_skips_documents_the_compiler_is_working_on_now(
    archiver: FakeArchiver, ima_db: async_sessionmaker[AsyncSession]
) -> None:
    await _synced(ima_db, archiver, ["a", "b"])
    archiver._queue.processing = [str(archiver._structure.get_raw_file_path("ima/Lib/a.md"))]

    assert await operations.compile_imported(llm=LLM, agent_id=None) == 1


async def test_compile_does_nothing_when_no_imported_file_exists(
    archiver: FakeArchiver, ima_db: async_sessionmaker[AsyncSession]
) -> None:
    await _synced(ima_db, archiver, ["a"], write=False)

    assert await operations.compile_imported(llm=LLM, agent_id=None) == 0
    assert archiver._queue.added == [] and archiver._compiler.started == 0


async def test_compile_waits_for_duplicate_review(
    archiver: FakeArchiver, ima_db: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.services.wiki.dedup_runner.wiki_dedup_blocks_compile", lambda *, agent_id=None: True)

    with pytest.raises(ImaOperationError) as caught:
        await operations.compile_imported(llm=LLM, agent_id=None)
    assert caught.value.code == "dedup_review_required"
