"""Tool Guidance API endpoints for observing and governing tool evolution."""

from __future__ import annotations

import logging
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, status
from myrm_agent_harness.toolkits.memory import (
    MemoryManager,
    ProceduralMemory,
    ToolGuidanceItem,
    synthesize_tool_guidance,
)

from app.api.memory.utils import get_crud_memory_manager
from app.schemas.memory.tool_guidance import (
    PinGuidanceRequest,
    PinGuidanceResponse,
    ToolGuidanceGroupDTO,
    ToolGuidanceItemDTO,
    ToolGuidanceListResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tool-guidance", tags=["memory-tool-guidance"])


@router.get("", response_model=ToolGuidanceListResponse)
async def get_tool_guidance(
    manager: MemoryManager = Depends(get_crud_memory_manager),
) -> ToolGuidanceListResponse:
    """List aggregated tool guidance and raw procedural memories scoped by tool."""
    relational = getattr(manager, "_relational", None)
    if not relational:
        return ToolGuidanceListResponse(tools=[], total_tools=0, total_rules=0)

    rules = await relational.list_rules(active_only=True, limit=200)
    items_by_tool: dict[str, list[ToolGuidanceItemDTO]] = defaultdict(list)
    raw_guidance_items: list[ToolGuidanceItem] = []

    for r in rules:
        if not isinstance(r, ProceduralMemory) or not r.tool_name:
            continue

        item_dto = ToolGuidanceItemDTO(
            id=r.id,
            tool_name=r.tool_name,
            rule_text=r.action,
            trigger_pattern=r.trigger,
            confidence=1.0 if r.is_user_locked else 0.8,
            is_pinned=r.is_user_locked,
            env_fingerprint=str(r.metadata.get("env_fingerprint")) if r.metadata.get("env_fingerprint") else None,
            agent_id=str(r.metadata.get("agent_id")) if r.metadata.get("agent_id") else None,
            source="manual" if r.is_user_locked else "self_healing",
            hit_count=int(r.metadata.get("hit_count", 1)),
            created_at=r.created_at.isoformat() if hasattr(r.created_at, "isoformat") else str(r.created_at),
            updated_at=r.updated_at.isoformat() if hasattr(r.updated_at, "isoformat") else str(r.updated_at),
        )
        items_by_tool[r.tool_name].append(item_dto)

        raw_guidance_items.append(
            ToolGuidanceItem(
                id=r.id,
                tool_name=r.tool_name,
                rule_text=r.action,
                trigger_pattern=r.trigger,
                confidence=1.0 if r.is_user_locked else 0.8,
                is_pinned=r.is_user_locked,
                env_fingerprint=str(r.metadata.get("env_fingerprint")) if r.metadata.get("env_fingerprint") else None,
                agent_id=str(r.metadata.get("agent_id")) if r.metadata.get("agent_id") else None,
                source="manual" if r.is_user_locked else "self_healing",
                hit_count=int(r.metadata.get("hit_count", 1)),
            )
        )

    synthesized_map = synthesize_tool_guidance(raw_guidance_items)

    groups: list[ToolGuidanceGroupDTO] = []
    total_rules = 0

    for tool_name in sorted(items_by_tool.keys()):
        tool_items = items_by_tool[tool_name]
        total_rules += len(tool_items)
        has_pinned = any(it.is_pinned for it in tool_items)
        guidelines = synthesized_map.get(tool_name, [])

        groups.append(
            ToolGuidanceGroupDTO(
                tool_name=tool_name,
                guidelines=guidelines,
                has_pinned=has_pinned,
                items=tool_items,
            )
        )

    return ToolGuidanceListResponse(
        tools=groups,
        total_tools=len(groups),
        total_rules=total_rules,
    )


@router.post("/pin", response_model=PinGuidanceResponse)
async def pin_tool_guidance(
    payload: PinGuidanceRequest,
    manager: MemoryManager = Depends(get_crud_memory_manager),
) -> PinGuidanceResponse:
    """Pin or unpin a procedural rule for a tool to make it permanent/prioritized."""
    relational = getattr(manager, "_relational", None)
    if not relational:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Relational store unavailable",
        )

    rule = await relational.get_rule(payload.rule_id)
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rule {payload.rule_id} not found",
        )

    # In ProceduralMemory, is_user_locked designates user-endorsed/pinned status
    rule.is_user_locked = payload.is_pinned
    await relational.update_rule(payload.rule_id, rule)

    return PinGuidanceResponse(rule_id=payload.rule_id, is_pinned=payload.is_pinned)


@router.delete("/{rule_id}")
async def delete_tool_guidance(
    rule_id: str,
    manager: MemoryManager = Depends(get_crud_memory_manager),
) -> dict[str, str]:
    """Delete a tool procedural guideline."""
    relational = getattr(manager, "_relational", None)
    if not relational:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Relational store unavailable",
        )

    deleted = await relational.delete_rule(rule_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rule {rule_id} not found",
        )
    return {"status": "deleted", "rule_id": rule_id}
