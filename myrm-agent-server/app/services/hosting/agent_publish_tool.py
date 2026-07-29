"""Agent-facing artifact publish tool — bridges Agent to hosting orchestrator.

[INPUT]
- app.services.hosting.orchestrator::publish_artifact_to_target (POS: publication workflow)
- app.services.hosting.targets::get_default_hosting_target (POS: default target lookup)
- app.platform_utils.workspace_root::get_workspace_root (POS: workspace root path resolution)

[OUTPUT]
- create_artifact_publish_tool: deferred LangChain tool factory

[POS]
Conditional business tool that lets the Agent publish HTML artifacts to
user-configured hosting targets (Vercel / Cloudflare Pages / Netlify / Webhook).
Registered by tool_setup._setup_artifact_publish_tool when at least one hosting
target is configured. Uses the same orchestrator as the GUI Globe publish flow.
"""

from __future__ import annotations

from typing import Any

from langchain.tools import tool
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

_ARTIFACT_PUBLISH_DESCRIPTION = (
    "Publish a generated HTML artifact to the user's configured hosting target "
    "(Vercel, Cloudflare Pages, Netlify, or HTTP Webhook) and return the live URL. "
    "Requires artifact_id from a previously generated artifact in this conversation. "
    "Only use when the user explicitly asks to publish, deploy, or get a live link."
)


class ArtifactPublishInput(BaseModel):
    """Input schema for artifact_publish tool."""

    artifact_id: str = Field(
        ...,
        description="ID of the artifact to publish (from a previously generated artifact).",
    )
    hosting_target_id: str = Field(
        default="",
        description=(
            "Optional hosting target ID. Leave empty to use the user's default target."
        ),
    )


def create_artifact_publish_tool() -> BaseTool:
    """Create artifact_publish tool that publishes artifacts at execution time."""

    @tool(
        "artifact_publish",
        description=_ARTIFACT_PUBLISH_DESCRIPTION,
        args_schema=ArtifactPublishInput,
    )
    async def artifact_publish_func(
        artifact_id: str,
        hosting_target_id: str = "",
    ) -> dict[str, Any]:
        from app.database.connection import get_session
        from app.services.hosting.orchestrator import publish_artifact_to_target
        from app.services.hosting.targets import get_default_hosting_target

        async with get_session() as db:
            target_id = hosting_target_id.strip()
            if not target_id:
                default_target = await get_default_hosting_target(db)
                if default_target is None:
                    return {
                        "content": (
                            "No hosting target configured. "
                            "Please add a hosting target in Settings → Hosting first."
                        ),
                        "metadata": {"error": True, "artifact_id": artifact_id},
                    }
                target_id = default_target.id

            from app.platform_utils.workspace_root import get_workspace_root

            workspace_root = str(get_workspace_root())
            result = await publish_artifact_to_target(
                db,
                artifact_id,
                workspace_root,
                hosting_target_id=target_id,
            )

            if not result.success:
                return {
                    "content": f"Publication failed: {result.error or result.status}",
                    "metadata": {
                        "error": True,
                        "artifact_id": artifact_id,
                        "status": result.status,
                    },
                }

            return {
                "content": f"Published successfully! Live URL: {result.url}",
                "metadata": {
                    "artifact_id": artifact_id,
                    "url": result.url,
                    "status": result.status,
                    "hosting_target_id": target_id,
                },
            }

    return artifact_publish_func
