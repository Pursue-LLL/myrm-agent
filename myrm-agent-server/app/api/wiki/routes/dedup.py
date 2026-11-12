"""[INPUT]
- app.api.wiki.archiver_dependency::get_scoped_wiki_archiver (POS: Single provider of the archiver for routes that compile, query or mutate a vault. Routes that only read or write vault files use ``app.services.wiki.vault.get_wiki_structure`` instead, so no compile worker is ever built without a model.)
- app.services.wiki::MemoryToWikiArchiver (POS: Top-level wiki facade. Domain subpackages (vault / maintain / governance / obsidian / source_sync / clip / knowledge_pack) live under this package and expose their own facades.)

[OUTPUT]
- WikiDedupMemberResponse: WikiDedupMemberResponse
- WikiDedupMemberSnippetResponse: WikiDedupMemberSnippetResponse
- WikiDedupGroupResponse: WikiDedupGroupResponse
- WikiDedupScanResponse: WikiDedupScanResponse
- WikiDedupDispositionRequest: WikiDedupDispositionRequest
- WikiDedupDispositionResponse: WikiDedupDispositionResponse
- WikiDedupProgressResponse: WikiDedupProgressResponse
- WikiDedupTrashedEntryResponse: WikiDedupTrashedEntryResponse
- WikiDedupExcludedEntryResponse: WikiDedupExcludedEntryResponse
- WikiDedupVaultHygieneResponse: WikiDedupVaultHygieneResponse
- WikiDedupPathActionRequest: WikiDedupPathActionRequest
- scan_wiki_duplicates: scan_wiki_duplicates
- list_wiki_duplicate_groups: list_wiki_duplicate_groups
- get_wiki_dedup_group_snippets: get_wiki_dedup_group_snippets
- apply_wiki_duplicate_disposition: apply_wiki_duplicate_disposition
- get_wiki_dedup_progress: get_wiki_dedup_progress
- get_wiki_dedup_vault_hygiene: get_wiki_dedup_vault_hygiene
- restore_wiki_dedup_trashed_raw: restore_wiki_dedup_trashed_raw
- undo_wiki_dedup_excluded_raw: undo_wiki_dedup_excluded_raw

[POS]
Wiki API 的子路由模块；由 app/api/wiki/router.py 组装到 /wiki 前缀下。
"""

import logging
from typing import TYPE_CHECKING, Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.wiki.archiver_dependency import get_scoped_wiki_archiver as _get_wiki_archiver
from app.services.wiki import MemoryToWikiArchiver

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

router = APIRouter(tags=["wiki"])


class WikiDedupMemberResponse(BaseModel):
    relative_path: str
    size_bytes: int
    mtime_ns: int


class WikiDedupMemberSnippetResponse(BaseModel):
    relative_path: str
    snippet: str


class WikiDedupGroupResponse(BaseModel):
    group_id: int
    tier: Literal["exact", "normalized", "near"]
    fingerprint: str
    recommended_keep_path: str
    status: Literal["open", "deferred", "resolved"]
    members: list[WikiDedupMemberResponse]


class WikiDedupScanResponse(BaseModel):
    accepted: bool = False
    skipped: bool = False
    skipped_reason: str | None = None
    files_scanned: int = 0
    groups_found: int = 0
    open_groups: int = 0
    exact_groups: int = 0
    normalized_groups: int = 0
    near_groups: int = 0
    duration_ms: int = 0


class WikiDedupDispositionRequest(BaseModel):
    action: Literal["trash", "exclude", "dismiss", "defer"]
    reason: str = Field(default="", max_length=500)


class WikiDedupDispositionResponse(BaseModel):
    group_id: int
    action: Literal["trash", "exclude", "dismiss", "defer"]
    affected_paths: list[str] = Field(default_factory=list)
    compile_jobs_prevented: int = 0


class WikiDedupProgressResponse(BaseModel):
    phase: Literal["idle", "scanning", "grouping", "done", "failed"] = "idle"
    files_scanned: int = 0
    files_total: int = 0
    groups_found: int = 0
    message: str = ""


class WikiDedupTrashedEntryResponse(BaseModel):
    relative_path: str
    trash_relpath: str
    content_hash: str
    created_at: str


class WikiDedupExcludedEntryResponse(BaseModel):
    relative_path: str
    reason: str
    created_at: str


class WikiDedupVaultHygieneResponse(BaseModel):
    trashed: list[WikiDedupTrashedEntryResponse] = Field(default_factory=list)
    excluded: list[WikiDedupExcludedEntryResponse] = Field(default_factory=list)


class WikiDedupPathActionRequest(BaseModel):
    relative_path: str = Field(min_length=1, max_length=2048)


@router.post("/dedup/scan", response_model=WikiDedupScanResponse, status_code=202)
async def scan_wiki_duplicates(
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
    incremental: Annotated[bool, Query(description="Incremental scan mode")] = True,
) -> WikiDedupScanResponse:
    from app.services.wiki.dedup_runner import schedule_wiki_dedup_scan

    result = await schedule_wiki_dedup_scan(agent_id=agent_id, incremental=incremental)
    if result.skipped and result.skipped_reason == "compile_in_progress":
        raise HTTPException(
            status_code=409,
            detail="Wiki compilation is in progress; dedup scan skipped",
        )
    if result.skipped and result.skipped_reason == "scan_in_progress":
        return WikiDedupScanResponse(skipped=True, skipped_reason=result.skipped_reason)
    if not result.accepted:
        return WikiDedupScanResponse(skipped=True, skipped_reason=result.skipped_reason)
    return WikiDedupScanResponse(accepted=True)


