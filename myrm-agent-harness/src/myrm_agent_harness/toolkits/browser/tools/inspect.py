"""browser_inspect tool for quick page structure analysis.

[INPUT]
- common::mark_untrusted (POS: unified browser output security boundary; credential redaction + untrusted-content wrapping)

[OUTPUT]
- create_inspect_tool: Create browser_inspect tool bound to session.

[POS]
browser_inspect tool for quick page structure analysis.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from langchain.tools import tool
from pydantic import BaseModel

from .common import mark_untrusted

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

    from ..session import BrowserSession


def create_inspect_tool(session: BrowserSession) -> BaseTool:
    """Create browser_inspect tool bound to session."""

    class InspectInput(BaseModel):
        pass  # No parameters needed

    @tool("browser_inspect_tool", args_schema=InspectInput)
    async def browser_inspect() -> str:
        """Analyze page structure quickly without capturing full ARIA tree.

        Returns structured metadata:
        - Total interactive elements count
        - Key semantic regions (<main>, <article>, <form>, etc.)
        - Recommended CSS selector for scoped browser_snapshot_tool calls

        Use this on unknown or large pages before browser_snapshot_tool to select the optimal 'selector'.
        """
        return mark_untrusted(await session.inspect())

    return browser_inspect
