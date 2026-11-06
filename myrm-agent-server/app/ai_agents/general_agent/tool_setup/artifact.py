"""Artifact 发布工具。

[POS]
ToolSetupMixin 的一个工具族；由 mixin.py 组合。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .base import ToolSetupBaseMixin

if TYPE_CHECKING:

    pass

logger = logging.getLogger(__name__)


class ArtifactToolsMixin(ToolSetupBaseMixin):
    """Artifact 发布工具。"""

    async def _setup_artifact_publish_tool(self, tools: list[object]) -> None:
        """Register artifact_publish tool when hosting targets are configured.

        Conditional loading: only mounted when the user has at least one
        hosting target, keeping zero prompt-token overhead for unconfigured users.
        """
        try:
            from app.services.hosting.credentials import has_any_hosting_credentials

            if not await has_any_hosting_credentials():
                return

            from app.services.hosting.agent_publish_tool import (
                create_artifact_publish_tool,
            )

            tools.append(create_artifact_publish_tool())
            logger.info("Loaded artifact_publish tool [conditional, hosting configured]")
        except Exception as e:
            logger.debug("artifact_publish tool skipped: %s", e)
