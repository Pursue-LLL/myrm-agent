"""Pipeline template subpackage — deterministic pipeline instantiation.

[POS]
Pipeline 子域。spec_io 为 SKILL.md frontmatter 解析与模板元数据 I/O；
instantiator 为确定性模板实例化（零 LLM 调用）。
"""

from app.services.kanban.pipeline.instantiator import (
    get_pipeline_skill,
    instantiate_pipeline,
    list_pipeline_skills,
)
from app.services.kanban.pipeline.spec_io import (
    MAX_REPEAT,
    SEEDS_DIR,
    InstantiateResult,
    PipelineQuestion,
    PipelineQuestionGroup,
    PipelineSpec,
    RoleTemplate,
    TaskGraphVariant,
    TaskSeed,
)

__all__ = [
    "InstantiateResult",
    "MAX_REPEAT",
    "PipelineQuestion",
    "PipelineQuestionGroup",
    "PipelineSpec",
    "RoleTemplate",
    "SEEDS_DIR",
    "TaskGraphVariant",
    "TaskSeed",
    "get_pipeline_skill",
    "instantiate_pipeline",
    "list_pipeline_skills",
]
