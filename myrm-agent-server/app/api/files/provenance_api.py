"""Artifact Provenance and Cross-Session Asset Hub API.

[INPUT]
- app.database.connection::get_db (POS: Database session dependency)
- app.database.models.artifact::Artifact, ArtifactVersion, ArtifactAuditLog (POS: Artifact models)
- app.database.models.chat::Chat (POS: Chat session model for provenance association)
- myrm_agent_harness.agent.artifacts.vault::ArtifactVault (POS: Vault object store)

[OUTPUT]
- router: APIRouter — Artifact Provenance & cross-session retrieval endpoints

[POS]
Provides cross-session aggregation, multi-format classification, and bidirectional provenance
graph endpoints linking artifacts back to their originating chat sessions and turns.
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from myrm_agent_harness.agent.artifacts.vault import ArtifactVault
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.connection import get_db
from app.database.models.artifact import Artifact
from app.database.models.chat import Chat
from app.platform_utils.workspace_root import get_workspace_root

logger = logging.getLogger(__name__)

router = APIRouter()

ArtifactCategory = Literal["all", "document", "code", "data", "media", "link", "other"]

_DOC_EXTS: frozenset[str] = frozenset({"md", "markdown", "pdf", "docx", "doc", "txt", "rtf"})
_CODE_EXTS: frozenset[str] = frozenset({"py", "ts", "tsx", "js", "jsx", "sh", "json", "yaml", "yml", "html", "css", "sql", "rs", "go"})
_DATA_EXTS: frozenset[str] = frozenset({"csv", "tsv", "xlsx", "xls", "parquet"})
_MEDIA_EXTS: frozenset[str] = frozenset({"png", "jpg", "jpeg", "svg", "gif", "webp", "mp4", "mp3", "wav"})
_LINK_EXTS: frozenset[str] = frozenset({"url", "webloc", "link"})


def classify_artifact_category(name: str) -> str:
    """Classify artifact into semantic asset categories based on filename and extension."""
    lower_name = name.lower().strip()
    if lower_name.startswith("http://") or lower_name.startswith("https://"):
        return "link"
    ext = lower_name.rsplit(".", 1)[-1] if "." in lower_name else ""
    if ext in _DOC_EXTS:
        return "document"
    if ext in _CODE_EXTS:
        return "code"
    if ext in _DATA_EXTS:
        return "data"
    if ext in _MEDIA_EXTS:
        return "media"
    if ext in _LINK_EXTS:
        return "link"
    return "other"


class ArtifactProvenanceItem(BaseModel):
    id: str
    name: str
    description: str | None = None
    category: str
    created_at: str
    updated_at: str
    chat_id: str | None = None
    chat_title: str | None = None
    agent_id: str | None = None
    latest_version_id: str | None = None
    vault_uri: str | None = None
    sha256_hash: str | None = None
    commit_message: str | None = None
    size_bytes: int | None = None
    extension: str


class ArtifactCategoryStats(BaseModel):
    all: int = 0
    document: int = 0
    code: int = 0
    data: int = 0
    media: int = 0
    link: int = 0
    other: int = 0


class ArtifactProvenanceListResponse(BaseModel):
    items: list[ArtifactProvenanceItem]
    total: int
    stats: ArtifactCategoryStats


class ArtifactVersionTimelineEntry(BaseModel):
    version_id: str
    vault_uri: str
    sha256_hash: str
    creator_id: str | None = None
    commit_message: str | None = None
    created_at: str
    size_bytes: int | None = None


class ArtifactProvenanceDetailResponse(BaseModel):
    artifact: ArtifactProvenanceItem
    versions: list[ArtifactVersionTimelineEntry]
    audit_logs_count: int


def _get_artifact_size(vault: ArtifactVault, vault_uri: str | None) -> int | None:
    if not vault_uri:
        return None
    try:
        object_id = vault_uri[len("vault://") :] if vault_uri.startswith("vault://") else vault_uri
        object_path = vault.get_object_path(object_id)
        if object_path.exists():
            return object_path.stat().st_size
    except Exception:
        pass
    return None


@router.get("/provenance", response_model=ArtifactProvenanceListResponse)
async def list_artifact_provenance(
    category: ArtifactCategory = Query("all", description="Filter by asset category"),
    query: str | None = Query(None, description="Fuzzy match search on artifact name or description"),
    chat_id: str | None = Query(None, description="Filter by originating chat session ID"),
    agent_id: str | None = Query(None, description="Filter by associated Agent ID"),
    limit: int = Query(50, ge=1, le=200, description="Page limit"),
    offset: int = Query(0, ge=0, description="Page offset"),
    db: AsyncSession = Depends(get_db),
) -> ArtifactProvenanceListResponse:
    """Retrieve cross-session artifact provenance hub items with multi-category filters and statistics."""
    workspace_root = get_workspace_root()
    vault = ArtifactVault(workspace_root=workspace_root)

    # 1. Base query with preloaded versions and join on chat
    stmt = (
        select(Artifact, Chat)
        .outerjoin(Chat, Artifact.chat_id == Chat.id)
        .options(selectinload(Artifact.versions))
        .where(Artifact.is_deleted.is_(False))
    )

    if chat_id:
        stmt = stmt.where(Artifact.chat_id == chat_id)
    if agent_id:
        stmt = stmt.where(Chat.agent_id == agent_id)
    if query:
        pattern = f"%{query.strip()}%"
        stmt = stmt.where(Artifact.name.ilike(pattern) | Artifact.description.ilike(pattern))

    result = await db.execute(stmt.order_by(Artifact.updated_at.desc()))
    rows = result.all()

    # 2. Map and aggregate category statistics
    all_items: list[ArtifactProvenanceItem] = []
    category_counts: dict[str, int] = {
        "all": len(rows),
        "document": 0,
        "code": 0,
        "data": 0,
        "media": 0,
        "link": 0,
        "other": 0,
    }

    for artifact, chat in rows:
        cat = classify_artifact_category(artifact.name)
        if cat in category_counts:
            category_counts[cat] += 1
        else:
            category_counts["other"] += 1

        latest_version = max(artifact.versions, key=lambda v: v.created_at) if artifact.versions else None
        size_bytes = _get_artifact_size(vault, latest_version.vault_uri if latest_version else None)
        ext = artifact.name.rsplit(".", 1)[-1] if "." in artifact.name else ""

        all_items.append(
            ArtifactProvenanceItem(
                id=artifact.id,
                name=artifact.name,
                description=artifact.description,
                category=cat,
                created_at=artifact.created_at.isoformat(),
                updated_at=artifact.updated_at.isoformat(),
                chat_id=artifact.chat_id,
                chat_title=chat.title if chat else None,
                agent_id=chat.agent_id if chat else None,
                latest_version_id=latest_version.id if latest_version else None,
                vault_uri=latest_version.vault_uri if latest_version else None,
                sha256_hash=latest_version.sha256_hash if latest_version else None,
                commit_message=latest_version.commit_message if latest_version else None,
                size_bytes=size_bytes,
                extension=ext,
            )
        )

    # 3. Filter by category if requested
    if category != "all":
        filtered_items = [item for item in all_items if item.category == category]
    else:
        filtered_items = all_items

    paginated = filtered_items[offset : offset + limit]

    return ArtifactProvenanceListResponse(
        items=paginated,
        total=len(filtered_items),
        stats=ArtifactCategoryStats(**category_counts),
    )


@router.get("/provenance/{artifact_id}", response_model=ArtifactProvenanceDetailResponse)
async def get_artifact_provenance_detail(
    artifact_id: str,
    db: AsyncSession = Depends(get_db),
) -> ArtifactProvenanceDetailResponse:
    """Retrieve full bidirectional provenance graph, version history, and audit log count for a specific artifact."""
    workspace_root = get_workspace_root()
    vault = ArtifactVault(workspace_root=workspace_root)

    stmt = (
        select(Artifact, Chat)
        .outerjoin(Chat, Artifact.chat_id == Chat.id)
        .options(selectinload(Artifact.versions), selectinload(Artifact.audit_logs))
        .where(Artifact.id == artifact_id, Artifact.is_deleted.is_(False))
    )
    result = await db.execute(stmt)
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Artifact not found")

    artifact, chat = row
    latest_version = max(artifact.versions, key=lambda v: v.created_at) if artifact.versions else None
    size_bytes = _get_artifact_size(vault, latest_version.vault_uri if latest_version else None)
    cat = classify_artifact_category(artifact.name)
    ext = artifact.name.rsplit(".", 1)[-1] if "." in artifact.name else ""

    item = ArtifactProvenanceItem(
        id=artifact.id,
        name=artifact.name,
        description=artifact.description,
        category=cat,
        created_at=artifact.created_at.isoformat(),
        updated_at=artifact.updated_at.isoformat(),
        chat_id=artifact.chat_id,
        chat_title=chat.title if chat else None,
        agent_id=chat.agent_id if chat else None,
        latest_version_id=latest_version.id if latest_version else None,
        vault_uri=latest_version.vault_uri if latest_version else None,
        sha256_hash=latest_version.sha256_hash if latest_version else None,
        commit_message=latest_version.commit_message if latest_version else None,
        size_bytes=size_bytes,
        extension=ext,
    )

    version_entries: list[ArtifactVersionTimelineEntry] = []
    for ver in sorted(artifact.versions, key=lambda v: v.created_at, reverse=True):
        ver_size = _get_artifact_size(vault, ver.vault_uri)
        version_entries.append(
            ArtifactVersionTimelineEntry(
                version_id=ver.id,
                vault_uri=ver.vault_uri,
                sha256_hash=ver.sha256_hash,
                creator_id=ver.creator_id,
                commit_message=ver.commit_message,
                created_at=ver.created_at.isoformat(),
                size_bytes=ver_size,
            )
        )

    return ArtifactProvenanceDetailResponse(
        artifact=item,
        versions=version_entries,
        audit_logs_count=len(artifact.audit_logs),
    )
