"""REST API router for Life Milestones and Personal Timeline Suite.

[POS]
Provides HTTP endpoints for managing lifelong human milestones, evolving personal values,
reflective growth diaries, and empathetic conversational context projections.

[INPUT]
- fastapi
- app.schemas.life_milestones
- app.services.memory.life_milestones.provider
- myrm_agent_harness.toolkits.memory

[OUTPUT]
- router (FastAPI APIRouter)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, status
from myrm_agent_harness.toolkits.memory import (
    GrowthDiaryEntry,
    LifeMilestone,
    LifeStageEra,
    MilestoneCategory,
    PrivacyIntimacyLevel,
    ValueSystemNode,
)

from app.schemas.life_milestones import (
    ContextProjectionResponseDTO,
    DiaryResponseDTO,
    EraResponseDTO,
    EvolveValueRequest,
    LifeMilestonesStatsResponse,
    MilestoneResponseDTO,
    ProjectContextRequest,
    RecordDiaryRequest,
    RecordMilestoneRequest,
    RegisterEraRequest,
    RegisterValueRequest,
    RetrospectiveCardResponseDTO,
    ValueResponseDTO,
)
from app.services.memory.life_milestones.provider import (
    get_life_milestones_suite,
)

router = APIRouter(prefix="/life-milestones", tags=["Life Milestones & Personal Timeline"])


def _to_milestone_dto(m: LifeMilestone) -> MilestoneResponseDTO:
    return MilestoneResponseDTO(
        milestone_id=m.milestone_id,
        timestamp_str=m.timestamp_str,
        year=m.year,
        category=m.category.value,
        title=m.title,
        narrative=m.narrative,
        long_term_impact=m.long_term_impact,
        core_values=list(m.core_values),
        intimacy_level=m.intimacy_level.value,
        significance_score=m.significance_score,
        location=m.location,
    )


@router.post("/milestone", response_model=MilestoneResponseDTO, status_code=status.HTTP_201_CREATED)
async def record_milestone(req: RecordMilestoneRequest) -> MilestoneResponseDTO:
    """Record and evaluate a macro life milestone."""
    suite = get_life_milestones_suite()
    ms_id = req.milestone_id or f"ms_{uuid.uuid4().hex[:8]}"

    try:
        cat = MilestoneCategory(req.category)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown milestone category '{req.category}'",
        ) from None

    try:
        intimacy = PrivacyIntimacyLevel(req.intimacy_level)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown privacy intimacy level '{req.intimacy_level}'",
        ) from None

    milestone = LifeMilestone(
        milestone_id=ms_id,
        timestamp_str=req.timestamp_str,
        year=req.year,
        category=cat,
        title=req.title,
        narrative=req.narrative,
        long_term_impact=req.long_term_impact,
        core_values=req.core_values,
        intimacy_level=intimacy,
        significance_score=req.significance_score,
        location=req.location,
    )

    admitted, reason = suite.record_milestone(milestone, is_user_explicit=req.is_user_explicit)
    if not admitted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Milestone rejected by significance gate: {reason}",
        )

    return _to_milestone_dto(milestone)


@router.get("/milestone/{milestone_id}", response_model=MilestoneResponseDTO)
async def get_milestone(milestone_id: str) -> MilestoneResponseDTO:
    """Retrieve a specific life milestone by ID."""
    suite = get_life_milestones_suite()
    m = suite.get_milestone(milestone_id)
    if m is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Milestone not found")
    return _to_milestone_dto(m)


@router.delete("/milestone/{milestone_id}", status_code=status.HTTP_200_OK)
async def delete_milestone(milestone_id: str) -> dict[str, str | bool]:
    """Remove a life milestone by ID."""
    suite = get_life_milestones_suite()
    deleted = suite.delete_milestone(milestone_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Milestone not found")
    return {"success": True, "milestone_id": milestone_id}


@router.get("/timeline", response_model=list[MilestoneResponseDTO])
async def get_timeline(
    category: str | None = Query(default=None, description="Optional category filter"),
    max_intimacy: str = Query(default="open_overview", description="Privacy boundary"),
    start_year: int | None = Query(default=None, ge=1900, le=2100),
    end_year: int | None = Query(default=None, ge=1900, le=2100),
) -> list[MilestoneResponseDTO]:
    """Retrieve chronologically ordered milestones matching boundaries."""
    suite = get_life_milestones_suite()

    cat_enum = None
    if category:
        try:
            cat_enum = MilestoneCategory(category)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown category '{category}'",
            ) from None

    try:
        intimacy_enum = PrivacyIntimacyLevel(max_intimacy)
    except ValueError:
        intimacy_enum = PrivacyIntimacyLevel.OPEN_OVERVIEW

    milestones = suite.list_milestones(
        category=cat_enum,
        max_intimacy=intimacy_enum,
        start_year=start_year,
        end_year=end_year,
    )
    return [_to_milestone_dto(m) for m in milestones]


@router.post("/era", response_model=EraResponseDTO, status_code=status.HTTP_201_CREATED)
async def register_era(req: RegisterEraRequest) -> EraResponseDTO:
    """Register a lifecycle era segment."""
    suite = get_life_milestones_suite()
    era = LifeStageEra(
        era_id=req.era_id,
        label=req.label,
        start_year=req.start_year,
        end_year=req.end_year,
        guiding_philosophy=req.guiding_philosophy,
    )
    suite.register_era(era)
    return EraResponseDTO(
        era_id=era.era_id,
        label=era.label,
        start_year=era.start_year,
        end_year=era.end_year,
        guiding_philosophy=era.guiding_philosophy,
    )


@router.get("/eras", response_model=list[EraResponseDTO])
async def list_eras() -> list[EraResponseDTO]:
    """List all registered lifecycle era segments."""
    suite = get_life_milestones_suite()
    return [
        EraResponseDTO(
            era_id=e.era_id,
            label=e.label,
            start_year=e.start_year,
            end_year=e.end_year,
            guiding_philosophy=e.guiding_philosophy,
        )
        for e in suite.list_eras()
    ]


@router.post("/value-node", response_model=ValueResponseDTO, status_code=status.HTTP_201_CREATED)
async def register_value_node(req: RegisterValueRequest) -> ValueResponseDTO:
    """Register a guiding value belief."""
    suite = get_life_milestones_suite()
    val_id = req.value_id or f"val_{uuid.uuid4().hex[:8]}"
    node = ValueSystemNode(
        value_id=val_id,
        theme=req.theme,
        current_stance=req.current_stance,
        prior_belief=req.prior_belief,
        transition_catalyst=req.transition_catalyst,
        trigger_milestone_ids=req.trigger_milestone_ids,
        effective_since_year=req.effective_since_year,
        is_active=True,
        weight=req.weight,
    )
    suite.register_value(node)
    return ValueResponseDTO(
        value_id=node.value_id,
        theme=node.theme,
        current_stance=node.current_stance,
        prior_belief=node.prior_belief,
        transition_catalyst=node.transition_catalyst,
        trigger_milestone_ids=list(node.trigger_milestone_ids),
        effective_since_year=node.effective_since_year,
        is_active=node.is_active,
        weight=node.weight,
    )


@router.post("/value-node/evolve", response_model=ValueResponseDTO)
async def evolve_value_node(req: EvolveValueRequest) -> ValueResponseDTO:
    """Evolve an existing value stance into a new belief with causal trace."""
    suite = get_life_milestones_suite()
    new_id = req.new_value_id or f"val_{uuid.uuid4().hex[:8]}"
    new_node = ValueSystemNode(
        value_id=new_id,
        theme=req.theme,
        current_stance=req.new_stance,
        transition_catalyst=req.transition_catalyst,
        trigger_milestone_ids=req.trigger_milestone_ids,
        effective_since_year=req.effective_since_year,
        is_active=True,
        weight=1.2,
    )
    suite.evolve_value(new_node, prior_node_id=req.prior_value_id)
    return ValueResponseDTO(
        value_id=new_node.value_id,
        theme=new_node.theme,
        current_stance=new_node.current_stance,
        prior_belief=new_node.prior_belief,
        transition_catalyst=new_node.transition_catalyst,
        trigger_milestone_ids=list(new_node.trigger_milestone_ids),
        effective_since_year=new_node.effective_since_year,
        is_active=new_node.is_active,
        weight=new_node.weight,
    )


@router.get("/values/active", response_model=list[ValueResponseDTO])
async def list_active_values() -> list[ValueResponseDTO]:
    """List all currently active value beliefs."""
    suite = get_life_milestones_suite()
    return [
        ValueResponseDTO(
            value_id=v.value_id,
            theme=v.theme,
            current_stance=v.current_stance,
            prior_belief=v.prior_belief,
            transition_catalyst=v.transition_catalyst,
            trigger_milestone_ids=list(v.trigger_milestone_ids),
            effective_since_year=v.effective_since_year,
            is_active=v.is_active,
            weight=v.weight,
        )
        for v in suite.list_active_values()
    ]


@router.post("/diary", response_model=DiaryResponseDTO, status_code=status.HTTP_201_CREATED)
async def record_diary_entry(req: RecordDiaryRequest) -> DiaryResponseDTO:
    """Record a personal growth reflection diary entry."""
    suite = get_life_milestones_suite()
    entry_id = req.entry_id or f"diary_{uuid.uuid4().hex[:8]}"
    entry = GrowthDiaryEntry(
        entry_id=entry_id,
        timestamp=datetime.now(timezone.utc),
        emotional_state=req.emotional_state,
        reflection_text=req.reflection_text,
        linked_milestone_id=req.linked_milestone_id,
        era_label=req.era_label,
    )
    suite.record_diary(entry)
    return DiaryResponseDTO(
        entry_id=entry.entry_id,
        timestamp=entry.timestamp.isoformat(),
        emotional_state=entry.emotional_state,
        reflection_text=entry.reflection_text,
        linked_milestone_id=entry.linked_milestone_id,
        era_label=entry.era_label,
    )


@router.get("/diaries", response_model=list[DiaryResponseDTO])
async def list_diaries(
    era_label: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[DiaryResponseDTO]:
    """List growth reflection diaries chronologically descending."""
    suite = get_life_milestones_suite()
    diaries = suite.list_diaries(era_label=era_label, limit=limit)
    return [
        DiaryResponseDTO(
            entry_id=d.entry_id,
            timestamp=d.timestamp.isoformat(),
            emotional_state=d.emotional_state,
            reflection_text=d.reflection_text,
            linked_milestone_id=d.linked_milestone_id,
            era_label=d.era_label,
        )
        for d in diaries
    ]


@router.post("/project-context", response_model=ContextProjectionResponseDTO)
async def project_context(req: ProjectContextRequest) -> ContextProjectionResponseDTO:
    """Produce an empathetic context projection for a user query."""
    suite = get_life_milestones_suite()
    try:
        intimacy = PrivacyIntimacyLevel(req.max_intimacy)
    except ValueError:
        intimacy = PrivacyIntimacyLevel.INTIMATE_PERSONAL

    bundle = suite.project_context(
        query_text=req.query_text,
        max_intimacy=intimacy,
        force_projection=req.force_projection,
    )
    return ContextProjectionResponseDTO(
        projected_text=bundle.projected_text,
        relevant_milestone_count=bundle.relevant_milestone_count,
        active_values=list(bundle.active_values),
        applied_intimacy_level=bundle.applied_intimacy_level.value,
    )


@router.get("/retrospective-card", response_model=RetrospectiveCardResponseDTO)
async def get_retrospective_card(
    era_label: str = Query(description="Era or stage label"),
    start_year: int | None = Query(default=None, ge=1900, le=2100),
    end_year: int | None = Query(default=None, ge=1900, le=2100),
) -> RetrospectiveCardResponseDTO:
    """Generate a reflective retrospective card for a lifecycle era."""
    suite = get_life_milestones_suite()
    card = suite.generate_retrospective_card(
        era_label=era_label,
        start_year=start_year,
        end_year=end_year,
    )
    return RetrospectiveCardResponseDTO(
        era_label=card.era_label,
        time_span=card.time_span,
        milestone_highlights=list(card.milestone_highlights),
        dominant_values=list(card.dominant_values),
        growth_reflections=list(card.growth_reflections),
        companion_empathy_note=card.companion_empathy_note,
    )


@router.get("/stats", response_model=LifeMilestonesStatsResponse)
async def get_stats() -> LifeMilestonesStatsResponse:
    """Retrieve statistical counters for personal memory assets."""
    suite = get_life_milestones_suite()
    stats = suite.get_stats()
    return LifeMilestonesStatsResponse(
        total_milestones=stats["total_milestones"],
        total_eras=stats["total_eras"],
        active_values=stats["active_values"],
        total_diaries=stats["total_diaries"],
    )
