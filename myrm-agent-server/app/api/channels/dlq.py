from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.channels.core.gateway import ChannelGateway
from app.core.channel_bridge import get_channel_gateway

router = APIRouter(tags=["Channels DLQ"])


class DLQMessageResponse(BaseModel):
    id: str
    channel: str
    recipient_id: str
    content: str
    error_reason: str
    status: str
    retry_count: int
    next_retry_at: float
    created_at: float
    payload: dict[str, object]


class DLQListResponse(BaseModel):
    items: list[DLQMessageResponse]
    total: int


@router.get("", response_model=DLQListResponse)
async def get_failed_messages(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: str | None = Query(None, description="Filter by status (pending, retrying, success, failed_permanently)"),
    gateway: ChannelGateway = Depends(get_channel_gateway),
) -> DLQListResponse:
    """Get failed messages from the Dead Letter Queue."""
    msgs = await gateway.bus.get_dlq_messages()
    total = len(msgs)

    # Simple pagination/filtering since the harness currently returns all
    if status and status != "failed_permanently":
        msgs = []
        total = 0

    start = offset
    end = offset + limit
    msgs = msgs[start:end]

    items: list[DLQMessageResponse] = []
    for m in msgs:
        items.append(
            DLQMessageResponse(
                id=m.id,
                channel=m.channel,
                recipient_id=m.recipient,
                content=str(m.content),
                error_reason=m.last_error or "",
                status="failed_permanently",
                retry_count=m.retry_count,
                next_retry_at=0.0,
                created_at=m.enqueued_at,
                payload={},
            )
        )

    return DLQListResponse(items=items, total=total)


@router.post("/{msg_id}/retry")
async def retry_failed_message(
    msg_id: str, gateway: ChannelGateway = Depends(get_channel_gateway)
) -> dict[str, str]:
    """Manually retry a failed message."""
    success = await gateway.bus.retry_dlq_message(msg_id)
    if not success:
        raise HTTPException(status_code=404, detail="Failed message not found")
    return {"status": "success", "message": "Message queued for retry"}


@router.delete("/{msg_id}")
async def delete_failed_message(
    msg_id: str, gateway: ChannelGateway = Depends(get_channel_gateway)
) -> dict[str, str]:
    """Delete a failed message from the DLQ."""
    success = await gateway.bus.delete_dlq_message(msg_id)
    if not success:
        raise HTTPException(status_code=404, detail="Failed message not found")
    return {"status": "success", "message": "Message deleted"}
