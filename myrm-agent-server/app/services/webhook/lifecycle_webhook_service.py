"""Lifecycle Outbound Webhook Service.

[POS] Asynchronously dispatches Agent lifecycle events to user-configured HTTP Webhook endpoints.
Includes SSRF safety guards, HMAC-SHA256 signature generation, non-blocking delivery queue, and connectivity ping probe.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_session
from app.database.models.lifecycle_webhook import LifecycleWebhookModel
from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus
from app.services.hosting.ssrf_guard import SSRFValidationError, validate_webhook_url

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 10
MAX_DELIVERY_ATTEMPTS = 2
RETRY_BACKOFF_SECONDS = 1.0
QUEUE_MAX_SIZE = 512


@dataclass(frozen=True, slots=True)
class OutboundWebhookTarget:
    """Target configuration for outbound dispatch."""

    id: str
    name: str
    url: str
    secret: str | None
    events: list[str]
    agent_id: str | None
    is_active: bool
    timeout_seconds: int


@dataclass(frozen=True, slots=True)
class PingResult:
    """Result of an immediate webhook ping connectivity test."""

    success: bool
    status_code: int | None
    latency_ms: float
    error: str | None = None


class _NoRedirectHandler(urlrequest.HTTPRedirectHandler):
    """Refuse to follow redirects to prevent credential / body leakage."""

    def redirect_request(  # noqa: D102
        self,
        req: object,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> None:
        return None


_opener = urlrequest.build_opener(_NoRedirectHandler)


class LifecycleOutboundWebhookService:
    """Singleton service managing lifecycle webhook subscriptions and dispatch."""

    _instance: LifecycleOutboundWebhookService | None = None

    def __init__(self) -> None:
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=QUEUE_MAX_SIZE)
        self._worker_task: asyncio.Task[None] | None = None
        self._running: bool = False
        self._subscribed: bool = False

    @classmethod
    def get_instance(cls) -> LifecycleOutboundWebhookService:
        """Get or create singleton instance."""
        if cls._instance is None:
            cls._instance = LifecycleOutboundWebhookService()
        return cls._instance

    def start(self) -> None:
        """Start background queue worker and subscribe to AppEventBus."""
        if self._running:
            return
        self._running = True
        try:
            loop = asyncio.get_running_loop()
            self._worker_task = loop.create_task(self._worker_loop())
        except RuntimeError:
            pass

        if not self._subscribed:
            bus = get_event_bus()
            bus.subscribe(self._on_app_event)
            self._subscribed = True
            logger.info("LifecycleOutboundWebhookService started and subscribed to AppEventBus")

    async def stop(self) -> None:
        """Stop background worker."""
        self._running = False
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        self._worker_task = None
        logger.info("LifecycleOutboundWebhookService stopped")

    def _on_app_event(self, event: AppEvent) -> None:
        """Non-blocking synchronous callback from AppEventBus."""
        if not self._running:
            return
        event_name = str(event.event_type)
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._dispatch_event_async(event_name, event.data))
        except RuntimeError:
            pass

    async def _dispatch_event_async(self, event_name: str, data: dict[str, Any]) -> None:
        """Fetch active webhook targets matching event and enqueue payloads."""
        try:
            async with get_session() as session:
                stmt = select(LifecycleWebhookModel).where(LifecycleWebhookModel.is_active == True)  # noqa: E712
                res = await session.execute(stmt)
                models = res.scalars().all()
                targets = [
                    OutboundWebhookTarget(
                        id=m.id,
                        name=m.name,
                        url=m.url,
                        secret=m.secret,
                        events=m.events_json or [],
                        agent_id=m.agent_id,
                        is_active=m.is_active,
                        timeout_seconds=m.timeout_seconds,
                    )
                    for m in models
                ]
        except Exception as exc:
            logger.warning("Failed to fetch lifecycle webhook targets from DB: %s", exc)
            return

        for target in targets:
            if target.events and event_name not in target.events:
                continue
            event_agent_id = data.get("agent_id")
            if target.agent_id and event_agent_id and target.agent_id != event_agent_id:
                continue

            delivery_id = uuid.uuid4().hex
            payload_bytes = self._build_payload_bytes(event_name, data, delivery_id)
            delivery_item = self._build_delivery_item(target, event_name, payload_bytes, delivery_id)

            try:
                self._queue.put_nowait(delivery_item)
            except asyncio.QueueFull:
                logger.warning(
                    "Lifecycle webhook queue full (%d pending) — dropping event %s for %s",
                    QUEUE_MAX_SIZE,
                    event_name,
                    target.name,
                )

    def _build_payload_bytes(self, event_name: str, data: dict[str, Any], delivery_id: str) -> bytes:
        payload = {
            "hook_event_name": event_name,
            "delivery_id": delivery_id,
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "data": data,
        }
        return json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")

    def _build_delivery_item(
        self,
        target: OutboundWebhookTarget,
        event_name: str,
        body: bytes,
        delivery_id: str,
    ) -> dict[str, Any]:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Myrm-Agent-Lifecycle-Webhook/1.0",
            "X-Myrm-Event": event_name,
            "X-Myrm-Delivery": delivery_id,
        }
        if target.secret:
            digest = hmac.new(target.secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
            headers["X-Myrm-Signature-256"] = f"sha256={digest}"

        return {
            "target_id": target.id,
            "url": target.url,
            "name": target.name,
            "event": event_name,
            "body": body,
            "headers": headers,
            "timeout": target.timeout_seconds,
        }

    async def _worker_loop(self) -> None:
        while self._running:
            try:
                delivery = await self._queue.get()
                await self._deliver_and_record(delivery)
                self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Error in lifecycle webhook worker loop: %s", exc, exc_info=True)

    async def _deliver_and_record(self, delivery: dict[str, Any]) -> None:
        target_id = delivery["target_id"]
        url = delivery["url"]
        body = delivery["body"]
        headers = delivery["headers"]
        timeout = delivery["timeout"]

        try:
            validate_webhook_url(url, allow_http=True)
        except SSRFValidationError as exc:
            logger.warning("SSRF blocked outbound webhook delivery to %s: %s", url, exc)
            await self._update_delivery_status(target_id, status_code=None, error=f"SSRF blocked: {exc}")
            return

        status_code, error_msg = await asyncio.to_thread(self._sync_deliver, url, body, headers, timeout)
        await self._update_delivery_status(target_id, status_code=status_code, error=error_msg)

    def _sync_deliver(
        self,
        url: str,
        body: bytes,
        headers: dict[str, str],
        timeout: int,
    ) -> tuple[int | None, str | None]:
        last_error = None
        for attempt in range(1, MAX_DELIVERY_ATTEMPTS + 1):
            req = urlrequest.Request(url, data=body, headers=headers, method="POST")
            try:
                with _opener.open(req, timeout=timeout) as resp:
                    status = getattr(resp, "status", 200)
                    if 200 <= status < 300:
                        return status, None
                    last_error = f"HTTP {status}"
            except urlerror.HTTPError as exc:
                last_error = f"HTTP {exc.code}"
                if 400 <= exc.code < 500:
                    return exc.code, last_error
            except Exception as exc:
                last_error = str(exc) or type(exc).__name__

            if attempt < MAX_DELIVERY_ATTEMPTS:
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)

        return None, last_error

    async def _update_delivery_status(
        self,
        target_id: str,
        status_code: int | None,
        error: str | None,
    ) -> None:
        try:
            async with get_session() as session:
                m = await session.get(LifecycleWebhookModel, target_id)
                if m:
                    m.last_delivery_at = datetime.now(timezone.utc)
                    m.last_delivery_status = status_code
                    m.last_error = error
                    await session.commit()
        except Exception as exc:
            logger.debug("Failed to record webhook delivery status for %s: %s", target_id, exc)

    async def ping_webhook(self, url: str, secret: str | None = None, timeout: int = 10) -> PingResult:
        """Immediately ping target endpoint with a test event."""
        try:
            validate_webhook_url(url, allow_http=True)
        except SSRFValidationError as exc:
            return PingResult(success=False, status_code=None, latency_ms=0.0, error=f"SSRF blocked: {exc}")

        delivery_id = uuid.uuid4().hex
        payload_bytes = self._build_payload_bytes("ping", {"message": "Myrm lifecycle webhook ping probe"}, delivery_id)
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Myrm-Agent-Lifecycle-Webhook/1.0",
            "X-Myrm-Event": "ping",
            "X-Myrm-Delivery": delivery_id,
        }
        if secret:
            digest = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
            headers["X-Myrm-Signature-256"] = f"sha256={digest}"

        start_t = time.perf_counter()
        status_code, error = await asyncio.to_thread(self._sync_deliver, url, payload_bytes, headers, timeout)
        latency_ms = (time.perf_counter() - start_t) * 1000.0

        success = status_code is not None and 200 <= status_code < 300
        return PingResult(
            success=success,
            status_code=status_code,
            latency_ms=round(latency_ms, 2),
            error=error,
        )
