"""[INPUT]
- pydantic BaseModel / Field (POS: 请求/响应模型基类)

[OUTPUT]
PipelineQuestionResponse, PipelineQuestionGroupResponse, PipelineRoleResponse, PipelineTaskSeedResponse, PipelineTaskGraphVariantResponse, PipelineTemplateResponse, PipelineTemplateDetailResponse, PipelineTemplateListResponse, PipelineInstantiateRequest, PipelineInstantiateResponse, PipelineEstimateRequest, PipelineEstimateResponse

[POS]
Kanban pipeline template schemas. Pipeline discovery questions, graph variants, templates and instantiation.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PipelineQuestionResponse(BaseModel):
    """A single discovery question."""

    id: str
    type: str
    label: str
    options: list[str] = []


class PipelineQuestionGroupResponse(BaseModel):
    """Grouped discovery questions."""

    group: str
    group_label: str
    questions: list[PipelineQuestionResponse]


class PipelineRoleResponse(BaseModel):
    """Role archetype within a pipeline."""

    role_id: str
    description: str
    required_skills: list[str] = []


class PipelineTaskSeedResponse(BaseModel):
    """A single task node in the pipeline graph template."""

    title_template: str
    description_template: str
    role: str
    parents: list[int] = []
    repeat_for: str | None = None


class PipelineTaskGraphVariantResponse(BaseModel):
    """A variant of the task graph."""

    id: str
    label: str
    description: str
    seeds: list[PipelineTaskSeedResponse] = []


class PipelineTemplateResponse(BaseModel):
    """Pipeline template summary for list view."""

    skill_id: str
    name: str
    description: str
    category: str
    tags: list[str] = []
    task_count: int = 0
    roles: list[str] = []


class PipelineTemplateDetailResponse(BaseModel):
    """Full pipeline template with discovery questions and task graph."""

    skill_id: str
    name: str
    description: str
    category: str
    tags: list[str] = []
    discovery_questions: list[PipelineQuestionGroupResponse] = []
    role_templates: list[PipelineRoleResponse] = []
    task_graph_seed: list[PipelineTaskSeedResponse] = []
    task_graph_variants: list[PipelineTaskGraphVariantResponse] = []


class PipelineTemplateListResponse(BaseModel):
    """List of available pipeline templates."""

    items: list[PipelineTemplateResponse]
    total: int


class PipelineInstantiateRequest(BaseModel):
    """Request body for instantiating a pipeline template."""

    skill_id: str = Field(..., min_length=1)
    answers: dict[str, str] = Field(default_factory=dict)
    variant_id: str | None = Field(None, description="Optional variant ID to select a specific task graph.")


class PipelineInstantiateResponse(BaseModel):
    """Result of pipeline instantiation."""

    task_ids: list[str]
    edges: list[list[str]] = []
    role_agent_mapping: dict[str, str | None] = {}


class PipelineEstimateRequest(BaseModel):
    """Request body for pre-run estimation of a pipeline template."""

    skill_id: str = Field(..., min_length=1)
    answers: dict[str, str] = Field(default_factory=dict)
    variant_id: str | None = Field(None)


class PipelineEstimateResponse(BaseModel):
    """Pre-run execution and resource estimate for a pipeline template."""

    task_count: int = Field(ge=1)
    skill_count: int = Field(ge=0)
    estimated_prompt_tokens: int = Field(ge=0)
    estimated_completion_tokens: int = Field(ge=0)
    min_estimated_wu: int = Field(ge=1)
    max_estimated_wu: int = Field(ge=1)
    base_estimated_wu: int = Field(ge=1)
    recommended_tier: str = "standard"
    tier_mismatch_warning: bool = False
    is_fan_out: bool = False
    fan_out_factor: int = Field(default=1, ge=1)
