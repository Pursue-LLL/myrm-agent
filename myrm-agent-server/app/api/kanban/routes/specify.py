"""Kanban API routes — specify."""

from __future__ import annotations

from fastapi import HTTPException, Query

from app.api.kanban.http_common import (
    get_kanban_service,
    router,
)
from app.api.kanban.schemas import (
    ApplyDecomposeRequest,
    ApplySpecRequest,
    DecomposeChildResponse,
    DecomposeOutcomeResponse,
    SpecifyAllResponse,
    SpecifyOutcomeResponse,
)

# ---------------------------------------------------------------------------
# Specify (TRIAGE → spec rewrite) endpoints
# ---------------------------------------------------------------------------


def _outcome_to_response(outcome: object) -> SpecifyOutcomeResponse:
    """Map a harness SpecifyOutcome dataclass to the API DTO."""
    return SpecifyOutcomeResponse(
        task_id=getattr(outcome, "task_id", ""),
        ok=bool(getattr(outcome, "ok", False)),
        reason=str(getattr(outcome, "reason", "")),
        new_title=getattr(outcome, "new_title", None),
        new_body=getattr(outcome, "new_body", None),
        prompt_tokens=getattr(outcome, "prompt_tokens", None),
        completion_tokens=getattr(outcome, "completion_tokens", None),
        persisted=bool(getattr(outcome, "persisted", False)),
    )


@router.post(
    "/tasks/{task_id}/specify",
    response_model=SpecifyOutcomeResponse,
)
async def specify_task(
    task_id: str,
    dry_run: bool = Query(True, description="True returns a preview without persisting."),
) -> SpecifyOutcomeResponse:
    """Run the TaskSpecifier on a single TRIAGE task.

    dry_run=True returns a preview SpecifyOutcome (UI Apply/Reject loop).
    dry_run=False persists the spec, emits SPECIFIED event, and promotes
    TRIAGE → READY (or BACKLOG when dependencies are unmet).
    """
    svc = get_kanban_service()
    task = await svc.get_task(task_id)
    if task is None:
        raise HTTPException(404, f"Task {task_id} not found")
    outcome = await svc.specify_task(task_id, persist=not dry_run)
    return _outcome_to_response(outcome)


@router.post(
    "/tasks/{task_id}/apply-spec",
    response_model=SpecifyOutcomeResponse,
)
async def apply_spec(
    task_id: str,
    body: ApplySpecRequest,
) -> SpecifyOutcomeResponse:
    """Persist a previously-previewed spec without re-invoking the LLM.

    The frontend calls this after the user reviews a dry-run preview and
    clicks "Apply & Promote". The cached new_title / new_body from the
    preview are sent in the request body so the LLM is never called twice.
    """
    svc = get_kanban_service()
    task = await svc.get_task(task_id)
    if task is None:
        raise HTTPException(404, f"Task {task_id} not found")
    outcome = await svc.apply_spec(
        task_id,
        new_title=body.new_title,
        new_body=body.new_body,
        prompt_tokens=body.prompt_tokens,
        completion_tokens=body.completion_tokens,
    )
    return _outcome_to_response(outcome)


@router.post(
    "/boards/{board_id}/specify-all",
    response_model=SpecifyAllResponse,
)
async def specify_all_triage(
    board_id: str,
    dry_run: bool = Query(True, description="True returns previews without persisting."),
) -> SpecifyAllResponse:
    """Run the TaskSpecifier on every TRIAGE task of a board concurrently.

    Bounded concurrency (3 in-flight LLM calls) prevents stampedes.
    Failures are reported per-task; the sweep never aborts on a single
    failure.
    """
    svc = get_kanban_service()
    board = await svc.get_board(board_id)
    if board is None:
        raise HTTPException(404, f"Board {board_id} not found")

    outcomes = await svc.specify_all_triage(board_id, persist=not dry_run)
    return SpecifyAllResponse(
        items=[_outcome_to_response(o) for o in outcomes],
        total=len(outcomes),
        persisted=not dry_run,
    )


