"""Request and response bodies of the goal HTTP API.

[INPUT]
- pydantic::BaseModel (POS: request/response validation)

[OUTPUT]
- GoalStatusUpdateRequest, GoalDraftRequest, GoalDraftResponse, GoalBudgetUpdateRequest, SubgoalAddRequest: bodies of the goal status, draft, budget and subgoal endpoints

[POS]
Wire shapes of `router.py`, kept apart so the endpoint module holds only behaviour.
"""

from pydantic import BaseModel


class GoalStatusUpdateRequest(BaseModel):
    action: str  # "pause", "resume", "cancel", "approve", "reject", "wait", "unwait"
    note: str | None = None
    wait_reason: str | None = None


class GoalDraftRequest(BaseModel):
    objective: str
    locale: str | None = None


class GoalDraftResponse(BaseModel):
    constraints: list[str]
    acceptance_criteria: list[dict[str, object]]
    ui_summary: str


class GoalBudgetUpdateRequest(BaseModel):
    additional_tokens: int


class SubgoalAddRequest(BaseModel):
    text: str
