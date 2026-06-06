"""Pipeline template instantiator.

[INPUT]
- assets/prebuilt_skills/*/SKILL.md (POS: Pipeline-type prebuilt skill seeds with pipeline_spec frontmatter.)
- app.services.kanban::KanbanService (POS: Kanban business orchestration.)

[OUTPUT]
- list_pipeline_skills(): Discover all pipeline templates from prebuilt seeds.
- get_pipeline_skill(skill_id): Load a specific pipeline template.
- instantiate_pipeline(): Create a Kanban task DAG from a template + user answers.

[POS]
Deterministic pipeline template instantiation service. Parses pipeline_spec from
SKILL.md frontmatter, performs string template substitution, and batch-creates
tasks with dependency edges. Zero LLM calls.
"""

from __future__ import annotations

import importlib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from myrm_agent_harness.toolkits.kanban.types import TaskPriority

logger = logging.getLogger(__name__)

SEEDS_DIR = Path(__file__).resolve().parents[3] / "assets" / "prebuilt_skills"


@dataclass(frozen=True, slots=True)
class PipelineQuestion:
    """A single discovery question for pipeline wizard."""

    id: str
    type: str
    label: str
    options: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class PipelineQuestionGroup:
    """Grouped discovery questions."""

    group: str
    group_label: str
    questions: list[PipelineQuestion]


@dataclass(frozen=True, slots=True)
class RoleTemplate:
    """Role archetype within a pipeline."""

    role_id: str
    description: str
    required_skills: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class TaskSeed:
    """A single task node in the pipeline graph template."""

    title_template: str
    description_template: str
    role: str
    parents: list[int] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class TaskGraphVariant:
    """A variant of the task graph."""

    id: str
    label: str
    description: str
    seeds: list[TaskSeed]


@dataclass(frozen=True, slots=True)
class PipelineSpec:
    """Full pipeline specification parsed from SKILL.md frontmatter."""

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
    """Result of pipeline instantiation."""

    task_ids: list[str]
    edges: list[tuple[str, str]]  # (parent_task_id, child_task_id)
    role_agent_mapping: dict[str, str | None]


def _parse_pipeline_spec(skill_id: str, frontmatter: dict[str, object]) -> PipelineSpec | None:
    """Parse pipeline_spec from SKILL.md frontmatter dict."""
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
        if not isinstance(s_raw, dict):
            continue
        seeds.append(
            TaskSeed(
                title_template=str(s_raw.get("title_template", "")),
                description_template=str(s_raw.get("description_template", "")),
                role=str(s_raw.get("role", "")),
                parents=[int(p) for p in s_raw.get("parents", []) if isinstance(p, (int, float))],
            )
        )

    variants_raw = raw_spec.get("task_graph_variants", [])
    variants: list[TaskGraphVariant] = []
    for v_raw in variants_raw:
        if not isinstance(v_raw, dict):
            continue
        v_seeds_raw = v_raw.get("seeds", [])
        v_seeds: list[TaskSeed] = []
        for s_raw in v_seeds_raw:
            if not isinstance(s_raw, dict):
                continue
            v_seeds.append(
                TaskSeed(
                    title_template=str(s_raw.get("title_template", "")),
                    description_template=str(s_raw.get("description_template", "")),
                    role=str(s_raw.get("role", "")),
                    parents=[int(p) for p in s_raw.get("parents", []) if isinstance(p, (int, float))],
                )
            )
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


def _load_frontmatter(skill_md_path: Path) -> dict[str, object] | None:
    """Load and parse YAML frontmatter from a SKILL.md file."""
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


def list_pipeline_skills() -> list[PipelineSpec]:
    """Discover all pipeline-type skills from prebuilt seeds directory."""
    results: list[PipelineSpec] = []
    if not SEEDS_DIR.is_dir():
        return results

    for skill_dir in sorted(SEEDS_DIR.iterdir()):
        if not skill_dir.is_dir() or skill_dir.name.startswith(("_", ".")):
            continue
        skill_md_path = skill_dir / "SKILL.md"
        frontmatter = _load_frontmatter(skill_md_path)
        if frontmatter is None:
            continue
        if frontmatter.get("category") != "pipeline":
            continue
        spec = _parse_pipeline_spec(skill_dir.name, frontmatter)
        if spec and spec.task_graph_seed:
            results.append(spec)

    return results


