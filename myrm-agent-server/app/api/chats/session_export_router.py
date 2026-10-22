"""Session Export & Share Link API Router.

[INPUT]
- ExportHtmlOptions, RedactPreviewRequest, ShareLinkRequest

[OUTPUT]
- InteractiveHtmlExportResult, RedactionSummary, ShareLinkResponse

[POS]
app/api/chats/session_export_router.py: REST endpoints for standalone interactive HTML export,
secret credential preview, and secure share link generation.
"""

from fastapi import APIRouter, Request, status

from app.services.session_export import (
    ExportHtmlOptions,
    InteractiveHtmlExportResult,
    RedactPreviewRequest,
    RedactionSummary,
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
    """Compile multi-turn conversation into zero-dependency standalone HTML bundle."""
    return await session_export_service.export_interactive_html(
        chat_id=chat_id,
        options=options,
    )


@router.post(
    "/export/redact-preview",
    response_model=RedactionSummary,
    status_code=status.HTTP_200_OK,
    summary="Preview detected sensitive credentials in candidate text",
)
def preview_secret_redaction(
    req: RedactPreviewRequest,
) -> RedactionSummary:
    """Scan candidate text and return summary of sensitive credentials without modification."""
    return session_export_service.preview_redaction(req.text)


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
