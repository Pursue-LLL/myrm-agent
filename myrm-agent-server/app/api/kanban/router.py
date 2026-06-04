"""Kanban REST API — aggregates route modules on a single router."""

from app.api.kanban.http_common import router

from app.api.kanban.routes import boards, bulk, specify, task_meta, tasks  # noqa: F401

__all__ = ["router"]
