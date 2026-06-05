"""Controlled migration review API.

External migration bundles are staged for human review first and only applied
after approval through the unified review inbox.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from myrm_agent_harness.toolkits.memory import MemoryManager
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select

from app.api.dependencies import get_deploy_identity
from app.api.memory.utils import get_crud_memory_manager
from app.database.connection import get_session
from app.database.models import PendingMigration
from app.schemas.memory.archive import MemoryImportRequest
from app.schemas.memory.crud import MEMORY_EXPORT_VERSION
from app.services.skills.experience_ledger import (
    ExperienceEntityType,
    ExperienceEventType,
    ExperienceLedgerWrite,
    record_experience_event,
)

router = APIRouter(prefix="/migrations", tags=["migrations"])


async def _apply_skill_migration(skills_raw: list[object]) -> dict[str, int]:
    """Write competitor skill bundles into the default local skills directory."""

    import shutil
    from pathlib import Path

    from app.core.skills.models import DEFAULT_LOCAL_SKILL_PATHS

    base = Path(DEFAULT_LOCAL_SKILL_PATHS[0]).expanduser()
    base.mkdir(parents=True, exist_ok=True)
    imported = 0
    overwritten = 0

    for item in skills_raw:
        if not isinstance(item, dict):
            continue
        name_raw = item.get("name")
        content_raw = item.get("content")
        if not isinstance(name_raw, str) or not isinstance(content_raw, str):
            continue
        name = name_raw.strip()
        content = content_raw.strip()
        if not name or not content:
            continue
        skill_dir = base / name
        skill_md = skill_dir / "SKILL.md"
        if skill_md.is_file():
            backup = skill_md.with_name(f"{skill_md.name}.bak-migration")
            shutil.copy2(skill_md, backup)
            overwritten += 1
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_md.write_text(content, encoding="utf-8")
        imported += 1

    return {"skills_imported": imported, "skills_overwritten": overwritten}


def _migration_lineage_id(migration_id: str) -> str:
    return f"migration:{migration_id}"


class MigrationMemorySubmitRequest(MemoryImportRequest):
    source: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="迁移来源，例如 hermes/openclaw/manual",
    )
    description: str | None = Field(None, max_length=500, description="可选的迁移说明")


class MigrationSkillSubmitRequest(BaseModel):
    source: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="迁移来源，例如 hermes/openclaw/manual",
    )
    version: str = Field("1.0", description="迁移数据版本")
    skills: list[dict[str, object]] = Field(..., description="技能数据列表")
    description: str | None = Field(None, max_length=500, description="可选的迁移说明")
    target_agent_id: str | None = Field(
        None,
        description="Agent that should receive approved skills on migration bind",
    )


class PendingMigrationResponse(BaseModel):
    id: str
    source: str
    migration_type: str
    summary: str
    total_items: int
    item_counts: dict[str, int]
    status: str
    created_at: str
    target_agent_id: str | None = None
    target_agent_name: str | None = None


class PendingMigrationListResponse(BaseModel):
    items: list[PendingMigrationResponse]
    total: int


class MigrationSubmitResponse(BaseModel):
    migration_id: str
    status: str
    total_items: int


def _normalize_item_counts(data: dict[str, list[dict[str, object]]]) -> dict[str, int]:
    return {memory_type: len(items) for memory_type, items in data.items() if items}


def _build_summary(
    *,
    source: str,
    total_items: int,
    item_counts: dict[str, int],
    description: str | None,
) -> str:
    breakdown = ", ".join(f"{memory_type}:{count}" for memory_type, count in sorted(item_counts.items()))
    base = f"Pending migration from {source} ({total_items} items"
    if breakdown:
        base = f"{base}; {breakdown}"
    base = f"{base})"
    if description:
        return f"{base} - {description.strip()}"
    return base


async def _pending_migration_to_response(
    record: PendingMigration,
) -> PendingMigrationResponse:
    target_agent_id: str | None = None
    target_agent_name: str | None = None
    payload = record.payload
    if isinstance(payload, dict):
        raw_id = payload.get("target_agent_id")
        if isinstance(raw_id, str) and raw_id.strip():
            target_agent_id = raw_id.strip()
            from app.services.agent.agent_service import AgentService

            agent = await AgentService.get_agent_by_id(target_agent_id)
            if agent is not None:
                display_name = str(getattr(agent, "display_name", "") or "").strip()
                target_agent_name = display_name or target_agent_id

    return PendingMigrationResponse(
        id=record.id,
        source=record.source,
        migration_type=record.migration_type,
        summary=record.summary,
        total_items=record.total_items,
        item_counts=record.item_counts,
        status=record.status,
        created_at=record.created_at.isoformat(),
        target_agent_id=target_agent_id,
        target_agent_name=target_agent_name,
    )


async def list_pending_migration_records(limit: int) -> list[PendingMigration]:
    async with get_session() as db:
        stmt = (
            select(PendingMigration)
            .where(
                PendingMigration.status == "pending",
            )
            .order_by(desc(PendingMigration.created_at))
            .limit(limit)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())


async def count_pending_migration_records() -> int:
    async with get_session() as db:
        stmt = (
            select(func.count())
            .select_from(PendingMigration)
            .where(
                PendingMigration.status == "pending",
            )
        )
        total = await db.scalar(stmt)
        return int(total or 0)


async def approve_pending_migration_record(
    migration_id: str,
    manager: MemoryManager | None = None,
) -> PendingMigration:
    async with get_session() as db:
        stmt = select(PendingMigration).where(
            PendingMigration.id == migration_id,
            PendingMigration.status == "pending",
        )
        result = await db.execute(stmt)
        record = result.scalars().first()
        if record is None:
            raise HTTPException(
                status_code=404,
                detail="Pending migration not found or already processed",
            )

        payload = record.payload

        if record.migration_type == "memory_import":
            data = payload.get("data")
            if not isinstance(data, dict):
                raise HTTPException(status_code=400, detail="Pending migration payload is invalid")
            if manager is None:
                raise HTTPException(status_code=503, detail="Memory system unavailable for memory import approval")
            raw_skip_duplicates = payload.get("skip_duplicates", True)
            skip_duplicates = raw_skip_duplicates if isinstance(raw_skip_duplicates, bool) else True
            counts = await manager.import_memories(data, skip_duplicates=skip_duplicates)
        elif record.migration_type == "skill_import":
            skills_raw = payload.get("skills")
            if not isinstance(skills_raw, list):
                raise HTTPException(status_code=400, detail="Pending skill migration payload is invalid")
            counts = await _apply_skill_migration(skills_raw)
            target_agent_id = payload.get("target_agent_id")
            if isinstance(target_agent_id, str) and target_agent_id.strip():
                from app.services.migration.skill_binding import bind_local_skill_names_to_agent

                skill_names = [
                    str(item.get("name", "")).strip()
                    for item in skills_raw
                    if isinstance(item, dict) and str(item.get("name", "")).strip()
                ]
                bound = await bind_local_skill_names_to_agent(target_agent_id.strip(), skill_names)
                counts = {**counts, "skills_bound_to_agent": bound}
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown migration type: {record.migration_type}",
            )

        record.status = "approved"
        record.applied_result = counts
        record.resolved_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(record)

    await record_experience_event(
        ExperienceLedgerWrite(
            event_type=ExperienceEventType.MIGRATION_APPROVED,
            entity_type=ExperienceEntityType.MIGRATION,
            entity_id=record.id,
            lineage_id=_migration_lineage_id(record.id),
            outcome="approved",
            summary=record.summary,
            artifact_refs={
                "source": record.source,
                "migration_type": record.migration_type,
            },
            metrics_snapshot={"total_items": record.total_items, **counts},
            detail={"item_counts": record.item_counts, "applied_result": counts},
        )
    )
    return record


async def reject_pending_migration_record(migration_id: str) -> PendingMigration:
    async with get_session() as db:
        stmt = select(PendingMigration).where(
            PendingMigration.id == migration_id,
            PendingMigration.status == "pending",
        )
        result = await db.execute(stmt)
        record = result.scalars().first()
        if record is None:
            raise HTTPException(
                status_code=404,
                detail="Pending migration not found or already processed",
            )

        record.status = "rejected"
        record.resolved_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(record)

    await record_experience_event(
        ExperienceLedgerWrite(
            event_type=ExperienceEventType.MIGRATION_REJECTED,
            entity_type=ExperienceEntityType.MIGRATION,
            entity_id=record.id,
            lineage_id=_migration_lineage_id(record.id),
            outcome="rejected",
            summary=record.summary,
            artifact_refs={
                "source": record.source,
                "migration_type": record.migration_type,
            },
            metrics_snapshot={"total_items": record.total_items},
            detail={"item_counts": record.item_counts},
        )
    )
    return record


@router.post("/memory/submit", response_model=MigrationSubmitResponse)
async def submit_memory_migration(
    body: MigrationMemorySubmitRequest,
) -> MigrationSubmitResponse:
    """Stage a portable memory bundle for review instead of importing immediately."""
    if body.version != MEMORY_EXPORT_VERSION:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported migration bundle version: {body.version}",
        )

    item_counts = _normalize_item_counts(body.data)
    total_items = sum(item_counts.values())
    if total_items == 0:
        raise HTTPException(status_code=400, detail="Migration bundle is empty")

    record = PendingMigration(
        id=uuid.uuid4().hex,
        source=body.source.strip(),
        migration_type="memory_import",
        summary=_build_summary(
            source=body.source.strip(),
            total_items=total_items,
            item_counts=item_counts,
            description=body.description,
        ),
        total_items=total_items,
        item_counts=item_counts,
        payload={
            "version": body.version,
            "data": body.data,
            "skip_duplicates": body.skip_duplicates,
            "description": body.description,
        },
    )

    async with get_session() as db:
        db.add(record)
        await db.commit()

    await record_experience_event(
        ExperienceLedgerWrite(
            event_type=ExperienceEventType.MIGRATION_SUBMITTED,
            entity_type=ExperienceEntityType.MIGRATION,
            entity_id=record.id,
            lineage_id=_migration_lineage_id(record.id),
            outcome="pending",
            summary=record.summary,
            artifact_refs={
                "source": record.source,
                "migration_type": record.migration_type,
            },
            metrics_snapshot={"total_items": total_items},
            detail={
                "item_counts": item_counts,
                "payload_version": body.version,
                "skip_duplicates": body.skip_duplicates,
            },
        )
    )

    return MigrationSubmitResponse(
        migration_id=record.id,
        status="pending",
        total_items=total_items,
    )


@router.post("/skills/submit", response_model=MigrationSubmitResponse)
async def submit_skill_migration(
    body: MigrationSkillSubmitRequest,
) -> MigrationSubmitResponse:
    """Stage a portable skill bundle for review instead of importing immediately."""
    total_items = len(body.skills)
    if total_items == 0:
        raise HTTPException(status_code=400, detail="Skill migration bundle is empty")

    item_counts = {"skills": total_items}

    record = PendingMigration(
        id=uuid.uuid4().hex,
        source=body.source.strip(),
        migration_type="skill_import",
        summary=_build_summary(
            source=body.source.strip(),
            total_items=total_items,
            item_counts=item_counts,
            description=body.description,
        ),
        total_items=total_items,
        item_counts=item_counts,
        payload={
            "version": body.version,
            "skills": body.skills,
            "description": body.description,
            "target_agent_id": body.target_agent_id,
        },
    )

    async with get_session() as db:
        db.add(record)
        await db.commit()

    await record_experience_event(
        ExperienceLedgerWrite(
            event_type=ExperienceEventType.MIGRATION_SUBMITTED,
            entity_type=ExperienceEntityType.MIGRATION,
            entity_id=record.id,
            lineage_id=_migration_lineage_id(record.id),
            outcome="pending",
            summary=record.summary,
            artifact_refs={
                "source": record.source,
                "migration_type": record.migration_type,
            },
            metrics_snapshot={"total_items": total_items},
            detail={
                "item_counts": item_counts,
                "payload_version": body.version,
            },
        )
    )

    return MigrationSubmitResponse(
        migration_id=record.id,
        status="pending",
        total_items=total_items,
    )


@router.get("/pending", response_model=PendingMigrationListResponse)
async def get_pending_migrations(
    limit: int = Query(50, ge=1, le=100),
) -> PendingMigrationListResponse:
    records = await list_pending_migration_records(limit=limit)
    total = await count_pending_migration_records()
    items = [await _pending_migration_to_response(record) for record in records]
    return PendingMigrationListResponse(items=items, total=total)


@router.post("/pending/{migration_id}/approve", response_model=PendingMigrationResponse)
async def approve_pending_migration(
    migration_id: str,
    user_id: str = Depends(get_deploy_identity),
) -> PendingMigrationResponse:
    manager: MemoryManager | None = None
    async with get_session() as db:
        stmt = select(PendingMigration).where(
            PendingMigration.id == migration_id,
            PendingMigration.status == "pending",
        )
        result = await db.execute(stmt)
        peek = result.scalars().first()
    if peek is not None and peek.migration_type == "memory_import":
        manager = await get_crud_memory_manager()(user_id=user_id)

    record = await approve_pending_migration_record(
        migration_id=migration_id,
        manager=manager,
    )
    await record_experience_event(
        ExperienceLedgerWrite(
            event_type=ExperienceEventType.REVIEW_APPROVED,
            entity_type=ExperienceEntityType.REVIEW,
            entity_id=migration_id,
            lineage_id=_migration_lineage_id(migration_id),
            outcome="approved",
            summary=f"Review approved for migration:{migration_id}",
            artifact_refs={"review_type": "migration", "source": record.source},
            detail={"review_type": "migration", "review_id": migration_id},
        )
    )
    return await _pending_migration_to_response(record)


@router.post("/pending/{migration_id}/reject", response_model=PendingMigrationResponse)
async def reject_pending_migration(
    migration_id: str,
) -> PendingMigrationResponse:
    record = await reject_pending_migration_record(migration_id=migration_id)
    await record_experience_event(
        ExperienceLedgerWrite(
            event_type=ExperienceEventType.REVIEW_REJECTED,
            entity_type=ExperienceEntityType.REVIEW,
            entity_id=migration_id,
            lineage_id=_migration_lineage_id(migration_id),
            outcome="rejected",
            summary=f"Review rejected for migration:{migration_id}",
            artifact_refs={"review_type": "migration", "source": record.source},
            detail={"review_type": "migration", "review_id": migration_id},
        )
    )
    return await _pending_migration_to_response(record)
