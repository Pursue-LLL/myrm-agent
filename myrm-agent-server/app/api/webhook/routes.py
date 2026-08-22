"""REST API routes for lifecycle outbound webhooks.

[POS] Endpoints for Webhook CRUD, toggles, and live connectivity ping.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.webhook.schemas import (
    LifecycleWebhookCreate,
    LifecycleWebhookResponse,
    LifecycleWebhookUpdate,
    WebhookPingRequest,
    WebhookPingResponse,
)
from app.database.connection import get_session
from app.database.models.lifecycle_webhook import LifecycleWebhookModel
from app.services.hosting.ssrf_guard import SSRFValidationError, validate_webhook_url
from app.services.webhook.lifecycle_webhook_service import LifecycleOutboundWebhookService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/lifecycle-webhooks", tags=["lifecycle-webhooks"])


@router.get("", response_model=list[LifecycleWebhookResponse])
async def list_lifecycle_webhooks() -> list[LifecycleWebhookResponse]:
    """List all configured lifecycle webhooks."""
    async with get_session() as session:
        stmt = select(LifecycleWebhookModel).order_by(LifecycleWebhookModel.created_at.desc())
        res = await session.execute(stmt)
        models = res.scalars().all()
        return [
            LifecycleWebhookResponse(
                id=m.id,
                name=m.name,
                url=m.url,
                secret=m.secret,
                events=m.events_json or [],
                agent_id=m.agent_id,
                is_active=m.is_active,
                timeout_seconds=m.timeout_seconds,
                last_delivery_at=m.last_delivery_at,
                last_delivery_status=m.last_delivery_status,
                last_error=m.last_error,
                created_at=m.created_at,
                updated_at=m.updated_at,
            )
            for m in models
        ]


@router.post("", response_model=LifecycleWebhookResponse, status_code=status.HTTP_201_CREATED)
async def create_lifecycle_webhook(body: LifecycleWebhookCreate) -> LifecycleWebhookResponse:
    """Create a new outbound lifecycle webhook endpoint."""
    try:
        validate_webhook_url(body.url, allow_http=True)
    except SSRFValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid webhook URL: {exc}",
        ) from exc

    async with get_session() as session:
        m = LifecycleWebhookModel(
            name=body.name,
            url=body.url.strip(),
            secret=body.secret.strip() if body.secret else None,
            events_json=body.events,
            agent_id=body.agent_id,
            is_active=body.is_active,
            timeout_seconds=body.timeout_seconds,
        )
        session.add(m)
        await session.commit()
        await session.refresh(m)

        return LifecycleWebhookResponse(
            id=m.id,
            name=m.name,
            url=m.url,
            secret=m.secret,
            events=m.events_json or [],
            agent_id=m.agent_id,
            is_active=m.is_active,
            timeout_seconds=m.timeout_seconds,
            last_delivery_at=m.last_delivery_at,
            last_delivery_status=m.last_delivery_status,
            last_error=m.last_error,
            created_at=m.created_at,
            updated_at=m.updated_at,
        )


@router.put("/{webhook_id}", response_model=LifecycleWebhookResponse)
async def update_lifecycle_webhook(
    webhook_id: str,
    body: LifecycleWebhookUpdate,
) -> LifecycleWebhookResponse:
    """Update an existing lifecycle webhook endpoint."""
    if body.url is not None:
        try:
            validate_webhook_url(body.url, allow_http=True)
        except SSRFValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid webhook URL: {exc}",
            ) from exc

    async with get_session() as session:
        m = await session.get(LifecycleWebhookModel, webhook_id)
        if not m:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")

        if body.name is not None:
            m.name = body.name
        if body.url is not None:
            m.url = body.url.strip()
        if body.secret is not None:
            m.secret = body.secret.strip() if body.secret else None
        if body.events is not None:
            m.events_json = body.events
        if body.agent_id is not None:
            m.agent_id = body.agent_id
        if body.is_active is not None:
            m.is_active = body.is_active
        if body.timeout_seconds is not None:
            m.timeout_seconds = body.timeout_seconds

        await session.commit()
        await session.refresh(m)

        return LifecycleWebhookResponse(
            id=m.id,
            name=m.name,
            url=m.url,
            secret=m.secret,
            events=m.events_json or [],
            agent_id=m.agent_id,
            is_active=m.is_active,
            timeout_seconds=m.timeout_seconds,
            last_delivery_at=m.last_delivery_at,
            last_delivery_status=m.last_delivery_status,
            last_error=m.last_error,
            created_at=m.created_at,
            updated_at=m.updated_at,
        )


@router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lifecycle_webhook(webhook_id: str) -> None:
    """Delete a lifecycle webhook endpoint."""
    async with get_session() as session:
        m = await session.get(LifecycleWebhookModel, webhook_id)
        if not m:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")
        await session.delete(m)
        await session.commit()


@router.post("/ping", response_model=WebhookPingResponse)
async def ping_lifecycle_webhook(body: WebhookPingRequest) -> WebhookPingResponse:
    """Test immediate connectivity and signature dispatch to target webhook URL."""
    svc = LifecycleOutboundWebhookService.get_instance()
    res = await svc.ping_webhook(url=body.url, secret=body.secret, timeout=body.timeout_seconds)
    return WebhookPingResponse(
        success=res.success,
        status_code=res.status_code,
        latency_ms=res.latency_ms,
        error=res.error,
    )