# ---------------------------------------------------------------------------
# Decompose (TRIAGE → child task graph) endpoints
# ---------------------------------------------------------------------------


def _decompose_to_response(outcome: object) -> DecomposeOutcomeResponse:
    """Map a harness DecomposeOutcome dataclass to the API DTO."""
    children_raw = getattr(outcome, "children", ()) or ()
    return DecomposeOutcomeResponse(
        task_id=getattr(outcome, "task_id", ""),
        ok=bool(getattr(outcome, "ok", False)),
        fanout=bool(getattr(outcome, "fanout", False)),
        children=[
            DecomposeChildResponse(
                title=c.title,
                body=c.body,
                assignee=c.assignee,
                parent_indices=list(c.parent_indices),
                extra_skill_ids=list(getattr(c, "extra_skill_ids", ())),
            )
            for c in children_raw
        ],
        rationale=str(getattr(outcome, "rationale", "")),
        reason=str(getattr(outcome, "reason", "")),
        new_title=getattr(outcome, "new_title", None),
        new_body=getattr(outcome, "new_body", None),
        new_assignee=getattr(outcome, "new_assignee", None),
        child_ids=list(getattr(outcome, "child_ids", ()) or ()),
        prompt_tokens=getattr(outcome, "prompt_tokens", None),
        completion_tokens=getattr(outcome, "completion_tokens", None),
        persisted=bool(getattr(outcome, "persisted", False)),
    )


@router.post(
    "/tasks/{task_id}/decompose",
    response_model=DecomposeOutcomeResponse,
)
async def decompose_task(task_id: str) -> DecomposeOutcomeResponse:
    """Preview a decomposition for a TRIAGE task (always dry-run).

    Returns the LLM-proposed child task graph for the user to review
    in the DecomposeDialog. The user then calls apply-decompose to persist.
    """
    svc = get_kanban_service()
    task = await svc.get_task(task_id)
    if task is None:
        raise HTTPException(404, f"Task {task_id} not found")
    outcome = await svc.decompose_task(task_id)
    return _decompose_to_response(outcome)


@router.post(
    "/tasks/{task_id}/apply-decompose",
    response_model=DecomposeOutcomeResponse,
)
async def apply_decompose(
    task_id: str,
    body: ApplyDecomposeRequest,
) -> DecomposeOutcomeResponse:
    """Persist a previously-previewed decomposition.

    When ``fanout=true``, creates child tasks atomically and promotes
    root TRIAGE → BACKLOG.
    When ``fanout=false``, applies the tightened title/body/assignee
    to the task and promotes TRIAGE → READY (Specify fallback).
    """
    svc = get_kanban_service()
    task = await svc.get_task(task_id)
    if task is None:
        raise HTTPException(404, f"Task {task_id} not found")

    if not body.fanout:
        outcome = await svc.apply_no_fanout(
            task_id,
            new_title=body.new_title,
            new_body=body.new_body,
            new_assignee=body.new_assignee,
            rationale=body.rationale,
            prompt_tokens=body.prompt_tokens,
            completion_tokens=body.completion_tokens,
        )
        return _decompose_to_response(outcome)

    from myrm_agent_harness.toolkits.kanban.protocols import DecomposeChildSpec

    children = [
        DecomposeChildSpec(
            title=c.title,
            body=c.body,
            assignee=c.assignee,
            parent_indices=tuple(c.parent_indices),
            extra_skill_ids=tuple(c.extra_skill_ids),
        )
        for c in body.children
    ]

    outcome = await svc.apply_decompose(
        task_id,
        children=children,
        rationale=body.rationale,
        prompt_tokens=body.prompt_tokens,
        completion_tokens=body.completion_tokens,
    )
    return _decompose_to_response(outcome)
