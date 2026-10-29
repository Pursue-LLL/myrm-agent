"""Session Export & Share Link API Router.

[INPUT]
- ExportHtmlOptions, ShareLinkRequest

[OUTPUT]
- InteractiveHtmlExportResult, RedactionSummary, ShareLinkResponse

[POS]
app/api/chats/session_export_router.py: REST endpoints for standalone interactive HTML export,
credential preview of the stored conversation, and secure share link generation.
"""

from fastapi import APIRouter, Request, status

from app.core.utils.errors import not_found_error
from app.services.session_export import (
    ExportHtmlOptions,
    InteractiveHtmlExportResult,
    RedactionSummary,
    SessionNotFoundError,
    ShareLinkRequest,
    ShareLinkResponse,
    session_export_service,
)

router = APIRouter(prefix="/chats", tags=["Session Export & Share"])


@router.post(
    "/{chat_id}/export/interactive-html",
    response_model=InteractiveHtmlExportResult,
    status_code=status.HTTP_200_OK,
    summary="Compile chat session into a standalone offline interactive HTML document",
)
async def export_chat_interactive_html(
    chat_id: str,
    options: ExportHtmlOptions,
) -> InteractiveHtmlExportResult:
    """Compile the stored conversation into a zero-dependency standalone HTML bundle."""
    try:
        return await session_export_service.export_interactive_html(
            chat_id=chat_id,
            options=options,
        )
    except SessionNotFoundError as exc:
        raise not_found_error("Conversation") from exc


@router.post(
    "/{chat_id}/export/redact-preview",
    response_model=RedactionSummary,
    status_code=status.HTTP_200_OK,
    summary="Preview the sensitive credentials stored in a conversation",
)
async def preview_secret_redaction(chat_id: str) -> RedactionSummary:
    """Scan the stored conversation and report the credentials the export would scrub."""
    try:
        return await session_export_service.preview_redaction(chat_id)
    except SessionNotFoundError as exc:
        raise not_found_error("Conversation") from exc


@router.post(
    "/{chat_id}/export/share-link",
    response_model=ShareLinkResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate a secure time-limited read-only share link",
)
def create_chat_share_link(
    chat_id: str,
    req: ShareLinkRequest,
    request: Request,
) -> ShareLinkResponse:
    """Issue a stateless HMAC read-only share URL for the chat session."""
    base_url = str(request.base_url).rstrip("/")
    return session_export_service.create_share_link(
        chat_id=chat_id,
        req=req,
        base_url=base_url,
    )
