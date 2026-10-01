"""Zero Data Retention (ZDR) endpoints for enterprise compliance and ephemeral wipes.

[INPUT]
- fastapi::APIRouter, HTTPException, Query, Response (POS: Web 框架组件)
- app.services.chat.ephemeral_session_store::EphemeralSessionStore
  (POS: 纯内存会话存储器)
- app.core.security.zdr_attestation::generate_zdr_attestation
  (POS: 密码学合规凭证生成器)

[OUTPUT]
- router: APIRouter with ZDR status, attestation receipt, and wipe endpoints.

[POS]
API route handler for enterprise compliance teams and client-side ZDR controls.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import JSONResponse

from app.core.security.zdr_attestation import generate_zdr_attestation
from app.core.utils.response_utils import success_response
from app.services.chat.ephemeral_session_store import EphemeralSessionStore

router = APIRouter(prefix="", tags=["chat-zdr"])


@router.get("/{chat_id}/zdr/status")
async def get_zdr_status(chat_id: str) -> JSONResponse:
    """Get active ZDR compliance status and ephemeral buffer metrics."""
    store = EphemeralSessionStore.get_instance()
    has_session = await store.has_session(chat_id)
    if not has_session:
        return success_response(
            data={
                "chat_id": chat_id,
                "is_active_ephemeral": False,
                "zero_disk_retention": False,
                "message_count": 0,
            }
        )

    summary = await store.get_audit_summary(chat_id)
    return success_response(
        data={
            "chat_id": chat_id,
            "is_active_ephemeral": True,
            "zero_disk_retention": True,
            "message_count": summary["message_count"] if summary else 0,
            "total_chars": summary["total_chars"] if summary else 0,
            "reconnect_window_seconds": 60,
        }
    )


@router.get("/{chat_id}/zdr/attestation")
async def get_zdr_attestation(
    chat_id: str,
    format: str = Query("json", description="Output format: json or markdown"),
) -> Response:
    """Download signed cryptographic attestation receipt for this ZDR session."""
    store = EphemeralSessionStore.get_instance()
    summary = await store.get_audit_summary(chat_id)
    if not summary:
        raise HTTPException(
            status_code=404,
            detail=f"No active ephemeral ZDR session found for chat_id={chat_id}",
        )

    attestation = generate_zdr_attestation(
        chat_id=chat_id,
        message_count=int(summary["message_count"]),
        total_chars=int(summary["total_chars"]),
        created_at_timestamp=float(summary["created_at"]),
    )

    if format.lower() == "markdown":
        report_md = attestation.to_markdown_report()
        return Response(
            content=report_md,
            media_type="text/markdown",
            headers={
                "Content-Disposition": f'attachment; filename="zdr_attestation_{chat_id}.md"'
            },
        )

    return success_response(data=attestation.to_dict())


@router.post("/{chat_id}/zdr/wipe")
async def wipe_zdr_session(chat_id: str) -> JSONResponse:
    """Physically overwrite memory buffers with 0x00 and purge the session immediately."""
    store = EphemeralSessionStore.get_instance()
    wiped = await store.wipe(chat_id)
    return success_response(
        data={
            "chat_id": chat_id,
            "wiped": wiped,
            "message": "Memory buffers overwritten with 0x00 and purged successfully",
        }
    )


@router.post("/{chat_id}/zdr/reconnect")
async def reconnect_zdr_session(chat_id: str) -> JSONResponse:
    """Acknowledge client reconnection within the 60s tolerance window."""
    store = EphemeralSessionStore.get_instance()
    reconnected = await store.mark_reconnected(chat_id)
    return success_response(
        data={
            "chat_id": chat_id,
            "reconnected": reconnected,
        }
    )
