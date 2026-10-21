"""iMessage webhook management — auto-registration and verification.

[POS]
Webhook lifecycle management extracted from channel to maintain single-responsibility.
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


async def register_webhook(http: httpx.AsyncClient, api_url: str, password: str, webhook_url: str) -> None:
    """Register our webhook URL with BlueBubbles server for event delivery."""
    if not webhook_url:
        return
    try:
        resp = await http.get(
            f"{api_url}/api/v1/webhook",
            params={"password": password},
            timeout=5.0,
        )
        if resp.status_code == 200:
            existing = resp.json().get("data", [])
            if isinstance(existing, list):
                for wh in existing:
                    if isinstance(wh, dict) and wh.get("url") == webhook_url:
                        logger.debug("IMessageChannel: webhook already registered")
                        return

        await http.post(
            f"{api_url}/api/v1/webhook",
            params={"password": password},
            json={"url": webhook_url, "events": ["new-message"]},
            timeout=5.0,
        )
        logger.info("IMessageChannel: webhook registered at %s", webhook_url)
    except Exception as exc:
        logger.warning("IMessageChannel: webhook registration failed: %s", exc)


async def unregister_webhook(http: httpx.AsyncClient, api_url: str, password: str, webhook_url: str) -> None:
    """Remove our webhook registration from BlueBubbles on shutdown."""
    if not webhook_url:
        return
    try:
        resp = await http.get(
            f"{api_url}/api/v1/webhook",
            params={"password": password},
            timeout=5.0,
        )
        if resp.status_code != 200:
            return
        existing = resp.json().get("data", [])
        if not isinstance(existing, list):
            return
        for wh in existing:
            if isinstance(wh, dict) and wh.get("url") == webhook_url:
                wh_id = wh.get("id")
                if wh_id:
                    await http.delete(
                        f"{api_url}/api/v1/webhook/{wh_id}",
                        params={"password": password},
                        timeout=5.0,
                    )
                    logger.info("IMessageChannel: webhook unregistered")
    except Exception:
        pass
