"""Pipeline spec types and SKILL.md frontmatter parsing.

[INPUT]
- assets/prebuilt_skills/*/SKILL.md (POS: Pipeline-type prebuilt skill seeds.)

[OUTPUT]
- Pipeline dataclasses and _parse_pipeline_spec / _load_frontmatter helpers.

[POS]
I/O layer for pipeline template metadata; no Kanban mutations.
"""

from __future__ import annotations

import importlib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

SEEDS_DIR = Path(__file__).resolve().parents[3] / "assets" / "prebuilt_skills"

MAX_REPEAT: int = 20


@dataclass(frozen=True, slots=True)
class PipelineQuestion:
    id: str
    type: str
    label: str
    options: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class PipelineQuestionGroup:
    group: str
    group_label: str
    questions: list[PipelineQuestion]


@dataclass(frozen=True, slots=True)
class RoleTemplate:
    role_id: str
    description: str
    required_skills: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class TaskSeed:
    title_template: str
    description_template: str
    role: str
    parents: list[int] = field(default_factory=list)
    repeat_for: str | None = None


@dataclass(frozen=True, slots=True)
class TaskGraphVariant:
    id: str
    label: str
    description: str
    seeds: list[TaskSeed]


@dataclass(frozen=True, slots=True)
class PipelineSpec:
    skill_id: str
    name: str
    description: str
    category: str
    tags: list[str]
    discovery_questions: list[PipelineQuestionGroup]
    role_templates: list[RoleTemplate]
    task_graph_seed: list[TaskSeed]
    task_graph_variants: list[TaskGraphVariant] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class InstantiateResult:
    task_ids: list[str]
    edges: list[tuple[str, str]]
    role_agent_mapping: dict[str, str | None]


def _parse_task_seed(raw: dict[str, object]) -> TaskSeed:
    repeat_for_val = raw.get("repeat_for")
    return TaskSeed(
        title_template=str(raw.get("title_template", "")),
        description_template=str(raw.get("description_template", "")),
        role=str(raw.get("role", "")),
        parents=[int(p) for p in raw.get("parents", []) if isinstance(p, (int, float))],
        repeat_for=str(repeat_for_val) if repeat_for_val else None,
    )


def _parse_pipeline_spec(skill_id: str, frontmatter: dict[str, object]) -> PipelineSpec | None:
    raw_spec = frontmatter.get("pipeline_spec")
    if not isinstance(raw_spec, dict):
        return None

    questions_raw = raw_spec.get("discovery_questions", [])
    question_groups: list[PipelineQuestionGroup] = []
    for group_raw in questions_raw:
        if not isinstance(group_raw, dict):
            continue
        qs: list[PipelineQuestion] = []
        for q_raw in group_raw.get("questions", []):
            if not isinstance(q_raw, dict):
                continue
            qs.append(
                PipelineQuestion(
                    id=str(q_raw.get("id", "")),
                    type=str(q_raw.get("type", "text")),
                    label=str(q_raw.get("label", "")),
                    options=[str(o) for o in q_raw.get("options", [])] if q_raw.get("options") else [],
                )
            )
        question_groups.append(
            PipelineQuestionGroup(
                group=str(group_raw.get("group", "")),
                group_label=str(group_raw.get("group_label", "")),
                questions=qs,
            )
        )

    roles_raw = raw_spec.get("role_templates", [])
    roles: list[RoleTemplate] = []
    for r_raw in roles_raw:
        if not isinstance(r_raw, dict):
            continue
        roles.append(
            RoleTemplate(
                role_id=str(r_raw.get("role_id", "")),
                description=str(r_raw.get("description", "")),
                required_skills=[str(s) for s in r_raw.get("required_skills", [])],
            )
        )

    seeds_raw = raw_spec.get("task_graph_seed", [])
    seeds: list[TaskSeed] = []
    for s_raw in seeds_raw:
        if isinstance(s_raw, dict):
            seeds.append(_parse_task_seed(s_raw))

    variants_raw = raw_spec.get("task_graph_variants", [])
    variants: list[TaskGraphVariant] = []
    for v_raw in variants_raw:
        if not isinstance(v_raw, dict):
            continue
        v_seeds = [_parse_task_seed(s_raw) for s_raw in v_raw.get("seeds", []) if isinstance(s_raw, dict)]
        variants.append(
            TaskGraphVariant(
                id=str(v_raw.get("id", "")),
                label=str(v_raw.get("label", "")),
                description=str(v_raw.get("description", "")),
                seeds=v_seeds,
            )
        )

    return PipelineSpec(
        skill_id=skill_id,
        name=str(frontmatter.get("name", skill_id)),
        description=str(frontmatter.get("description", "")),
        category=str(frontmatter.get("category", "")),
        tags=[str(t) for t in frontmatter.get("tags", [])] if frontmatter.get("tags") else [],
        discovery_questions=question_groups,
        role_templates=roles,
        task_graph_seed=seeds,
        task_graph_variants=variants,
    )


def load_skill_frontmatter(skill_md_path: Path) -> dict[str, object] | None:
    if not skill_md_path.is_file():
        return None
    content = skill_md_path.read_text(encoding="utf-8")
    frontmatter_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not frontmatter_match:
        return None
    try:
        yaml_mod = importlib.import_module("yaml")
        data = yaml_mod.safe_load(frontmatter_match.group(1))
        if isinstance(data, dict):
            return {str(k): v for k, v in data.items()}
    except Exception as exc:
        logger.warning("Failed to parse frontmatter for %s: %s", skill_md_path, exc)
    return None
