"""Web Push REST API router.

[INPUT]
- app.core.web_push::get_web_push_service
- app.api.web_push.schemas

[OUTPUT]
- router: Web Push REST endpoints (VAPID key, subscribe, unsubscribe, test)

[POS]
API layer for Web Push. Thin delegation to WebPushService.
"""

import logging

from fastapi import APIRouter

from app.api.web_push.schemas import (
    WebPushSubscriptionRequest,
    WebPushSubscriptionResponse,
    WebPushTestRequest,
    WebPushUnsubscribeRequest,
    WebPushVapidKeyResponse,
)
from app.core.web_push.service import get_web_push_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/web-push", tags=["Web Push"])


@router.get("/vapid-key", response_model=WebPushVapidKeyResponse)
async def get_vapid_public_key() -> WebPushVapidKeyResponse:
    """Return the VAPID application server public key for client-side subscription."""
    service = get_web_push_service()
    return WebPushVapidKeyResponse(public_key=service.public_key)


@router.post("/subscribe", response_model=WebPushSubscriptionResponse)
async def subscribe(req: WebPushSubscriptionRequest) -> WebPushSubscriptionResponse:
    """Register a new Web Push subscription."""
    service = get_web_push_service()
    endpoint_hash = await service.subscribe(
        endpoint=req.endpoint,
        p256dh=req.p256dh,
        auth=req.auth,
        user_agent=req.user_agent,
    )
    return WebPushSubscriptionResponse(endpoint_hash=endpoint_hash)


@router.post("/unsubscribe")
async def unsubscribe(req: WebPushUnsubscribeRequest) -> dict[str, str]:
    """Remove a Web Push subscription."""
    service = get_web_push_service()
    deleted = await service.unsubscribe(endpoint=req.endpoint)
    return {"status": "ok" if deleted else "not_found"}


@router.post("/test")
async def send_test(req: WebPushTestRequest) -> dict[str, int]:
    """Send a test push notification to all registered subscriptions."""
    service = get_web_push_service()
    delivered = await service.broadcast(title=req.title, body=req.body, url="/")
    return {"delivered": delivered}
