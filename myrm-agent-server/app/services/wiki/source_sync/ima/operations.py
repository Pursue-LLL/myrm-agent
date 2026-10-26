"""User-driven ima operations: connect, choose libraries, control the sync, compile what was imported.

[INPUT]
- .client / .transport / .credentials (POS: ima access and encrypted credentials)
- .state / .ledger (POS: selection, resumable state, per-item ledger)
- .job (POS: cron lifecycle of the sync job)

[OUTPUT]
- ImaOperationError, connect, disconnect, list_libraries, save_selection
- start_sync, pause_sync, resume_sync, retry_failed, compile_imported

[POS]
Everything the settings card can ask for besides reading status. Each call validates its precondition and
raises ``ImaOperationError`` with a stable code, so the API layer maps outcomes without parsing messages.
"""

from __future__ import annotations

from pathlib import Path

from langchain_core.language_models import BaseChatModel

from app.database.connection import get_session
from app.services.wiki.agent_scope import normalize_agent_scope
from app.services.wiki.vault import get_wiki_archiver

from .client import ImaClient
from .credentials import clear_credentials, load_credentials, save_credentials
from .job import pause_job, resume_job, start_job, stop_all_jobs, trigger_if_active
from .ledger import ImaLedger
from .models import ImaCredentials
from .schemas import ImaLibrary
from .state import ImaKbSelection, ImaSyncConfig, load_ima_config, load_ima_state, save_ima_config, save_ima_state
from .transport import ImaTransport

_MAX_SELECTED_LIBRARIES = 50


class ImaOperationError(Exception):
    """A precondition of the requested operation does not hold."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


async def _require_credentials() -> ImaCredentials:
    credentials = await load_credentials()
    if credentials is None:
        raise ImaOperationError("ima_not_connected", "ima is not connected")
    return credentials


async def _verify(credentials: ImaCredentials) -> None:
    async with ImaTransport(credentials) as transport:
        await ImaClient(transport).verify()


async def connect(*, client_id: str, api_key: str, agent_id: str | None) -> None:
    """Validate against ima first, so a wrong key is never stored; re-connecting resumes a sync waiting on credentials."""
    credentials = ImaCredentials(client_id=client_id.strip(), api_key=api_key.strip())
    if not credentials.client_id or not credentials.api_key:
        raise ImaOperationError("ima_credentials_missing", "client id and api key are required")
    await _verify(credentials)
    await save_credentials(credentials)
    async with get_session() as db:
        state = await load_ima_state(db, agent_id=agent_id)
        if state.needs_reauth:
            state.needs_reauth = False
            state.last_error_kind = ""
            await save_ima_state(db, state, agent_id=agent_id)
    await trigger_if_active(agent_id)


async def disconnect() -> None:
    """Drop the credentials and every agent's sync job. Imported documents and the ledger stay in place."""
    await stop_all_jobs()
    await clear_credentials()


async def list_libraries() -> list[ImaLibrary]:
    async with ImaTransport(await _require_credentials()) as transport:
        libraries = await ImaClient(transport).list_knowledge_bases()
    return [ImaLibrary(id=library.id, name=library.name) for library in libraries]


async def save_selection(*, library_ids: list[str], include_notes: bool, agent_id: str | None) -> ImaSyncConfig:
    """Names come from ima's own listing, never from the request, and unknown ids are dropped."""
    known = {library.id: library for library in await list_libraries()}
    selected = [
        ImaKbSelection(id=known[library_id].id, name=known[library_id].name)
        for library_id in dict.fromkeys(library_ids)
        if library_id in known
    ][:_MAX_SELECTED_LIBRARIES]
    async with get_session() as db:
        return await save_ima_config(db, ImaSyncConfig(knowledge_bases=selected, include_notes=include_notes), agent_id=agent_id)


async def start_sync(*, agent_id: str | None, locale: str) -> None:
    await _require_credentials()
    async with get_session() as db:
        config = await load_ima_config(db, agent_id=agent_id)
    if not (config.knowledge_bases or config.include_notes):
        raise ImaOperationError("ima_no_selection", "nothing selected to import")
    await start_job(agent_id, locale=locale)


async def pause_sync(*, agent_id: str | None) -> None:
    if not await pause_job(agent_id):
        raise ImaOperationError("ima_sync_not_started", "sync has not been started")


async def resume_sync(*, agent_id: str | None) -> None:
    if not await resume_job(agent_id):
        raise ImaOperationError("ima_sync_not_started", "sync has not been started")


async def retry_failed(*, agent_id: str | None) -> int:
    async with get_session() as db:
        reset = await ImaLedger(normalize_agent_scope(agent_id)).retry_failed(db)
        await db.commit()
    if reset:
        await trigger_if_active(agent_id)
    return reset


async def compile_imported(*, llm: BaseChatModel, agent_id: str | None) -> int:
    """Queue only the documents ima imported (and that still need compiling), not the rest of the vault."""
    from myrm_agent_harness.toolkits.wiki.pipeline.compiler_enqueue import filter_changed_files
    from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup import CorpusEligibilityFilter

    from app.services.wiki.dedup_runner import wiki_dedup_blocks_compile

    if wiki_dedup_blocks_compile(agent_id=agent_id):
        raise ImaOperationError("dedup_review_required", "resolve duplicate groups before compiling")
    archiver = get_wiki_archiver(llm, agent_id=agent_id)
    structure = archiver._structure
    async with get_session() as db:
        raw_paths = await ImaLedger(normalize_agent_scope(agent_id)).synced_paths(db)
    existing: list[Path] = []
    for relative in raw_paths:
        try:
            path = structure.get_raw_file_path(relative)
        except ValueError:
            continue
        if path.is_file():
            existing.append(path)
    eligible = await filter_changed_files(structure, CorpusEligibilityFilter(structure).filter_raw_paths(existing))
    in_flight = set(archiver._queue.list_processing_file_paths())
    files = [path for path in eligible if str(path) not in in_flight]
    if files:
        archiver._queue.add_batch(files)
        archiver._compiler.start_background_worker()
    return len(files)
