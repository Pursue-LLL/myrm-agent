"""Project Roadmap context injection middleware.

[INPUT] services.project.milestone_service::MilestoneService.get_project_roadmap_summary
[OUTPUT] SystemMessage with <project_roadmap> block injected into conversation
[POS] 项目路线图上下文注入中间件。自动将项目里程碑信息注入 Agent 对话，帮助 Agent 理解当前项目目标。

Injects project-level roadmap context (milestones, progress, goals) into the
agent conversation as a SystemMessage before memory context.

Injection position:

```
[0] SystemMessage: system prompt
[1] SystemMessage: <user_instructions>
[2] SystemMessage: <workspace_context>
[3] SystemMessage: <project_roadmap>       ← THIS MIDDLEWARE
[4] SystemMessage: <user_memory_context>   ← memory_context_middleware
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

PROJECT_ROADMAP_MARKER = "<project_roadmap"


def _has_roadmap_injected(messages: Sequence[BaseMessage]) -> bool:
    for msg in messages[:10]:
        if isinstance(msg, SystemMessage):
            content = msg.content
            if isinstance(content, str) and PROJECT_ROADMAP_MARKER in content:
                return True
    return False


def _build_roadmap_snippet(roadmap: dict) -> str | None:
    """Build a compact roadmap snippet for context injection (~100-200 tokens)."""
    project_name = roadmap.get("projectName", "")
    description = roadmap.get("projectDescription", "")
    goal_summary = roadmap.get("goalSummary", "")
    active_milestones: list[dict] = roadmap.get("activeMilestones", [])
    completed_milestones: list[dict] = roadmap.get("completedMilestones", [])

    if not project_name:
        return None

    parts: list[str] = [f"Project: {project_name}"]
    if description:
        parts.append(f"Description: {description}")
    if goal_summary:
        parts.append(f"Current Focus: {goal_summary}")

    if active_milestones:
        parts.append("\nActive Milestones:")
        for ms in active_milestones[:5]:
            title = ms.get("title", "")
            criteria = ms.get("acceptanceCriteria", "")
            line = f"  - [{ms.get('status', 'active')}] {title}"
            if criteria:
                line += f" (criteria: {criteria[:80]})"
            parts.append(line)

    if completed_milestones:
        done_titles = [ms.get("title", "") for ms in completed_milestones[-3:]]
        parts.append(f"\nCompleted: {', '.join(done_titles)}")

    return "\n".join(parts)


class ProjectRoadmapMiddleware(AgentMiddleware):  # type: ignore[type-arg]
    """Inject project roadmap context on first LLM call.

    Requires runtime context key: "project_roadmap" (dict from MilestoneService.get_project_roadmap_summary).
    """

    name = "project_roadmap_middleware"

    async def awrap_model_call(
        self, request: ModelRequest, handler: Callable[[ModelRequest], Awaitable[ModelResponse]]
    ) -> ModelResponse:
        state = request.state
        state_messages = state.get("messages", [])

        if _has_roadmap_injected(state_messages) or _has_roadmap_injected(request.messages):
            return await handler(request)

        context = getattr(request.runtime, "context", None) if request.runtime else None
        if not context:
            return await handler(request)

        # Try pre-loaded roadmap first, then lazy-load from project_id
        roadmap: dict | None = context.get("project_roadmap")
        if not roadmap:
            project_id: str | None = context.get("project_id")
            if not project_id:
                return await handler(request)
            try:
                from app.services.project.milestone_service import MilestoneService

                roadmap = await MilestoneService.get_project_roadmap_summary(project_id)
                if roadmap:
                    context["project_roadmap"] = roadmap
            except Exception as e:
                logger.warning("Failed to load project roadmap for %s: %s", project_id, e)
                return await handler(request)

        if not roadmap:
            return await handler(request)

        snippet = _build_roadmap_snippet(roadmap)
        if not snippet:
            return await handler(request)

        roadmap_content = f"""<project_roadmap>
{snippet}

Instructions: You are working within this project. Keep milestone objectives in mind.
When completing tasks, consider how they contribute to active milestones.
</project_roadmap>"""

        roadmap_msg = SystemMessage(content=roadmap_content)
        new_messages = list(request.messages)

        insert_idx = 0
        for i, msg in enumerate(new_messages):
            if isinstance(msg, SystemMessage):
                insert_idx = i + 1
            else:
                break
        new_messages.insert(insert_idx, roadmap_msg)
        state_messages.insert(insert_idx, roadmap_msg)

        logger.info("Project roadmap context injected for project: %s", roadmap.get("projectName"))
        return await handler(request.override(messages=new_messages))


project_roadmap_middleware = ProjectRoadmapMiddleware()
