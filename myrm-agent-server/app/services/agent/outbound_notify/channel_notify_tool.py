"""LangChain adapter for agent-initiated outbound channel notifications.

[INPUT]
- .protocols::NotificationSender (POS: outbound notification sender protocol)
- .types::NotifySessionState, NotifyToolConfig (POS: outbound notification data types)
- app.channels.types.messages::MediaAttachment, guess_media_type (POS: media types)

[OUTPUT]
- create_channel_notify_tool: Factory for channel_notify_tool BaseTool.

[POS]
Optional LangChain surface for agent-initiated outbound channel notifications. The destination is one required choice
among the configured ones, so the approval card shows exactly where the message goes.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Literal, cast
from urllib.parse import urlparse

from langchain_core.tools import BaseTool
from langchain_core.tools.convert import tool
from pydantic import BaseModel, Field, create_model

from .attachment_path_policy import (
    resolve_allowed_local_attachment_path,
)
from .types import NotifySessionState, NotifyToolConfig

if TYPE_CHECKING:
    from collections.abc import Collection

    from app.channels.types.messages import MediaAttachment

    from .protocols import NotificationSender

_TOOL_DESCRIPTION = (
    "Send a message, optionally with files, to one of the user's pre-configured destinations (see the destination parameter).\n\n"
    "Every send needs the user's approval, so use it only when the user asks to send something to an external destination. "
    "If the user names a recipient or channel that is not one of the destinations, or the request fits more than one "
    "destination, do not call this tool; ask the user instead."
)
_DESTINATION_DESCRIPTION = "Where to send. Every send needs the user's approval."
_BODY_DESCRIPTION = "The notification message content to send. Can be empty when attachments are provided."
_ATTACHMENTS_DESCRIPTION = (
    "Optional file attachments to include with the notification. "
    "Each entry is a workspace file path (relative or absolute, e.g. 'report.pdf' or '/myrm/sandbox/report.pdf') "
    "or an HTTP/HTTPS URL (e.g. 'https://example.com/image.png'). "
    "Supported types: images, documents, audio, video."
)


def _build_args_schema(destinations: Collection[str]) -> type[BaseModel]:
    """The tool's input model: ``destination`` is an enum of the configured destination names."""
    # A ``Literal`` of the configured names cannot be written statically, so it is built at runtime; the checkers type
    # that result as ``object``, hence the cast to the ``str`` type the field validates as.
    destination_type = cast("type[str]", Literal.__getitem__(tuple(destinations)))
    return create_model(
        "NotifyInput",
        destination=(destination_type, Field(description=_DESTINATION_DESCRIPTION)),
        body=(str, Field(default="", description=_BODY_DESCRIPTION)),
        attachments=(list[str], Field(default_factory=list, description=_ATTACHMENTS_DESCRIPTION)),
    )


def _resolve_attachments(
    entries: list[str],
    *,
    allowed_roots: tuple[str, ...],
) -> tuple[tuple[MediaAttachment, ...], list[str]]:
    """Convert non-blank path/URL strings to MediaAttachment objects.

    Returns (resolved_attachments, errors).
    """
    from app.channels.types.messages import MediaAttachment as MA
    from app.channels.types.messages import guess_media_type

    attachments: list[MA] = []
    errors: list[str] = []

    for entry in entries:
        is_url = entry.startswith(("http://", "https://"))

        resolved_path: str | None = None
        if not is_url:
            resolved_path = resolve_allowed_local_attachment_path(entry, allowed_roots)
            if resolved_path is None:
                errors.append(f"Path not allowed (must be under agent workspace): {entry}")
                continue
            if not os.path.exists(resolved_path) or not os.path.isfile(resolved_path):
                errors.append(f"File not found: {entry}")
                continue

        filename = os.path.basename(urlparse(entry).path) if is_url else os.path.basename(resolved_path or entry)
        media_type = guess_media_type(filename)

        attachments.append(
            MA(
                media_type=media_type,
                url=entry if is_url else None,
                path=resolved_path if not is_url else None,
                filename=filename,
            )
        )

    return tuple(attachments), errors


def create_channel_notify_tool(
    sender: NotificationSender,
    config: NotifyToolConfig,
    *,
    allowed_roots: tuple[str, ...] = (),
) -> BaseTool:
    """Create channel_notify_tool bound to the given sender and config."""
    if not config.destinations:
        raise ValueError("channel_notify_tool needs at least one destination")
    session_state = NotifySessionState()

    @tool("channel_notify_tool", args_schema=_build_args_schema(config.destinations), description=_TOOL_DESCRIPTION)
    async def channel_notify_tool(
        destination: str,
        body: str = "",
        attachments: list[str] | None = None,
    ) -> str:
        entries = [entry for entry in (raw.strip() for raw in attachments or []) if entry]
        if not body.strip() and not entries:
            return "Error: notification body and attachments cannot both be empty."

        if session_state.send_count >= config.rate_limit_per_session:
            return (
                f"Error: notification rate limit reached "
                f"({config.rate_limit_per_session} per session). "
                f"Cannot send more notifications in this session."
            )

        if len(body) > config.max_body_length:
            body_truncated = body[: config.max_body_length] + "\n\n[...truncated]"
        else:
            body_truncated = body

        media: tuple[MediaAttachment, ...] = ()
        if entries:
            media, resolve_errors = _resolve_attachments(entries, allowed_roots=allowed_roots)
            if resolve_errors:
                return "Error resolving attachments: " + "; ".join(resolve_errors)

        result = await sender.send(config.destinations[destination], body_truncated, media=media)

        session_state.send_count += 1

        if result.success:
            media_note = f" with {len(media)} attachment(s)" if media else ""
            return f"Notification sent successfully to {destination}{media_note}."
        return f"Error: failed to send notification — {result.error}"

    return channel_notify_tool