@router.get("/dedup/groups", response_model=list[WikiDedupGroupResponse])
async def list_wiki_duplicate_groups(
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
) -> list[WikiDedupGroupResponse]:
    from app.services.wiki.dedup_runner import list_wiki_dedup_groups

    groups = list_wiki_dedup_groups(agent_id=agent_id)
    return [
        WikiDedupGroupResponse(
            group_id=group.group_id,
            tier=group.tier.value,
            fingerprint=group.fingerprint,
            recommended_keep_path=group.recommended_keep_path,
            status=group.status.value,
            members=[
                WikiDedupMemberResponse(
                    relative_path=member.relative_path,
                    size_bytes=member.size_bytes,
                    mtime_ns=member.mtime_ns,
                )
                for member in group.members
            ],
        )
        for group in groups
    ]


@router.get(
    "/dedup/groups/{group_id}/snippets",
    response_model=list[WikiDedupMemberSnippetResponse],
)
async def get_wiki_dedup_group_snippets(
    group_id: int,
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
) -> list[WikiDedupMemberSnippetResponse]:
    from app.services.wiki.dedup_runner import get_wiki_dedup_group_snippets

    try:
        snippets = get_wiki_dedup_group_snippets(agent_id=agent_id, group_id=group_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [WikiDedupMemberSnippetResponse(relative_path=item.relative_path, snippet=item.snippet) for item in snippets]


@router.post("/dedup/groups/{group_id}/disposition", response_model=WikiDedupDispositionResponse)
async def apply_wiki_duplicate_disposition(
    group_id: int,
    request: WikiDedupDispositionRequest,
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
) -> WikiDedupDispositionResponse:
    from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup import DispositionAction

    from app.services.wiki.dedup_runner import apply_wiki_dedup_disposition

    action = DispositionAction(request.action)
    if action in {DispositionAction.TRASH, DispositionAction.EXCLUDE} and not request.reason.strip():
        raise HTTPException(status_code=422, detail="reason is required for trash/exclude dispositions")
    try:
        result = await apply_wiki_dedup_disposition(
            archiver=archiver,
            group_id=group_id,
            action=action,
            reason=request.reason.strip() or "Duplicate review disposition",
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return WikiDedupDispositionResponse(
        group_id=result.group_id,
        action=result.action.value,
        affected_paths=list(result.affected_paths),
        compile_jobs_prevented=result.compile_jobs_prevented,
    )


@router.get("/dedup/progress", response_model=WikiDedupProgressResponse)
async def get_wiki_dedup_progress(
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
) -> WikiDedupProgressResponse:
    from app.services.wiki.dedup_runner import get_wiki_dedup_progress

    progress = get_wiki_dedup_progress(agent_id=agent_id)
    return WikiDedupProgressResponse(
        phase=progress.phase,
        files_scanned=progress.files_scanned,
        files_total=progress.files_total,
        groups_found=progress.groups_found,
        message=progress.message,
    )


@router.get("/dedup/vault-hygiene", response_model=WikiDedupVaultHygieneResponse)
async def get_wiki_dedup_vault_hygiene(
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
) -> WikiDedupVaultHygieneResponse:
    from app.services.wiki.dedup_runner import get_wiki_dedup_vault_hygiene

    snapshot = get_wiki_dedup_vault_hygiene(agent_id=agent_id)
    return WikiDedupVaultHygieneResponse(
        trashed=[
            WikiDedupTrashedEntryResponse(
                relative_path=entry.relative_path,
                trash_relpath=entry.trash_relpath,
                content_hash=entry.content_hash,
                created_at=entry.created_at,
            )
            for entry in snapshot.trashed
        ],
        excluded=[
            WikiDedupExcludedEntryResponse(
                relative_path=entry.relative_path,
                reason=entry.reason,
                created_at=entry.created_at,
            )
            for entry in snapshot.excluded
        ],
    )


@router.post("/dedup/trash/restore", response_model=WikiDedupTrashedEntryResponse)
async def restore_wiki_dedup_trashed_raw(
    request: WikiDedupPathActionRequest,
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
) -> WikiDedupTrashedEntryResponse:
    from app.services.wiki.dedup_runner import restore_wiki_dedup_trashed

    try:
        restored = await restore_wiki_dedup_trashed(archiver=archiver, agent_id=agent_id, relative_path=request.relative_path)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return WikiDedupTrashedEntryResponse(
        relative_path=restored.relative_path,
        trash_relpath=restored.trash_relpath,
        content_hash=restored.content_hash,
        created_at=restored.created_at,
    )


@router.post("/dedup/excluded/undo", response_model=WikiDedupExcludedEntryResponse)
async def undo_wiki_dedup_excluded_raw(
    request: WikiDedupPathActionRequest,
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
) -> WikiDedupExcludedEntryResponse:
    from app.services.wiki.dedup_runner import undo_wiki_dedup_excluded

    try:
        restored = await undo_wiki_dedup_excluded(agent_id=agent_id, relative_path=request.relative_path)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return WikiDedupExcludedEntryResponse(
        relative_path=restored.relative_path,
        reason=restored.reason,
        created_at=restored.created_at,
    )
