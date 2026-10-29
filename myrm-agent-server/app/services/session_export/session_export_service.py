"""Session Export Application Service.

[INPUT] export_types.py, interactive_html_compiler.py, secret_redactor.py, chat_service.py, share_token.py
[OUTPUT] SessionExportService: Coordinates stored-conversation retrieval, credential preview, standalone HTML compilation, and share token issuance. SessionNotFoundError: the chat to export does not exist.
[POS] app/services/session_export/session_export_service.py
"""

import asyncio

from app.database.dto import ChatDTO
from app.services.chat.chat_service import ChatService
from app.services.chat.share_token import create_chat_share_token
from app.services.session_export.export_types import (
    ExportHtmlOptions,
    ExportTurnMessage,
    InteractiveHtmlExportResult,
    RedactionSummary,
    ShareLinkRequest,
    ShareLinkResponse,
)
from app.services.session_export.interactive_html_compiler import InteractiveHtmlCompiler
from app.services.session_export.secret_redactor import secret_redactor

_AGENT_NAME = "AI Agent"


class SessionNotFoundError(LookupError):
    """The chat to export or preview does not exist."""


class SessionExportService:
    """Coordinates stored-conversation retrieval, credential preview, and interactive HTML compilation."""

    @classmethod
    async def export_interactive_html(
        cls,
        chat_id: str,
        options: ExportHtmlOptions,
    ) -> InteractiveHtmlExportResult:
        """Compile the stored conversation into zero-network interactive HTML."""
        chat = await cls._require_chat(chat_id)
        return InteractiveHtmlCompiler.compile_session(
            chat_id=chat_id,
            title=chat.title or f"Conversation {chat_id[:8]}",
            agent_name=_AGENT_NAME,
            messages=await cls._load_turns(chat_id),
            options=options,
        )

    @classmethod
    async def preview_redaction(cls, chat_id: str) -> RedactionSummary:
        """Report the credentials stored in the conversation, which is what the export scrubs."""
        await cls._require_chat(chat_id)
        turns = await cls._load_turns(chat_id)
        # The scan is CPU-bound regex work over the whole conversation; off the event loop it no longer stalls other requests.
        return await asyncio.to_thread(secret_redactor.detect_secrets_in, [turn.content for turn in turns])

    @staticmethod
    async def _require_chat(chat_id: str) -> ChatDTO:
        chat = await ChatService.get_chat_metadata(chat_id)
        if chat is None:
            raise SessionNotFoundError(chat_id)
        return chat

    @staticmethod
    async def _load_turns(chat_id: str) -> list[ExportTurnMessage]:
        messages = await ChatService.get_all_messages(chat_id)
        return [
            ExportTurnMessage(
                role=message.role,
                content=message.content,
                created_at=message.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            )
            for message in messages
        ]

    @classmethod
    def create_share_link(
        cls,
        chat_id: str,
        req: ShareLinkRequest,
        base_url: str = "http://localhost:3000",
    ) -> ShareLinkResponse:
        """Issue a stateless HMAC share token and construct the share URL."""
        token, expires_at = create_chat_share_token(
            chat_id=chat_id,
            ttl_seconds=req.ttl_seconds,
            password=req.password,
        )
        share_url = f"{base_url.rstrip('/')}/share/{token}"
        return ShareLinkResponse(
            chat_id=chat_id,
            share_url=share_url,
            share_token=token,
            expires_at_unix=expires_at,
            is_password_protected=bool(req.password),
        )


session_export_service = SessionExportService()
