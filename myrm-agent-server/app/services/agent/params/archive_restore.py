"""[INPUT]
- app.services.agent.params.models::AgentRequest (POS: General Agent HTTP request DTO)
- app.services.agent.params.workspace_resolve::resolve_default_chat_workspace_dir (POS: chat workspace JIT resolver)
- myrm_agent_harness.runtime.context.archive_restore_action::materialize_archive_restore_action (POS: harness archive restore materializer)

[OUTPUT]
- ArchiveRestoreRequestError, BuiltArchiveRestoreActionContext
- prevalidate_archive_restore_actions(), build/inject archive restore prompt helpers

[POS]
Typed archive restore action validation and prompt materialization for General Agent requests.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.services.agent.params.models import AgentRequest
from app.services.agent.params.workspace_resolve import resolve_default_chat_workspace_dir

logger = logging.getLogger(__name__)

_MAX_ARCHIVE_RESTORE_ACTIONS = 3


class ArchiveRestoreRequestError(ValueError):
    """User-visible typed archive restore action validation failure."""


@dataclass(frozen=True, slots=True)
class BuiltArchiveRestoreActionContext:
    """Materialized archive restore context plus UI-safe result metadata."""

    prompt_context: str
    warnings: list[str]
    results: list[dict[str, object]]


async def build_archive_restore_action_context(
    request: AgentRequest,
    chat_workspace_dir: str | None,
    *,
    record_allowed: bool = True,
) -> tuple[str, list[str]]:
    built = await build_archive_restore_action_context_with_results(
        request,
        chat_workspace_dir,
        record_allowed=record_allowed,
    )
    return built.prompt_context, built.warnings


async def build_archive_restore_action_context_with_results(
    request: AgentRequest,
    chat_workspace_dir: str | None,
    *,
    record_allowed: bool = True,
) -> BuiltArchiveRestoreActionContext:
    if not request.archive_restore_actions:
        return BuiltArchiveRestoreActionContext("", [], [])
    if not request.chat_id or not chat_workspace_dir:
        raise ArchiveRestoreRequestError("Archive restore action requires an initialized chat workspace.")
    if len(request.archive_restore_actions) > _MAX_ARCHIVE_RESTORE_ACTIONS:
        raise ArchiveRestoreRequestError(
            f"Archive restore action accepts at most {_MAX_ARCHIVE_RESTORE_ACTIONS} ranges per request."
        )

    from myrm_agent_harness.runtime.context.archive_restore_action import (
        ArchiveRestoreActionError,
        materialize_archive_restore_action,
    )

    parts: list[str] = []
    results: list[dict[str, object]] = []
    for action in request.archive_restore_actions:
        try:
            restored = await materialize_archive_restore_action(
                workspace_dir=chat_workspace_dir,
                chat_id=request.chat_id,
                restore_arg=action.restore_arg,
                record_allowed=record_allowed,
            )
        except ArchiveRestoreActionError as exc:
            raise ArchiveRestoreRequestError(str(exc)) from exc
        parts.append(restored.render_xml())
        results.append(restored.to_result().to_dict())

    if not parts:
        return BuiltArchiveRestoreActionContext("", [], [])
    return BuiltArchiveRestoreActionContext(
        "\n\n<archive_restore_actions>\n" + "\n".join(parts) + "\n</archive_restore_actions>",
        [],
        results,
    )


def inject_archive_restore_actions_into_query(
    query: object,
    restore_context: str,
) -> object:
    if not restore_context:
        return query
    if isinstance(query, str):
        return f"{query}\n\n{restore_context}"
    if isinstance(query, list):
        next_query = list(query)
        next_query.append(
            {
                "type": "text",
                "text": f"Restored archived context for this turn:\n{restore_context}",
            }
        )
        return next_query
    return query


async def prevalidate_archive_restore_actions(request: AgentRequest) -> None:
    """Validate explicit archive restore actions before the chat turn is persisted."""
    if not request.archive_restore_actions:
        return
    if not request.chat_id:
        raise ArchiveRestoreRequestError("Archive restore action requires an initialized chat workspace.")

    chat_workspace_dir: str | None = None
    chat_loaded = False
    db_had_workspace = False
    try:
        from app.services.chat.chat_service import ChatService

        chat = await ChatService.get_chat_metadata(request.chat_id)
        if chat:
            chat_loaded = True

            if chat.project_id:
                from app.services.project.project_service import ProjectService

                project = await ProjectService.get_project(chat.project_id)
                if project and project.workspace_path:
                    chat_workspace_dir = project.workspace_path
                    db_had_workspace = True

            if not chat_workspace_dir and chat.workspace_dir:
                chat_workspace_dir = chat.workspace_dir
                db_had_workspace = True
    except Exception as exc:
        logger.warning("Failed to load chat metadata for %s: %s", request.chat_id, exc)

    if not chat_workspace_dir:
        chat_workspace_dir = await resolve_default_chat_workspace_dir(
            request.chat_id,
            persist_workspace=chat_loaded and not db_had_workspace,
        )

    await build_archive_restore_action_context(
        request,
        chat_workspace_dir,
        record_allowed=False,
    )
