"""[INPUT]
- pydantic::BaseModel (POS: schema base)

[OUTPUT]
- UsageSummary, UsageByDay, UsageByJob, UsageByModel, UsageStatsResponse

[POS]
Cron API schemas: cron usage statistics.
"""

from __future__ import annotations

from pydantic import BaseModel


class UsageSummary(BaseModel):
    total_runs: int
    success_runs: int
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    avg_tokens_per_run: int
    estimated_hours_saved: float = 0.0
    roi_multiple: float = 0.0
    estimated_value_saved_cents: float = 0.0
    estimated_cost_cents: float = 0.0


class UsageByDay(BaseModel):
    date: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    runs: int


class UsageByJob(BaseModel):
    job_id: str
    job_name: str
    total_tokens: int
    runs: int
    hours_saved: float = 0.0


class UsageByModel(BaseModel):
    model: str
    total_tokens: int
    runs: int


class UsageStatsResponse(BaseModel):
    summary: UsageSummary
    by_day: list[UsageByDay]
    by_job: list[UsageByJob]
    by_model: list[UsageByModel]
