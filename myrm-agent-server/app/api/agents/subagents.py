"""Subagent REST control plane for chat sessions.

[INPUT]
- services.agent.gateway::get_agent_gateway (POS: active agent session registry for streaming runs)
- services.chat.chat_service::ChatService (POS: workspace dir for teammate mailbox hydrate)
- sub_agents.session_tree::merge_active_subagent_children, cancel_active_children_for_session (POS: ACTIVE_SUBAGENTS registry SSOT)
- sub_agents.checkpoint.saver::SubagentCheckpointStorage (POS: interrupted subagent checkpoint persistence)
- coordination.mailbox::list_teammate_history, group_history_by_task (POS: P2P teammate message history)

[OUTPUT]
GET list / POST cancel-all / POST steer / POST cancel / POST resume for /chats/{chat_id}/subagents

[POS]
Server HTTP facade for Task Tray observability and subagent control; delegates registry merge/cancel to harness session_tree.
"""

import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Body, Path
from fastapi.responses import JSONResponse
from myrm_agent_harness.agent.coordination.mailbox import (
    group_history_by_task,
    list_teammate_history,
)
from myrm_agent_harness.agent.sub_agents.checkpoint.saver import SubagentCheckpointStorage
from myrm_agent_harness.agent.sub_agents.manager import ACTIVE_SUBAGENTS

from app.core.utils.response_utils import error_response, success_response
from app.services.agent.gateway import get_agent_gateway
from app.services.chat.chat_service import ChatService

logger = logging.getLogger(__name__)

router = APIRouter()


async def _merge_teammate_messages_into_children(
    chat_id: str,
    children_data: list[dict[str, object]],
) -> None:
    """Attach persisted teammate mailbox rows onto subagent list entries."""
    if not children_data:
        return

    workspace_dir: str | None = None
    try:
        workspace_dir = await ChatService.ensure_default_workspace_dir(chat_id)
    except Exception:
        logger.exception("Failed to resolve workspace for teammate hydrate: %s", chat_id)

    gateway = get_agent_gateway()
    info = gateway._session_info.get(chat_id)
    if info and info.agent and info.agent() is not None:
        agent = info.agent()
        agent_ws = getattr(agent, "workspace_path", None) or getattr(agent, "workspace_dir", None)
        if isinstance(agent_ws, str) and agent_ws:
            workspace_dir = workspace_dir or agent_ws

    history = list_teammate_history(chat_id, workspace_dir, limit=200)
    if not history:
        return

    grouped = group_history_by_task(history)
    for child in children_data:
        if not isinstance(child, dict):
            continue
        task_id = child.get("task_id")
        if not isinstance(task_id, str) or not task_id:
            continue
        msgs = grouped.get(task_id)
        if msgs:
            child["teammate_messages"] = msgs


@router.get("/{chat_id}/subagents")
async def list_subagents(
    chat_id: Annotated[str, Path(..., description="The chat session ID")],
) -> JSONResponse:
    """Get all active and checkpointed subagents for a given chat session."""
    gateway = get_agent_gateway()
    info = gateway._session_info.get(chat_id)

    children_data: list[dict[str, object]] = []

    gateway_children: list[dict[str, object]] = []
    if info and info.agent and info.agent() is not None:
        agent = info.agent()
        if hasattr(agent, "subagent_manager"):
            gateway_children = agent.subagent_manager.list_children()

    from myrm_agent_harness.agent.sub_agents.session_tree import merge_active_subagent_children

    children_data.extend(merge_active_subagent_children(chat_id, gateway_children))

    storage = SubagentCheckpointStorage()
    try:
        checkpoints = await storage.list_checkpoints(session_id=chat_id)
        active_task_ids = {c.get("task_id") for c in children_data if isinstance(c, dict)}

        for c in checkpoints:
            if c.task_id not in active_task_ids:
                children_data.append(
                    {
                        "task_id": c.task_id,
                        "agent_type": c.agent_type,
                        "status": "checkpoint",
                        "progress": c.progress,
                        "last_tool": c.last_tool,
                        "done": True,
                        "cancelled": True,
                    }
                )
    except Exception:
        logger.exception("Failed to list subagent checkpoints for session %s", chat_id)

    await _merge_teammate_messages_into_children(chat_id, children_data)

    return success_response(data=children_data)


