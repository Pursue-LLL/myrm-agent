"""Pipeline template instantiator.

[INPUT]
- pipeline.spec_io (POS: Pipeline SKILL.md types and frontmatter parsing.)
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

from typing import TYPE_CHECKING

from fastapi import HTTPException
from myrm_agent_harness.toolkits.kanban.types import TaskPriority, inherit_source_chat_metadata

if TYPE_CHECKING:
    from app.services.kanban import KanbanService

from app.services.kanban.pipeline.spec_io import (
    MAX_REPEAT,
    SEEDS_DIR,
    InstantiateResult,
    PipelineSpec,
    RoleTemplate,
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


async def _resolve_inherited_metadata(
    svc: KanbanService,
    parent_task_ids: list[str],
) -> dict[str, object] | None:
    """Copy source_chat_id from the first parent task that has one."""
    for parent_id in parent_task_ids:
        parent = await svc.get_task(parent_id)
        if parent is None:
            continue
        patch = inherit_source_chat_metadata(parent.metadata)
        if patch is not None:
            return patch
    return None


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
        role.role_id: _match_role_to_agent(role, agents or [], default_agent_id) for role in spec.role_templates
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
        metadata_patch = await _resolve_inherited_metadata(svc, parent_task_ids)

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
                per_item_skills = seed.repeat_for_item_skills.get(item, [])
                task = await svc.add_task(
                    board_id=board_id,
                    title=title,
                    description=description,
                    priority=TaskPriority.NORMAL,
                    agent_id=agent_id,
                    depends_on=parent_task_ids or None,
                    extra_skill_ids=per_item_skills or None,
                    metadata_patch=metadata_patch,
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
                metadata_patch=metadata_patch,
            )
            created_task_ids.append(task.task_id)
            seed_index_to_task_ids[seed_idx] = [task.task_id]
            created_edges.extend((parent_id, task.task_id) for parent_id in parent_task_ids)

    return InstantiateResult(
        task_ids=created_task_ids,
        edges=created_edges,
        role_agent_mapping=role_agent_map,
    )


def estimate_pipeline_plan(
    skill_id: str,
    answers: dict[str, str],
    variant_id: str | None = None,
    user_tier: str = "standard",
) -> dict[str, object]:
    """Calculate pre-run task DAG expansion, token scale, and WU estimation for a pipeline."""
    spec = get_pipeline_skill(skill_id)
    if spec is None:
        raise ValueError(f"Pipeline skill not found: {skill_id}")

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
        raise HTTPException(status_code=400, detail="No tasks defined in template")

    total_tasks = 0
    max_fan_out = 1
    has_fan_out = False
    all_required_skills: set[str] = set()

    for role in spec.role_templates:
        all_required_skills.update(role.required_skills)

    for seed in seeds_to_use:
        if seed.repeat_for:
            has_fan_out = True
            items = _split_repeat_items(answers.get(seed.repeat_for, ""))
            count = len(items) if items else 1
            total_tasks += count
            if count > max_fan_out:
                max_fan_out = count
        else:
            total_tasks += 1

    # Base token heuristics: 1500 prompt tokens + 800 completion tokens per task
    avg_prompt = 1500
    avg_completion = 800
    total_prompt_tokens = total_tasks * avg_prompt
    total_completion_tokens = total_tasks * avg_completion

    # Heuristic WU computation (aligned with burn_table)
    tier_mult = 10.0 if user_tier == "frontier" else (1.0 if user_tier == "lite" else 3.0)
    base_per_task_wu = (10 + (avg_prompt * 0.001 * tier_mult) + (avg_completion * 0.003 * tier_mult) + (3.0 * 5.0) + (len(all_required_skills) * 2))
    base_total_wu = max(1, int(base_per_task_wu * total_tasks))
    min_wu = max(1, int(base_total_wu * 0.75))
    max_wu = max(min_wu, int(base_total_wu * 1.35))

    tier_mismatch_warning = (user_tier == "frontier" and total_tasks <= 5 and len(all_required_skills) <= 2)
    recommended_tier = "standard" if tier_mismatch_warning else user_tier

    return {
        "task_count": total_tasks,
        "skill_count": len(all_required_skills),
        "estimated_prompt_tokens": total_prompt_tokens,
        "estimated_completion_tokens": total_completion_tokens,
        "min_estimated_wu": min_wu,
        "max_estimated_wu": max_wu,
        "base_estimated_wu": base_total_wu,
        "recommended_tier": recommended_tier,
        "tier_mismatch_warning": tier_mismatch_warning,
        "is_fan_out": has_fan_out,
        "fan_out_factor": max_fan_out,
    }

