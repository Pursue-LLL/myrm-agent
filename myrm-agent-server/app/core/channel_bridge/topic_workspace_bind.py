"""Topic workspace binding validation helpers.

[INPUT]
- app.services.project.project_service::ProjectService
- app.services.workspace.file_watch_service::resolve_watchable_workspace_path

[OUTPUT]
- assert_project_workspace: validate project vault exists
- validate_authorized_path: normalize and validate host path

[POS]
SqlTopicManager workspace bind sidecar — keeps topic_config.py focused on config CRUD.
"""

from __future__ import annotations


async def assert_project_workspace(project_id: str) -> None:
    from app.services.project.project_service import ProjectService

    project = await ProjectService.get_project(project_id)
    if project is None:
        raise ValueError(f"Project not found: {project_id}")
    if not project.workspace_path:
        raise ValueError(f"Project has no workspace path: {project_id}")


def validate_authorized_path(raw_path: str) -> str:
    from app.services.workspace.file_watch_service import resolve_watchable_workspace_path

    return resolve_watchable_workspace_path(raw_path)
