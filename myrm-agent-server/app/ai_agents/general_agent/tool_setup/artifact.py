"""[INPUT]
- app.ai_agents.general_agent.tool_setup.base::ToolSetupBaseMixin (POS: 各工具族 mixin 共同继承，避免重复声明宿主属性。)

[OUTPUT]
- ArtifactToolsMixin: Artifact 发布工具。

[POS]
ToolSetupMixin 的一个工具族；由 mixin.py 组合。
"""

from __future__ import annotations

import logging

from .base import ToolSetupBaseMixin

logger = logging.getLogger(__name__)


class ArtifactToolsMixin(ToolSetupBaseMixin):
    """Artifact 发布工具。"""

    async def _setup_artifact_publish_tool(self, tools: list[object], chat_id: str) -> None:
        """Register artifact_publish tool when the user has somewhere to publish.

        Conditional loading: only mounted when a hosting target, a legacy Vercel token or the operator's
        platform Vercel token exists, keeping zero prompt-token overhead for everyone else.
        *chat_id* is the chat the published files are registered under; it is the one the run's own artifact
        processor uses, so a file keeps one artifact whichever of the two registers it first.
        """
        try:
            from app.services.hosting.credentials import has_any_hosting_credentials

            if not await has_any_hosting_credentials():
                return

            from app.services.hosting.agent_publish_tool import (
                create_artifact_publish_tool,
            )

            tools.append(create_artifact_publish_tool(chat_id))
            logger.info("Loaded artifact_publish tool [conditional, hosting configured]")
        except Exception as e:
            logger.debug("artifact_publish tool skipped: %s", e)
