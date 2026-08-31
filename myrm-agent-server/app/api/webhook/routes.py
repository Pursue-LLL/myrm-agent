"""REST API routes for lifecycle outbound webhooks.

[POS] CRUD, toggles, anonymous `/ping`, and saved `/{id}/ping` connectivity probes for lifecycle webhooks.
"""

from __future__ import annotations

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
from app.services.webhook.lifecycle_webhook_service import (
    LifecycleOutboundWebhookService,
)

router = APIRouter(prefix="/lifecycle-webhooks", tags=["lifecycle-webhooks"])


def _to_webhook_response(
    model: LifecycleWebhookModel,
    *,
    include_secret: bool,
) -> LifecycleWebhookResponse:
    return LifecycleWebhookResponse(
        id=model.id,
        name=model.name,
        url=model.url,
        secret=model.secret if include_secret else None,
        has_secret=bool(model.secret),
        events=model.events_json or [],
        agent_id=model.agent_id,
        is_active=model.is_active,
        timeout_seconds=model.timeout_seconds,
        last_delivery_at=model.last_delivery_at,
        last_delivery_status=model.last_delivery_status,
        last_error=model.last_error,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


@router.get("", response_model=list[LifecycleWebhookResponse])
async def list_lifecycle_webhooks() -> list[LifecycleWebhookResponse]:
    """List all configured lifecycle webhooks."""
    async with get_session() as session:
        stmt = select(LifecycleWebhookModel).order_by(LifecycleWebhookModel.created_at.desc())
        res = await session.execute(stmt)
        models = res.scalars().all()
        return [_to_webhook_response(m, include_secret=False) for m in models]


@router.post("", response_model=LifecycleWebhookResponse, status_code=status.HTTP_201_CREATED)
async def create_lifecycle_webhook(
    body: LifecycleWebhookCreate,
) -> LifecycleWebhookResponse:
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

        return _to_webhook_response(m, include_secret=True)


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

        return _to_webhook_response(m, include_secret=body.secret is not None)


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


@router.post("/{webhook_id}/ping", response_model=WebhookPingResponse)
async def ping_saved_lifecycle_webhook(webhook_id: str) -> WebhookPingResponse:
    """Ping a saved webhook using its stored URL, secret, and timeout."""
    async with get_session() as session:
        model = await session.get(LifecycleWebhookModel, webhook_id)
        if not model:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")

    svc = LifecycleOutboundWebhookService.get_instance()
    res = await svc.ping_webhook(
        url=model.url,
        secret=model.secret,
        timeout=model.timeout_seconds,
    )
    return WebhookPingResponse(
        success=res.success,
        status_code=res.status_code,
        latency_ms=res.latency_ms,
        error=res.error,
    )
