"""Where a channel chat's agent runs.

[INPUT]
- app.services.agent.params.workspace_resolve::default_chat_workspace_path (POS: JIT chat workspace location)

[OUTPUT]
- agent_workspace(): the directory the chat's agent runs in, or None when the chat id cannot name one

[POS]
The one answer to "which directory can a channel agent read back?", for everything that parks a file for the agent
(oversized messages, reference documents). Channel agent params carry no bound workspace, so the agent always runs in the
chat's JIT sandbox, whatever the chat's topic binding says.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


def agent_workspace(chat_id: str) -> Path | None:
    """The chat's JIT workspace directory (pure: nothing is created), or None for an id that cannot name a directory."""
    from app.services.agent.params.workspace_resolve import default_chat_workspace_path

    try:
        return default_chat_workspace_path(chat_id)
    except ValueError:
        logger.warning("Channel chat %s cannot name a workspace directory", chat_id)
        return None
