"""[INPUT]
- pydantic BaseModel / Field (POS: 请求/响应模型基类)

[OUTPUT]
DiagnosticActionResponse, TaskDiagnosticResponse, DiagnosticSummaryResponse, TaskDiagnosticsResponse

[POS]
Kanban task diagnostics schemas. Diagnostic rule hits and the summary embedded in TaskResponse.
"""

from __future__ import annotations

from pydantic import BaseModel


class DiagnosticActionResponse(BaseModel):
    kind: str
    label: str
    payload: dict[str, str] = {}
    suggested: bool = False


class TaskDiagnosticResponse(BaseModel):
    rule_id: str
    severity: str
    title: str
    detail: str
    actions: list[DiagnosticActionResponse] = []


class DiagnosticSummaryResponse(BaseModel):
    """Lightweight summary embedded in TaskResponse for card badges."""

    count: int = 0
    max_severity: str | None = None


class TaskDiagnosticsResponse(BaseModel):
    """Full diagnostics for a single task (drawer-level)."""

    task_id: str
    diagnostics: list[TaskDiagnosticResponse] = []
