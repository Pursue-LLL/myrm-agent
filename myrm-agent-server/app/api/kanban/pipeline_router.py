"""Pipeline Template REST API endpoints.

[INPUT]
- app.services.kanban.pipeline_instantiator (POS: Deterministic pipeline template instantiation service.)
- .schemas (POS: Pydantic request/response models for pipeline templates.)

[OUTPUT]
- GET /pipelines: List available pipeline templates.
- GET /pipelines/{skill_id}: Get pipeline template detail.
- POST /boards/{board_id}/pipeline/instantiate: Instantiate a pipeline into task graph.

[POS]
Pipeline template REST API endpoints for Kanban.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.kanban.schemas import (
    PipelineInstantiateRequest,
    PipelineInstantiateResponse,
    PipelineQuestionGroupResponse,
    PipelineQuestionResponse,
    PipelineRoleResponse,
    PipelineTaskSeedResponse,
    PipelineTemplateDetailResponse,
    PipelineTemplateListResponse,
    PipelineTemplateResponse,
)

pipeline_router = APIRouter(prefix="/kanban", tags=["kanban-pipelines"])


@pipeline_router.get("/pipelines", response_model=PipelineTemplateListResponse)
async def list_pipelines() -> PipelineTemplateListResponse:
    """List available pipeline templates (category=pipeline prebuilt skills)."""
    from app.services.kanban.pipeline_instantiator import list_pipeline_skills

    specs = list_pipeline_skills()
    items = [
        PipelineTemplateResponse(
            skill_id=spec.skill_id,
            name=spec.name,
            description=spec.description,
            category=spec.category,
            tags=spec.tags,
            task_count=len(spec.task_graph_seed),
            roles=[r.role_id for r in spec.role_templates],
        )
        for spec in specs
    ]
    return PipelineTemplateListResponse(items=items, total=len(items))


@pipeline_router.get("/pipelines/{skill_id}", response_model=PipelineTemplateDetailResponse)
async def get_pipeline(skill_id: str) -> PipelineTemplateDetailResponse:
    """Get full pipeline template detail including discovery questions."""
    from app.services.kanban.pipeline_instantiator import get_pipeline_skill

    spec = get_pipeline_skill(skill_id)
    if spec is None:
        raise HTTPException(404, f"Pipeline template not found: {skill_id}")

    return PipelineTemplateDetailResponse(
        skill_id=spec.skill_id,
        name=spec.name,
        description=spec.description,
        category=spec.category,
        tags=spec.tags,
        discovery_questions=[
            PipelineQuestionGroupResponse(
                group=g.group,
                group_label=g.group_label,
                questions=[
                    PipelineQuestionResponse(id=q.id, type=q.type, label=q.label, options=q.options)
                    for q in g.questions
                ],
            )
            for g in spec.discovery_questions
        ],
        role_templates=[
            PipelineRoleResponse(
                role_id=r.role_id,
                description=r.description,
                required_skills=r.required_skills,
            )
            for r in spec.role_templates
        ],
        task_graph_seed=[
            PipelineTaskSeedResponse(
                title_template=s.title_template,
                description_template=s.description_template,
                role=s.role,
                parents=s.parents,
            )
            for s in spec.task_graph_seed
        ],
    )


@pipeline_router.post(
    "/boards/{board_id}/pipeline/instantiate",
    response_model=PipelineInstantiateResponse,
    status_code=201,
)
async def instantiate_pipeline(
    board_id: str,
    body: PipelineInstantiateRequest,
) -> PipelineInstantiateResponse:
    """Instantiate a pipeline template into a Kanban task graph."""
    from app.services.kanban.pipeline_instantiator import (
        instantiate_pipeline as do_instantiate,
    )

    try:
        result = await do_instantiate(
            board_id=board_id,
            skill_id=body.skill_id,
            answers=body.answers,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    return PipelineInstantiateResponse(
        task_ids=result.task_ids,
        edges=[[parent, child] for parent, child in result.edges],
        role_agent_mapping=result.role_agent_mapping,
    )
