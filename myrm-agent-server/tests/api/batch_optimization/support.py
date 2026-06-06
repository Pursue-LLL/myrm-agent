"""Shared stubs for batch optimization API tests."""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from datetime import datetime, timezone

batch_router_module = importlib.import_module("app.api.batch_optimization.router")


@dataclass(slots=True)
class FakeBatchTask:
    batch_id: str
    max_concurrent: int
    status: str = "running"
    priority: int = 1
    skill_ids: dict[str, list[str]] = field(default_factory=lambda: {"ids": ["skill-a"]})
    total_tasks: int = 1
    completed_tasks: int = 0
    failed_tasks: int = 0
    cancelled_tasks: int = 0
    total_execution_time: float = 0.0
    total_token_consumption: int = 0
    estimated_completion_time: datetime | None = None
    created_at: datetime = datetime(2026, 4, 14, 15, 5, 40, tzinfo=timezone.utc)
    started_at: datetime | None = datetime(2026, 4, 14, 15, 6, 0, tzinfo=timezone.utc)
    completed_at: datetime | None = None
    error_message: str | None = None
    user_id: str | None = "sandbox"


class BatchTaskRepositoryStub:
    def __init__(self, task: FakeBatchTask) -> None:
        self.task = task
        self.status_updates: list[tuple[str, str]] = []

    async def get_by_id(self, batch_id: str) -> FakeBatchTask | None:
        return self.task if batch_id == self.task.batch_id else None

    async def update_status(self, batch_id: str, status: str) -> None:
        self.status_updates.append((batch_id, status))
        self.task.status = status


class AuditLogRepositoryStub:
    def __init__(self) -> None:
        self.logs: list[dict[str, object]] = []

    async def create_log(
        self,
        batch_id: str,
        operation: str,
        status: str,
        details: dict[str, object],
        user_id: str,
    ) -> None:
        self.logs.append(
            {
                "batch_id": batch_id,
                "operation": operation,
                "status": status,
                "details": details,
                "user_id": user_id,
            }
        )
