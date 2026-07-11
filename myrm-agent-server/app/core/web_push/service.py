"""Web Push service — subscription CRUD + push sending.

[INPUT]
- app.core.web_push.vapid_keys::load_vapid_keys
- app.database.models::WebPushSubscription
- app.database.connection::get_session

[OUTPUT]
- WebPushService: subscribe/unsubscribe/broadcast
- get_web_push_service(): singleton accessor

[POS]
Core Web Push business logic. Decoupled from API layer and event dispatch.
Uses pywebpush for VAPID-signed push, SQLAlchemy for subscription persistence.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select, update

logger = logging.getLogger(__name__)

_GONE_STATUS_CODES = frozenset({404, 410})


class WebPushService:
    """Manages Web Push subscriptions and sends VAPID-signed push messages."""

    def __init__(self) -> None:
        self._private_pem: str | None = None
        self._public_key: str | None = None

    def _ensure_keys(self) -> tuple[str, str]:
        if self._private_pem is None or self._public_key is None:
            from app.core.web_push.vapid_keys import load_vapid_keys

            self._private_pem, self._public_key = load_vapid_keys()
        return self._private_pem, self._public_key

    @property
    def public_key(self) -> str:
        """Application server public key (URL-safe base64, no padding)."""
        _, pub = self._ensure_keys()
        return pub

    @staticmethod
    def _hash_endpoint(endpoint: str) -> str:
        return hashlib.sha256(endpoint.encode()).hexdigest()[:32]

    async def subscribe(
        self,
        endpoint: str,
        p256dh: str,
        auth: str,
        user_agent: str = "",
    ) -> str:
        """Register or update a push subscription. Returns endpoint_hash."""
        from app.database.connection import get_session
        from app.database.models import WebPushSubscription

        endpoint_hash = self._hash_endpoint(endpoint)
        now = datetime.now(timezone.utc)

        async with get_session() as session:
            existing = (
                await session.execute(
                    select(WebPushSubscription).where(
                        WebPushSubscription.endpoint_hash == endpoint_hash
                    )
                )
            ).scalar_one_or_none()

            if existing:
                await session.execute(
                    update(WebPushSubscription)
                    .where(WebPushSubscription.endpoint_hash == endpoint_hash)
                    .values(
                        endpoint=endpoint,
                        p256dh=p256dh,
                        auth=auth,
                        user_agent=user_agent,
                        last_used_at=now,
                    )
                )
            else:
                session.add(
                    WebPushSubscription(
                        endpoint_hash=endpoint_hash,
                        endpoint=endpoint,
                        p256dh=p256dh,
                        auth=auth,
                        user_agent=user_agent,
                        created_at=now,
                        last_used_at=now,
                    )
                )
            await session.commit()

        logger.info("Web Push subscription registered: %s", endpoint_hash)
        return endpoint_hash

    async def unsubscribe(self, endpoint: str) -> bool:
        """Remove a push subscription. Returns True if deleted."""
        from app.database.connection import get_session
        from app.database.models import WebPushSubscription

        endpoint_hash = self._hash_endpoint(endpoint)

        async with get_session() as session:
            result = await session.execute(
                delete(WebPushSubscription).where(
                    WebPushSubscription.endpoint_hash == endpoint_hash
                )
            )
            await session.commit()

        deleted = result.rowcount > 0
        if deleted:
            logger.info("Web Push subscription removed: %s", endpoint_hash)
        return deleted

    async def broadcast(self, title: str, body: str, url: str = "/") -> int:
        """Send a push notification to all registered subscriptions.

        Returns the number of successfully delivered pushes.
        """
        from app.database.connection import get_session
        from app.database.models import WebPushSubscription

        async with get_session() as session:
            result = await session.execute(select(WebPushSubscription))
            subscriptions = result.scalars().all()

        if not subscriptions:
            return 0

        payload = json.dumps(
            {"title": title, "body": body, "url": url},
            ensure_ascii=False,
        )

        tasks = [
            self._send_one(
                endpoint=sub.endpoint,
                p256dh=sub.p256dh,
                auth=sub.auth,
                payload=payload,
                endpoint_hash=sub.endpoint_hash,
            )
            for sub in subscriptions
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)
        delivered = sum(1 for r in results if r is True)
        logger.info(
            "Web Push broadcast: %d/%d delivered (title=%s)",
            delivered,
            len(subscriptions),
            title[:50],
        )
        return delivered

    async def _send_one(
        self,
        endpoint: str,
        p256dh: str,
        auth: str,
        payload: str,
        endpoint_hash: str,
    ) -> bool:
        """Send to a single subscription. Auto-cleans gone subscriptions."""
        private_pem, _ = self._ensure_keys()

        subscription_info: dict[str, Any] = {
            "endpoint": endpoint,
            "keys": {"p256dh": p256dh, "auth": auth},
        }

        vapid_claims = {
            "sub": "mailto:noreply@myrm.ai",
        }

        from pywebpush import WebPushException, webpush

        try:
            await asyncio.to_thread(
                webpush,
                subscription_info=subscription_info,
                data=payload,
                vapid_private_key=private_pem,
                vapid_claims=vapid_claims,
            )
            return True
        except WebPushException as exc:
            resp = getattr(exc, "response", None)
            if resp is not None:
                sc = getattr(resp, "status_code", None)
                if sc in _GONE_STATUS_CODES:
                    await self._remove_subscription(endpoint_hash)
                    logger.info(
                        "Removed expired subscription %s (HTTP %d)",
                        endpoint_hash,
                        sc,
                    )
                    return False
            logger.warning("Web Push failed for %s: %s", endpoint_hash, exc)
            return False
        except Exception as exc:
            logger.warning("Web Push failed for %s: %s", endpoint_hash, exc)
            return False

    async def _remove_subscription(self, endpoint_hash: str) -> None:
        """Remove a subscription by its hash (internal cleanup)."""
        from app.database.connection import get_session
        from app.database.models import WebPushSubscription

        try:
            async with get_session() as session:
                await session.execute(
                    delete(WebPushSubscription).where(
                        WebPushSubscription.endpoint_hash == endpoint_hash
                    )
                )
                await session.commit()
        except Exception as exc:
            logger.warning("Failed to remove subscription %s: %s", endpoint_hash, exc)


_service: WebPushService | None = None


def get_web_push_service() -> WebPushService:
    """Singleton accessor — lazily created on first call."""
    global _service  # noqa: PLW0603
    if _service is None:
        _service = WebPushService()
    return _service
