"""[INPUT]
- pydantic BaseModel / Field (POS: 请求/响应模型基类)

[OUTPUT]
RaceLaneSpec, RaceStartRequest, RaceEstimateResponse, RaceStartResponse, RaceLaneResponse, RaceLanesResponse, RaceDecideRequest, RaceDecideResponse, RaceFileChange, RaceLaneChangesResponse, RaceLaneFileResponse

[POS]
Kanban race schemas. Race start/estimate/decide bodies and lane comparison responses.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RaceLaneSpec(BaseModel):
    """One race contestant. Unset fields inherit the parent task."""

    agent_id: str | None = Field(None, description="Agent profile for this lane")
    model_override: str | None = Field(None, max_length=255, description="Per-lane LLM model in 'provider/model' form")
    instruction_variant: str = Field("", max_length=5000, description="Extra instructions appended to the lane prompt")
    title_suffix: str = Field("", max_length=50, description="Custom lane label")


class RaceStartRequest(BaseModel):
    """Start a race: fan one task out into parallel lane children."""

    lanes: list[RaceLaneSpec] = Field(..., min_length=2, max_length=5)
    branch: str | None = Field(None, max_length=255, description="Race target branch (defaults to the task branch)")
    confirm_cost: bool = Field(False, description="Must be true after reviewing the cost estimate")


class RaceEstimateResponse(BaseModel):
    """Token cost preview for a planned race."""

    lanes: int
    per_lane_avg_tokens: int
    total_tokens: int
    based_on_completed_tasks: int


class RaceStartResponse(BaseModel):
    """Result of starting a race."""

    parent_task_id: str
    lane_ids: list[str]
    estimate: RaceEstimateResponse


class RaceLaneResponse(BaseModel):
    """One lane of a race with judging-relevant state."""

    task_id: str
    title: str
    status: str
    agent_id: str | None = None
    branch: str | None = None
    result: str = ""
    total_tokens: int = 0


class RaceLanesResponse(BaseModel):
    """All lanes of a race parent."""

    parent_task_id: str
    lanes: list[RaceLaneResponse]


class RaceDecideRequest(BaseModel):
    """Pick the winning lane: merge it, archive the rest."""

    winner_task_id: str = Field(..., min_length=1)
    approver: str | None = Field(None, max_length=100)


class RaceDecideResponse(BaseModel):
    """Result of deciding a race."""

    parent_task_id: str
    winner_task_id: str
    archived_lane_ids: list[str]


class RaceFileChange(BaseModel):
    """One file changed by a lane."""

    path: str
    additions: int
    deletions: int


class RaceLaneChangesResponse(BaseModel):
    """Files changed by a lane against the race target branch."""

    lane_task_id: str
    target_branch: str
    lane_branch: str
    truncated: bool
    files: list[RaceFileChange]


class RaceLaneFileResponse(BaseModel):
    """Target vs lane file contents for side-by-side review."""

    lane_task_id: str
    path: str
    target_content: str
    lane_content: str
    truncated: bool
