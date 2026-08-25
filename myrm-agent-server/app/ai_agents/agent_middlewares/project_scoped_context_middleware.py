"""Project Scoped Workspace Context Injection Middleware.

[INPUT] agent context["project_dir"] or context["active_project_root"]
[OUTPUT] SystemMessage with <project_scoped_workspace> block injected into conversation
[POS] 项目作用域工作区上下文注入中间件。向 Agent 注入当前工作目录/子项目根路径及代码探索最佳实践（优先使用 ast_symbol_search_tool / 精准增量编辑）。

Injection position:
```
[0] SystemMessage: system prompt
[1] SystemMessage: <user_instructions>
[2] SystemMessage: <project_scoped_workspace>   ← THIS MIDDLEWARE
[3] SystemMessage: <project_roadmap>
[4] SystemMessage: <user_memory_context>
[5] HumanMessage: user message
```

Respects idempotency: once injected, never repeats.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import BaseMessage, SystemMessage

logger = logging.getLogger(__name__)

PROJECT_SCOPED_WORKSPACE_MARKER = "<project_scoped_workspace"


def _has_scoped_workspace_injected(messages: Sequence[BaseMessage]) -> bool:
    for msg in messages[:10]:
        if isinstance(msg, SystemMessage):
            content = msg.content
            if isinstance(content, str) and PROJECT_SCOPED_WORKSPACE_MARKER in content:
                return True
    return False


def _build_scoped_workspace_snippet(project_dir: str) -> str:
    """Build a compact project-scoped workspace directive (~50-80 tokens)."""
    clean_dir = project_dir.strip().rstrip("/") or "."
    return (
        f'<{PROJECT_SCOPED_WORKSPACE_MARKER} path="{clean_dir}">\n'
        f"Active Project Scope: '{clean_dir}'\n"
        "Guidelines:\n"
        "- Base relative file operations and code searches within this scoped directory.\n"
        "- Prefer using ast_symbol_search_tool for outline and symbol definitions before reading entire files.\n"
        "- Make precise incremental file modifications rather than rewriting large source files.\n"
        "</project_scoped_workspace>"
    )


def _find_system_insert_idx(messages: Sequence[BaseMessage]) -> int:
    """Find insertion index right after user_instructions if present, else after system prompt."""
    insert_idx = 0
    for i, msg in enumerate(messages):
        if isinstance(msg, SystemMessage):
            content = str(msg.content)
            if "<user_instructions" in content:
                return i + 1
            insert_idx = i + 1
    return insert_idx


class ProjectScopedWorkspaceMiddleware(AgentMiddleware):
    """Injects project-scoped workspace boundaries into LLM context."""

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        context = getattr(request, "context", {}) or {}
        project_dir = context.get("project_dir") or context.get("active_project_root") or context.get("workspace_dir")

        if not project_dir or _has_scoped_workspace_injected(request.messages):
            return await handler(request)

        snippet = _build_scoped_workspace_snippet(str(project_dir))
        insert_idx = _find_system_insert_idx(request.messages)
        new_messages = list(request.messages)
        new_messages.insert(insert_idx, SystemMessage(content=snippet))

        return await handler(request.override(messages=new_messages))


project_scoped_workspace_middleware = ProjectScopedWorkspaceMiddleware()
