"""Pipeline template instantiator.

[INPUT]
- pipeline_spec_io (POS: Pipeline SKILL.md types and frontmatter parsing.)
- app.services.kanban::KanbanService (POS: Kanban business orchestration.)

[OUTPUT]
- list_pipeline_skills(): Discover all pipeline templates from prebuilt seeds.
- get_pipeline_skill(skill_id): Load a specific pipeline template.
- instantiate_pipeline(): Create a Kanban task DAG from a template + user answers.

[POS]
Deterministic pipeline template instantiation service. Supports repeat_for
fan-out (one seed → N parallel tasks from multi-select answers). Zero LLM calls.
"""

from __future__ import annotations

from fastapi import HTTPException
from myrm_agent_harness.toolkits.kanban.types import TaskPriority

from app.services.kanban.pipeline_spec_io import (
    MAX_REPEAT,
    SEEDS_DIR,
    InstantiateResult,
    PipelineQuestion,
    PipelineQuestionGroup,
    PipelineSpec,
    RoleTemplate,
    TaskGraphVariant,
    TaskSeed,
    _parse_pipeline_spec,
    load_skill_frontmatter,
)

_load_frontmatter = load_skill_frontmatter


def list_pipeline_skills() -> list[PipelineSpec]:
    results: list[PipelineSpec] = []
    if not SEEDS_DIR.is_dir():
        return results

    for skill_dir in sorted(SEEDS_DIR.iterdir()):
        if not skill_dir.is_dir() or skill_dir.name.startswith(("_", ".")):
            continue
        frontmatter = load_skill_frontmatter(skill_dir / "SKILL.md")
        if frontmatter is None or frontmatter.get("category") != "pipeline":
            continue
        spec = _parse_pipeline_spec(skill_dir.name, frontmatter)
        if spec and spec.task_graph_seed:
            results.append(spec)

    return results


def get_pipeline_skill(skill_id: str) -> PipelineSpec | None:
    frontmatter = load_skill_frontmatter(SEEDS_DIR / skill_id / "SKILL.md")
    if frontmatter is None or frontmatter.get("category") != "pipeline":
        return None
    return _parse_pipeline_spec(skill_id, frontmatter)


def _substitute_template(template: str, answers: dict[str, str]) -> str:
    class SafeDict(dict[str, str]):
        def __missing__(self, key: str) -> str:
            return f"{{{key}}}"

    try:
        return template.format_map(SafeDict(answers))
    except (KeyError, ValueError, IndexError):
        return template


def _split_repeat_items(raw_answer: str) -> list[str]:
    return [item.strip() for item in raw_answer.split(",") if item.strip()]


def _match_role_to_agent(
    role: RoleTemplate,
    agents: list[dict[str, object]],
    default_agent_id: str | None,
) -> str | None:
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
    from app.services.kanban import KanbanService

    spec = get_pipeline_skill(skill_id)
    if spec is None:
        raise ValueError(f"Pipeline skill not found: {skill_id}")

    svc = KanbanService.get_instance()
    board = await svc.get_board(board_id)
    if board is None:
        raise ValueError(f"Board not found: {board_id}")

    role_agent_map: dict[str, str | None] = {
        role.role_id: _match_role_to_agent(role, agents or [], default_agent_id)
        for role in spec.role_templates
    }

    seeds_to_use: list[TaskSeed] | None = None
    if variant_id:
        if spec.task_graph_variants:
            for variant in spec.task_graph_variants:
                if variant.id == variant_id:
                    seeds_to_use = variant.seeds
                    break
        if seeds_to_use is None:
            raise HTTPException(status_code=400, detail=f"Invalid variant_id: {variant_id}")
    else:
        seeds_to_use = spec.task_graph_seed
        if not seeds_to_use and spec.task_graph_variants:
            seeds_to_use = spec.task_graph_variants[0].seeds

    if not seeds_to_use:
        raise HTTPException(status_code=400, detail="No tasks defined in the selected variant or default seed")

    created_task_ids: list[str] = []
    created_edges: list[tuple[str, str]] = []
    seed_index_to_task_ids: dict[int, list[str]] = {}

    for seed_idx, seed in enumerate(seeds_to_use):
        parent_task_ids: list[str] = []
        for parent_idx in seed.parents:
            parent_task_ids.extend(seed_index_to_task_ids.get(parent_idx, []))

        agent_id = role_agent_map.get(seed.role)

        if seed.repeat_for:
            items = _split_repeat_items(answers.get(seed.repeat_for, ""))
            if not items:
                raise HTTPException(
                    status_code=400,
                    detail=f"repeat_for question '{seed.repeat_for}' requires at least one selection",
                )
            if len(items) > MAX_REPEAT:
                raise HTTPException(
                    status_code=400,
                    detail=f"repeat_for exceeds limit ({len(items)} > {MAX_REPEAT})",
                )
            ids_for_seed: list[str] = []
            for item in items:
                per_item_answers = {**answers, "_item": item}
                title = _substitute_template(seed.title_template, per_item_answers)
                description = _substitute_template(seed.description_template, per_item_answers)
                task = await svc.add_task(
                    board_id=board_id,
                    title=title,
                    description=description,
                    priority=TaskPriority.NORMAL,
                    agent_id=agent_id,
                    depends_on=parent_task_ids or None,
                )
                created_task_ids.append(task.task_id)
                ids_for_seed.append(task.task_id)
                created_edges.extend((parent_id, task.task_id) for parent_id in parent_task_ids)
            seed_index_to_task_ids[seed_idx] = ids_for_seed
        else:
            title = _substitute_template(seed.title_template, answers)
            description = _substitute_template(seed.description_template, answers)
            task = await svc.add_task(
                board_id=board_id,
                title=title,
                description=description,
                priority=TaskPriority.NORMAL,
                agent_id=agent_id,
                depends_on=parent_task_ids or None,
            )
            created_task_ids.append(task.task_id)
            seed_index_to_task_ids[seed_idx] = [task.task_id]
            created_edges.extend((parent_id, task.task_id) for parent_id in parent_task_ids)

    return InstantiateResult(
        task_ids=created_task_ids,
        edges=created_edges,
        role_agent_mapping=role_agent_map,
    )
