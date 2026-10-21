"""Workspace rules introspection API.

@input: app.api.dependencies::get_workspace_root (POS: 当前 workspace 根路径解析)
@input: myrm_agent_harness.agent.workspace_rules.scanner::scan_workspace_rules (POS: 规则文件扫描)
@output: GET /api/v1/workspace/rules — 已发现规则文件的 path/source/char_count/truncated/content
@pos: Workspace 规则自省 HTTP 层，供 Settings WorkspaceRulesSection 展示和内容预览
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
    content: str


class WorkspaceRulesResponse(BaseModel):
    rules: list[WorkspaceRuleItem]
    total_chars: int
    workspace_root: str


@router.get("/rules", tags=["workspace"])
async def get_workspace_rules() -> WorkspaceRulesResponse:
    """Return currently discovered workspace rule files.

    Scans the active workspace root for project-level rule files
    (AGENTS.md, CLAUDE.md, .myrm/rules/*.md, .cursor/rules/*.mdc)
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
            content=rule.content,
        )
        for rule in rules
    ]
    total_chars = sum(item.char_count for item in items)

    return WorkspaceRulesResponse(
        rules=items,
        total_chars=total_chars,
        workspace_root=workspace_root,
    )
