"""Feishu/Lark custom bot webhook delivery for cron job results.

[INPUT]
- myrm_agent_harness.toolkits.cron.types::CronJob, JobResult

[OUTPUT]
- is_feishu_bot_hook_url: detect bot v2 hook URLs
- deliver_feishu_bot_webhook: POST Feishu text message payload

[POS]
Server-side cron delivery adapter. Feishu bot hooks expect
``msg_type=text`` JSON, not the generic Myrm WebhookDelivery schema.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable, Coroutine

import httpx
from myrm_agent_harness.toolkits.cron.types import CronJob, JobResult

logger = logging.getLogger(__name__)

_CONNECT_TIMEOUT = 10
_READ_TIMEOUT = 30
_MAX_RETRIES = 2
_BACKOFF_BASE_S = 2.0
_MAX_TEXT_CHARS = 4000


def is_feishu_bot_hook_url(url: str) -> bool:
    """Return True when ``url`` is a Feishu/Lark custom bot v2 hook."""
    lowered = url.lower()
    return "open.feishu.cn" in lowered or "open.larksuite.com" in lowered


def _build_feishu_text(job: CronJob, result: JobResult) -> str:
    header = f"[{job.name}]" if job.name.strip() else f"[{job.id}]"
    text = (result.output or "").strip()
    if result.error:
        suffix = f"\n\nError: {result.error[:500]}"
        text = f"{text}{suffix}" if text else result.error[:500]
    if not text:
        text = "Cron task completed." if result.success else "Cron task failed."
    combined = f"{header}\n{text}"
    return combined[:_MAX_TEXT_CHARS]


async def deliver_feishu_bot_webhook(job: CronJob, result: JobResult) -> None:
    """POST cron result to a Feishu/Lark custom bot webhook URL."""
    url = (job.delivery.target or "").strip()
    if not url:
        raise ValueError(f"Feishu bot webhook URL missing for job {job.id}")

    payload = {
        "msg_type": "text",
        "content": {"text": _build_feishu_text(job, result)},
    }
    body = json.dumps(payload, ensure_ascii=False)

    await _retry(
        lambda: _post(url, body),
        label=f"feishu-bot-hook:{job.id}",
    )


async def _post(url: str, body: str) -> None:
    headers = {"Content-Type": "application/json; charset=utf-8"}
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(_READ_TIMEOUT, connect=_CONNECT_TIMEOUT),
    ) as client:
        response = await client.post(url, content=body, headers=headers)
        if response.status_code >= 400:
            raise RuntimeError(f"Feishu bot webhook returned {response.status_code}: {response.text[:200]}")
        try:
            data = response.json()
        except json.JSONDecodeError:
            return
        if isinstance(data, dict):
            code = data.get("code", data.get("StatusCode", 0))
            if code not in (0, None):
                msg = data.get("msg", data.get("StatusMessage", "unknown error"))
                raise RuntimeError(f"Feishu bot webhook error code={code}: {msg}")


async def _retry(
    coro_fn: Callable[[], Coroutine[object, object, None]],
    *,
    label: str,
) -> None:
    last_exc: Exception | None = None
    for attempt in range(1 + _MAX_RETRIES):
        try:
            await coro_fn()
            return
        except Exception as exc:
            last_exc = exc
            if isinstance(exc, ValueError):
                raise
            if attempt < _MAX_RETRIES:
                delay = _BACKOFF_BASE_S * (2**attempt)
                logger.warning(
                    "%s attempt %d/%d failed: %s — retrying in %.1fs",
                    label,
                    attempt + 1,
                    _MAX_RETRIES + 1,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)
    raise last_exc  # type: ignore[misc]
