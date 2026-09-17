"""Domain Mesh API endpoints for Three-Domain progressive L0/L1/L2 memory view and migration.

[INPUT]
MemoryManager (harness 记忆管理器), HermesMigrationRequest (Hermes 迁移请求)

[OUTPUT]
router: `/memory/domain-mesh` 三域认知网格概览、下钻追溯与无损迁移端点

[POS]
app.api.memory.operations.domain_mesh: 三域认知网格操作层，提供 User/Assistant/Task 三域概览、L0/L1/L2 追溯及迁移路由
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from myrm_agent_harness.toolkits.memory import (
    MemoryDomain,
    MemoryManager,
    import_hermes_bundle,
    infer_domain_and_category,
)

from app.api.memory.utils import get_memory_manager
from app.schemas.memory.domain_mesh import (
    DomainBucketOverview,
    DomainMeshOverviewResponse,
    DrillDownResponse,
    HermesMigrationRequest,
    HermesMigrationResponse,
    ProgressiveHighlight,
)
from app.services.memory.command_center.command_center import ALL_MEMORY_TYPES

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/domain-mesh", tags=["memory-domain-mesh"])


@router.get("/overview", response_model=DomainMeshOverviewResponse)
async def get_domain_mesh_overview(
    manager: MemoryManager = Depends(get_memory_manager),
) -> DomainMeshOverviewResponse:
    """Return aggregated stats and L0/L1 previews across User, Assistant, and Task domains."""
    user_highlights: list[ProgressiveHighlight] = []
    assistant_highlights: list[ProgressiveHighlight] = []
    task_highlights: list[ProgressiveHighlight] = []

    user_cats: dict[str, int] = {}
    assistant_cats: dict[str, int] = {}
    task_cats: dict[str, int] = {}

    for mtype in ALL_MEMORY_TYPES:
        try:
            mems = await manager.list_memories(mtype, limit=2000)
        except Exception:
            continue

        for m in mems:
            dom = getattr(m, "domain", None)
            dom_val = dom.value if hasattr(dom, "value") else (str(dom) if dom is not None else "")
            cat = getattr(m, "domain_category", None) or ""

            if not dom_val or dom_val not in (
                MemoryDomain.USER.value,
                MemoryDomain.ASSISTANT.value,
                MemoryDomain.TASK.value,
            ):
                raw_tags = getattr(m, "tags", None) or []
                safe_tags = [str(t) for t in raw_tags if isinstance(t, (str, int, float))]
                infer_dom, infer_cat = infer_domain_and_category(
                    memory_type=mtype.value,
                    content=getattr(m, "content", ""),
                    event_type=getattr(m, "event_type", None),
                    preference_type=getattr(m, "preference_type", None),
                    tags=safe_tags,
                )
                dom_val = infer_dom.value
                cat = cat or infer_cat.value
            else:
                cat = cat or "profile"

            l0 = getattr(m, "summary_l0", "") or (
                m.content[:120].strip() if hasattr(m, "content") else ""
            )
            l1 = getattr(m, "overview_l1", "") or (
                m.content[:300].strip() if hasattr(m, "content") else ""
            )
            upd = (
                m.updated_at.isoformat()
                if hasattr(m, "updated_at") and m.updated_at
                else (
                    m.created_at.isoformat()
                    if hasattr(m, "created_at") and m.created_at
                    else ""
                )
            )
            item = ProgressiveHighlight(
                id=m.id,
                l0=l0,
                l1=l1,
                category=cat,
                memory_type=mtype.value,
                updated_at=upd,
            )

            if dom_val == MemoryDomain.ASSISTANT.value:
                assistant_cats[cat] = assistant_cats.get(cat, 0) + 1
                if len(assistant_highlights) < 10:
                    assistant_highlights.append(item)
            elif dom_val == MemoryDomain.TASK.value:
                task_cats[cat] = task_cats.get(cat, 0) + 1
                if len(task_highlights) < 10:
                    task_highlights.append(item)
            else:
                user_cats[cat] = user_cats.get(cat, 0) + 1
                if len(user_highlights) < 10:
                    user_highlights.append(item)

    total = sum(user_cats.values()) + sum(assistant_cats.values()) + sum(task_cats.values())
    return DomainMeshOverviewResponse(
        user=DomainBucketOverview(
            domain="user",
            total_count=sum(user_cats.values()),
            category_counts=user_cats,
            highlights=user_highlights,
        ),
        assistant=DomainBucketOverview(
            domain="assistant",
            total_count=sum(assistant_cats.values()),
            category_counts=assistant_cats,
            highlights=assistant_highlights,
        ),
        task=DomainBucketOverview(
            domain="task",
            total_count=sum(task_cats.values()),
            category_counts=task_cats,
            highlights=task_highlights,
        ),
        total_memories=total,
    )


@router.get("/drill-down/{memory_id}", response_model=DrillDownResponse)
async def get_memory_drill_down(
    memory_id: str,
    manager: MemoryManager = Depends(get_memory_manager),
) -> DrillDownResponse:
    """Retrieve full L2 verbatim content and metadata for a single memory."""
    mem = await manager.get_memory(memory_id)
    if mem is None:
        raise HTTPException(status_code=404, detail=f"Memory '{memory_id}' not found.")

    dom = getattr(mem, "domain", None)
    dom_val = dom.value if hasattr(dom, "value") else (str(dom) if dom is not None else "")
    cat = getattr(mem, "domain_category", None) or ""

    if not dom_val or dom_val not in (
        MemoryDomain.USER.value,
        MemoryDomain.ASSISTANT.value,
        MemoryDomain.TASK.value,
    ):
        mem_type_name = getattr(mem, "memory_type", "semantic")
        mem_type_str = mem_type_name.value if hasattr(mem_type_name, "value") else str(mem_type_name)
        raw_tags = getattr(mem, "tags", None) or []
        safe_tags = [str(t) for t in raw_tags if isinstance(t, (str, int, float))]
        infer_dom, infer_cat = infer_domain_and_category(
            memory_type=mem_type_str,
            content=getattr(mem, "content", ""),
            event_type=getattr(mem, "event_type", None),
            preference_type=getattr(mem, "preference_type", None),
            tags=safe_tags,
        )
        dom_val = infer_dom.value
        cat = cat or infer_cat.value
    else:
        cat = cat or "profile"

    l0 = getattr(mem, "summary_l0", "") or (
        mem.content[:120].strip() if hasattr(mem, "content") else ""
    )
    l1 = getattr(mem, "overview_l1", "") or (
        mem.content[:300].strip() if hasattr(mem, "content") else ""
    )
    l2 = getattr(mem, "content", "")
    created = (
        mem.created_at.isoformat()
        if hasattr(mem, "created_at") and mem.created_at
        else ""
    )
    updated = (
        mem.updated_at.isoformat()
        if hasattr(mem, "updated_at") and mem.updated_at
        else ""
    )
    meta = getattr(mem, "metadata", {}) or {}
    mem_type = getattr(mem, "memory_type", "semantic")
    mem_type_val = mem_type.value if hasattr(mem_type, "value") else str(mem_type)

    return DrillDownResponse(
        id=mem.id,
        domain=dom_val,
        category=cat,
        memory_type=mem_type_val,
        l0=l0,
        l1=l1,
        l2_content=l2,
        created_at=created,
        updated_at=updated,
        metadata=meta,
    )


@router.post("/migrate/hermes", response_model=HermesMigrationResponse)
async def migrate_from_hermes(
    payload: HermesMigrationRequest,
    manager: MemoryManager = Depends(get_memory_manager),
) -> HermesMigrationResponse:
    """Import and migrate Hermes or OpenViking memory bundle into memory manager."""
    is_json = payload.format.lower() == "json"
    success, failures = await import_hermes_bundle(
        manager, payload.content, is_json=is_json
    )
    return HermesMigrationResponse(
        success_count=success,
        fail_count=failures,
        message=f"Migration completed: {success} imported, {failures} failed.",
    )
