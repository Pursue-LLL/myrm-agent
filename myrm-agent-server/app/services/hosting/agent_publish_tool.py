"""Agent-facing artifact publish tool — bridges Agent to hosting orchestrator.

[INPUT]
- app.core.artifacts::LocalArtifactProcessor (POS: registers a workspace file as an artifact, as a chat run does)
- app.services.hosting.orchestrator::publish_artifact_to_target (POS: publication workflow)
- app.services.hosting.targets::get_default_hosting_target (POS: default target lookup)
- app.services.hosting.credentials::migrate_legacy_vercel_credentials (POS: default Vercel target of a tenant with Vercel access)
- myrm_agent_harness.toolkits.code_execution.executors.base::get_executor (POS: workspace of the running session)

[OUTPUT]
- create_artifact_publish_tool: deferred LangChain tool factory

[POS]
Conditional business tool that lets the Agent publish a workspace file to user-configured hosting targets
(Vercel / Webhook). The file is named by its workspace path and must lie inside the workspace; it is registered as
an artifact of the chat (one artifact per file, so publishing it again updates the same page) and goes through the
orchestrator the GUI Globe publish flow uses.
Registered by tool_setup._setup_artifact_publish_tool when the user has somewhere to publish (a hosting target,
a legacy Vercel token or the operator's platform Vercel token).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import cast

from langchain.tools import tool
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_ARTIFACT_PUBLISH_DESCRIPTION = (
    "Publish a file from the workspace (HTML application, PDF document, Excel spreadsheet, Markdown report, etc.) to the user's configured hosting target "
    "(Vercel or HTTP Webhook) and return the live URL. "
    "The stylesheets, scripts and images a page links to in its folder are published with it. "
    "Pass the workspace path of the file, for example the path you wrote. "
    "Only use when the user explicitly asks to publish, deploy, or get a live link."
)


class ArtifactPublishInput(BaseModel):
    """Input schema for artifact_publish tool."""

    path: str = Field(
        ...,
        description="Workspace path of the file to publish (for example site/index.html).",
    )
    hosting_target_id: str = Field(
        default="",
        description="Optional hosting target ID. Leave empty to use the user's default target.",
    )
    password: str = Field(
        default="",
        description=(
            "Optional password to protect the published artifact. Provide this only when "
            "the user explicitly asks to password-protect, encrypt, or lock access to the deployment. "
            "Leave empty for public access."
        ),
    )


class _Rejected(Exception):
    """The call cannot go ahead; the message is what the model is told, ``reason`` is what the log records."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


def _outside_workspace() -> _Rejected:
    return _Rejected("outside_workspace", "Only files inside the workspace can be published.")


async def _resolve_target_id(requested: str) -> str:
    from app.database.connection import get_session
    from app.services.hosting.credentials import migrate_legacy_vercel_credentials
    from app.services.hosting.targets import get_default_hosting_target

    async with get_session() as db:
        # The settings screen runs this before it lists targets; a tenant that only has Vercel access
        # gets its default target here too, without opening the screen first.
        await migrate_legacy_vercel_credentials(db)
        if requested:
            return requested
        default_target = await get_default_hosting_target(db)
    if default_target is None:
        raise _Rejected("no_target", "No hosting target configured. Please add a hosting target in Settings → Hosting first.")
    return default_target.id


async def _workspace_file(path: str) -> tuple[Path, Path]:
    """The workspace of the running session and the file that *path* names inside it."""
    from myrm_agent_harness.toolkits.code_execution.executors.base import get_executor

    if not path.strip():
        raise _Rejected("empty_path", "path is required.")
    executor = get_executor()
    if executor is None:
        raise _Rejected("no_workspace", "No workspace is available in this session.")
    try:
        file = Path(await executor.resolve_path(path.strip()))
    except (ValueError, OSError):
        raise _outside_workspace() from None
    workspace = Path(executor.workspace_path).resolve()
    # resolve_path also lets through directories the user granted access to; a published file is a workspace file.
    if not file.is_relative_to(workspace):
        raise _outside_workspace()
    if not file.is_file():
        raise _Rejected("not_a_file", f"No file at that path in the workspace: {path.strip()}")
    return workspace, file


async def _register_artifact(chat_id: str, file: Path) -> str:
    """Register *file* as an artifact of the chat exactly as a run's artifact event does; returns the artifact id."""
    from app.core.artifacts import LocalArtifactProcessor

    event: dict[str, object] = {"type": "artifacts_ready", "data": [{"filename": file.name, "path": str(file)}]}
    emitted = await LocalArtifactProcessor(chat_id=chat_id).process_artifacts_ready(event)
    if emitted is None:
        raise _Rejected("not_publishable", f"This file cannot be published: {file.name}")
    return str(cast(list[dict[str, object]], emitted["data"])[0]["id"])


def create_artifact_publish_tool(chat_id: str) -> BaseTool:
    """Create artifact_publish tool that publishes a workspace file of *chat_id* at execution time."""

    @tool(
        "artifact_publish",
        description=_ARTIFACT_PUBLISH_DESCRIPTION,
        args_schema=ArtifactPublishInput,
    )
    async def artifact_publish_func(
        path: str,
        hosting_target_id: str = "",
        password: str = "",
    ) -> dict[str, object]:
        from app.database.connection import get_session
        from app.services.hosting.orchestrator import publish_artifact_to_target

        try:
            target_id = await _resolve_target_id(hosting_target_id.strip())
            workspace, file = await _workspace_file(path)
            artifact_id = await _register_artifact(chat_id, file)
        except _Rejected as rejected:
            logger.info("artifact_publish: outcome=rejected reason=%s", rejected.reason)
            return {"content": str(rejected), "metadata": {"error": True, "path": path}}

        async with get_session() as db:
            result = await publish_artifact_to_target(
                db,
                artifact_id,
                str(workspace),
                hosting_target_id=target_id,
                password=password.strip(),
            )

        if not result.success:
            logger.warning(
                "artifact_publish: outcome=failed artifact=%s target=%s status=%s", artifact_id, target_id, result.status
            )
            return {
                "content": f"Publication failed: {result.error or result.status}",
                "metadata": {"error": True, "artifact_id": artifact_id, "path": path, "status": result.status},
            }

        logger.info("artifact_publish: outcome=published artifact=%s target=%s", artifact_id, target_id)
        return {
            "content": f"Published successfully! Live URL: {result.url}",
            "metadata": {
                "artifact_id": artifact_id,
                "path": path,
                "url": result.url,
                "status": result.status,
                "hosting_target_id": target_id,
            },
        }

    return artifact_publish_func