@router.post("/{chat_id}/subagents/cancel-all")
async def cancel_all_subagents(
    chat_id: Annotated[str, Path(..., description="The chat session ID")],
) -> JSONResponse:
    """Cancel all running subagents for the current chat session."""
    from myrm_agent_harness.agent.sub_agents.session_tree import cancel_active_children_for_session

    gateway = get_agent_gateway()
    info = gateway._session_info.get(chat_id)

    cancelled = 0
    if info and info.agent and info.agent() is not None:
        agent = info.agent()
        if hasattr(agent, "cancel_all_children"):
            cancelled += agent.cancel_all_children()

    cancelled += cancel_active_children_for_session(chat_id)
    if cancelled == 0:
        return error_response(
            message=f"No running subagents found for chat session {chat_id}.",
            status_code=404,
        )

    return success_response(data={"cancelled": cancelled, "chat_id": chat_id})


@router.post("/{chat_id}/subagents/delegation/pause")
async def pause_delegation_for_session(
    chat_id: Annotated[str, Path(..., description="The chat session ID")],
) -> JSONResponse:
    """Pause new subagent spawns for this session (in-flight children continue)."""
    from myrm_agent_harness.agent.meta_tools.spawn_subagent.delegation_pause_gate import (
        pause_delegation,
    )

    pause_delegation(chat_id)
    return success_response(data={"paused": True, "chat_id": chat_id})


@router.post("/{chat_id}/subagents/delegation/resume")
async def resume_delegation_for_session(
    chat_id: Annotated[str, Path(..., description="The chat session ID")],
) -> JSONResponse:
    """Resume subagent spawns for this session."""
    from myrm_agent_harness.agent.meta_tools.spawn_subagent.delegation_pause_gate import (
        resume_delegation,
    )

    resume_delegation(chat_id)
    return success_response(data={"paused": False, "chat_id": chat_id})


@router.get("/{chat_id}/subagents/delegation/status")
async def delegation_pause_status(
    chat_id: Annotated[str, Path(..., description="The chat session ID")],
) -> JSONResponse:
    """Return whether delegation is paused for this session."""
    from myrm_agent_harness.agent.meta_tools.spawn_subagent.delegation_pause_gate import (
        delegation_pause_status as gate_status,
    )

    return success_response(data=gate_status(chat_id))


@router.post("/{chat_id}/subagents/{task_id}/steer")
async def steer_subagent(
    chat_id: Annotated[str, Path(..., description="The chat session ID")],
    task_id: Annotated[str, Path(..., description="The subagent task ID")],
    message: Annotated[str, Body(..., embed=True, description="The steering message")],
) -> JSONResponse:
    """Inject a steering message into a running subagent."""
    manager = ACTIVE_SUBAGENTS.get(task_id)
    if not manager:
        return error_response(
            message=f"Subagent {task_id} is not running or not found in memory.",
            status_code=404,
        )

    success = manager.steer_child(task_id, message)
    if not success:
        return error_response(message=f"Failed to steer subagent {task_id}", status_code=400)

    return success_response(data={"steered": True, "task_id": task_id})


@router.post("/{chat_id}/subagents/{task_id}/cancel")
async def cancel_subagent(
    chat_id: Annotated[str, Path(..., description="The chat session ID")],
    task_id: Annotated[str, Path(..., description="The subagent task ID")],
) -> JSONResponse:
    """Cancel a running subagent."""
    manager = ACTIVE_SUBAGENTS.get(task_id)
    if not manager:
        return error_response(
            message=f"Subagent {task_id} is not running or not found in memory.",
            status_code=404,
        )

    success = manager.cancel_child(task_id)
    if not success:
        return error_response(message=f"Failed to cancel subagent {task_id}", status_code=400)

    return success_response(data={"cancelled": True, "task_id": task_id})


@router.post("/{chat_id}/subagents/{task_id}/resume")
async def resume_subagent(
    chat_id: Annotated[str, Path(..., description="The chat session ID")],
    task_id: Annotated[str, Path(..., description="The subagent task ID")],
) -> JSONResponse:
    """Resume a subagent from a checkpoint."""
    gateway = get_agent_gateway()
    info = gateway._session_info.get(chat_id)
    if not info or not info.agent or info.agent() is None:
        return error_response(
            message=f"Session {chat_id} is not currently active.",
            status_code=400,
        )

    agent = info.agent()
    if not hasattr(agent, "subagent_manager"):
        return error_response(
            message=f"Session {chat_id} does not support subagents.",
            status_code=400,
        )

    try:
        asyncio.create_task(agent.subagent_manager.resume_from_checkpoint(task_id))
        return success_response(data={"resumed": True, "task_id": task_id})
    except Exception:
        logger.exception("Failed to resume subagent %s", task_id)
        return error_response(message=f"Failed to resume subagent {task_id}", status_code=500)

