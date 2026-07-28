"""Workspace organize plan and job types.

[INPUT]
- pydantic BaseModel (POS: 请求/持久化 schema 基类)

[OUTPUT]
- OrganizePlan / OrganizePlanItem / OrganizeJob / OrganizeApplyResult / OrganizeValidationIssue 类型

[POS]
Workspace organize 领域模型。plan JSON 与 job 持久化结构的单一 SSOT。
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class OrganizePreset(StrEnum):
    DATE = "date"
    EXT = "ext"
    PROJECT = "project"
    CUSTOM = "custom"


class OrganizePlanItem(BaseModel):
    src: str = Field(..., min_length=1, max_length=4096)
    dst: str = Field(..., min_length=1, max_length=4096)
    reason: str = Field(..., min_length=1, max_length=512)
    src_mtime_ns: int | None = Field(
        default=None,
        description="Optional mtime snapshot from plan generation for TOCTOU checks on apply",
    )


class OrganizePlan(BaseModel):
    version: Literal[1] = 1
    scope_root: str = Field(..., min_length=1, max_length=4096)
    preset: OrganizePreset = OrganizePreset.CUSTOM
    items: list[OrganizePlanItem] = Field(default_factory=list)


class OrganizeMoveRecord(BaseModel):
    src: str
    dst: str


class OrganizeJobStatus(StrEnum):
    APPLIED = "applied"
    ROLLED_BACK = "rolled_back"
    PARTIAL_ROLLBACK = "partial_rollback"


class OrganizeJob(BaseModel):
    job_id: str
    workspace: str
    scope_root: str
    status: OrganizeJobStatus
    moves: list[OrganizeMoveRecord]
    created_at: float
    rolled_back_at: float | None = None


class OrganizeValidationIssue(BaseModel):
    index: int
    code: str
    message: str


class OrganizeApplyResult(BaseModel):
    dry_run: bool
    job_id: str | None = None
    job_status: OrganizeJobStatus | None = None
    applied_count: int = 0
    issues: list[OrganizeValidationIssue] = Field(default_factory=list)
    moves: list[OrganizeMoveRecord] = Field(default_factory=list)
