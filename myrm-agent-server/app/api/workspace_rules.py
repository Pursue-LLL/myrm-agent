"""Workspace rules introspection API.

Provides a read-only endpoint for the frontend to display which
project-level rule files are currently loaded by the agent framework.

GET /api/v1/workspace/rules — returns list of discovered rule files
with their source, path, truncation status, and character count.
"""

import logging

from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()


class WorkspaceRuleItem(BaseModel):
    path: str
    source: str
    char_count: int
    truncated: bool


class WorkspaceRulesResponse(BaseModel):
    rules: list[WorkspaceRuleItem]
    total_chars: int
    workspace_root: str


@router.get("/workspace/rules", tags=["workspace"])
async def get_workspace_rules() -> WorkspaceRulesResponse:
    """Return currently discovered workspace rule files.

    Scans the active workspace root for project-level rule files
    (AGENTS.md, CLAUDE.md, .cursorrules, .myrm/rules/*.md, .cursor/rules/*.mdc)
    and returns metadata about each.
    """
    from myrm_agent_harness.agent.workspace_rules.scanner import (
        scan_workspace_rules,
    )

    from app.api.dependencies import get_workspace_root

    workspace_path = get_workspace_root()
    workspace_root = str(workspace_path)
    if not workspace_root:
        return WorkspaceRulesResponse(rules=[], total_chars=0, workspace_root="")

    rules = scan_workspace_rules(workspace_root)
    items = [
        WorkspaceRuleItem(
            path=rule.path,
            source=rule.source,
            char_count=len(rule.content),
            truncated=rule.truncated,
        )
        for rule in rules
    ]
    total_chars = sum(item.char_count for item in items)

    return WorkspaceRulesResponse(
        rules=items,
        total_chars=total_chars,
        workspace_root=workspace_root,
    )
