"""Attach the folder a viewer picked on the new-task screen to the turn it starts.

[INPUT]
- app.services.agent.params::AgentRequest (POS: workspace_dir one-shot bind)
- app.services.chat.chat_service::ChatService (POS: chat.workspace_dir persistence)
- app.services.workspace.workspace_path_policy::resolve_workspace_path (POS: workspace path gate)

[OUTPUT]
- TurnWorkspaceRefused: the requested folder cannot be a workspace, with the policy issue attached
- bind_turn_workspace: canonical path this turn runs in, or None when the request's folder is not used

[POS]
Runs before the user row is persisted, so a refused folder ends the turn without leaving a message
behind. The web client sends the folder it shows with every message, so the request's folder counts
only while nothing else owns the chat's workspace; a project or a folder the chat already stores
decides instead, and the request's copy is dropped unjudged: a stored folder that has since vanished
or become too broad must not block the chat. Changing a stored folder stays the job of
PATCH /chats/{id}/workspace.
"""

from __future__ import annotations

from app.services.agent.params import AgentRequest
from app.services.workspace.workspace_path_policy import (
    WorkspacePathIssue,
    WorkspacePathValidationError,
    resolve_workspace_path,
)


class TurnWorkspaceRefused(Exception):
    """A first-turn workspace bind that the path policy refuses."""

    def __init__(self, issue: WorkspacePathIssue, detail: str) -> None:
        super().__init__(detail)
        self.issue = issue
        self.detail = detail


async def bind_turn_workspace(request: AgentRequest) -> str | None:
    """Validate the requested folder when this turn will run in it, and store it on a chat that has none.

    Afterwards ``request.workspace_dir`` is the canonical path or None. A chat that is not persisted
    yet has no row to update, so the lazy session draft stores the path together with the chat row.
    """
    requested = request.workspace_dir
    if not requested:
        return None
    if request.resume_value is not None:
        # The turn that asked for approval already bound its folder.
        request.workspace_dir = None
        return None

    from app.services.chat.chat_service import ChatService

    chat = await ChatService.get_chat_metadata(request.chat_id) if request.chat_id else None
    if chat is not None and (chat.project_id or chat.workspace_dir):
        request.workspace_dir = None
        return None

    try:
        resolved = resolve_workspace_path(requested, require_directory=True)
    except WorkspacePathValidationError as exc:
        raise TurnWorkspaceRefused(exc.issue, str(exc)) from exc

    request.workspace_dir = resolved
    if chat is not None:
        await ChatService.update_chat_fields(chat.id, {"workspace_dir": resolved})
    return resolved