def get_pipeline_skill(skill_id: str) -> PipelineSpec | None:
    """Load a specific pipeline skill by ID."""
    skill_dir = SEEDS_DIR / skill_id
    skill_md_path = skill_dir / "SKILL.md"
    frontmatter = _load_frontmatter(skill_md_path)
    if frontmatter is None:
        return None
    if frontmatter.get("category") != "pipeline":
        return None
    return _parse_pipeline_spec(skill_id, frontmatter)


def _substitute_template(template: str, answers: dict[str, str]) -> str:
    """Deterministic string template substitution using Python format_map.

    Gracefully handles missing keys by leaving them as-is.
    """

    class SafeDict(dict):
        def __missing__(self, key: str) -> str:
            return f"{{{key}}}"

    try:
        return template.format_map(SafeDict(answers))
    except (KeyError, ValueError, IndexError):
        return template


def _match_role_to_agent(
    role: RoleTemplate,
    agents: list[dict[str, object]],
    default_agent_id: str | None,
) -> str | None:
    """Match a role template to the best available agent by required_skills overlap.

    Returns agent_id or default_agent_id if no match found.
    """
    if not agents:
        return default_agent_id

    best_agent_id: str | None = default_agent_id
    best_score = 0

    for agent in agents:
        agent_skill_ids: list[str] = []
        raw_skills = agent.get("skill_ids") or agent.get("skills") or []
        if isinstance(raw_skills, list):
            agent_skill_ids = [str(s) for s in raw_skills]

        overlap = len(set(role.required_skills) & set(agent_skill_ids))
        if overlap > best_score:
            best_score = overlap
            best_agent_id = str(agent.get("id", "")) or default_agent_id

    return best_agent_id


async def instantiate_pipeline(
    board_id: str,
    skill_id: str,
    answers: dict[str, str],
    agents: list[dict[str, object]] | None = None,
    default_agent_id: str | None = None,
    variant_id: str | None = None,
) -> InstantiateResult:
    """Instantiate a pipeline template into a Kanban task graph.

    1. Load pipeline_spec from the skill
    2. Substitute user answers into task templates
    3. Match roles to agents
    4. Batch-create tasks and dependency edges via KanbanService
    """
    from app.services.kanban import KanbanService

    spec = get_pipeline_skill(skill_id)
    if spec is None:
        raise ValueError(f"Pipeline skill not found: {skill_id}")

    svc = KanbanService.get_instance()
    board = await svc.get_board(board_id)
    if board is None:
        raise ValueError(f"Board not found: {board_id}")

    role_agent_map: dict[str, str | None] = {}
    for role in spec.role_templates:
        role_agent_map[role.role_id] = _match_role_to_agent(
            role,
            agents or [],
            default_agent_id,
        )

    seeds_to_use = None
    if variant_id:
        if spec.task_graph_variants:
            for variant in spec.task_graph_variants:
                if variant.id == variant_id:
                    seeds_to_use = variant.seeds
                    break
        if seeds_to_use is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail=f"Invalid variant_id: {variant_id}")
    else:
        seeds_to_use = spec.task_graph_seed
        if not seeds_to_use and spec.task_graph_variants:
            seeds_to_use = spec.task_graph_variants[0].seeds
            
    if not seeds_to_use:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="No tasks defined in the selected variant or default seed")

    created_task_ids: list[str] = []
    created_edges: list[tuple[str, str]] = []

    for seed in seeds_to_use:
        title = _substitute_template(seed.title_template, answers)
        description = _substitute_template(seed.description_template, answers)
        agent_id = role_agent_map.get(seed.role)

        parent_task_ids: list[str] = []
        for parent_idx in seed.parents:
            if 0 <= parent_idx < len(created_task_ids):
                parent_task_ids.append(created_task_ids[parent_idx])

        task = await svc.add_task(
            board_id=board_id,
            title=title,
            description=description,
            priority=TaskPriority.NORMAL,
            agent_id=agent_id,
            depends_on=parent_task_ids or None,
        )
        created_task_ids.append(task.task_id)

        for parent_id in parent_task_ids:
            created_edges.append((parent_id, task.task_id))

    return InstantiateResult(
        task_ids=created_task_ids,
        edges=created_edges,
        role_agent_mapping=role_agent_map,
    )
