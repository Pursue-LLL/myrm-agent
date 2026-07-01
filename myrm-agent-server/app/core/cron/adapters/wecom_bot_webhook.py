"""WeCom (Enterprise WeChat) group bot webhook delivery for cron job results.

[INPUT]
- myrm_agent_harness.toolkits.cron.types::CronJob, JobResult

[OUTPUT]
- is_wecom_bot_hook_url: detect WeCom group bot webhook URLs
- deliver_wecom_bot_webhook: POST WeCom markdown message payload

[POS]
Server-side cron delivery adapter. WeCom group bot webhooks expect
``msgtype=markdown`` JSON, not the generic Myrm WebhookDelivery schema.
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
_MAX_CONTENT_CHARS = 4000


def is_wecom_bot_hook_url(url: str) -> bool:
    """Return True when ``url`` is a WeCom group bot webhook."""
    return "qyapi.weixin.qq.com/cgi-bin/webhook" in url.lower()


def _build_wecom_markdown(job: CronJob, result: JobResult) -> str:
    header = f"**[{job.name}]**" if job.name.strip() else f"**[{job.id}]**"
    status = "✓ 成功" if result.success else "✗ 失败"
    text = (result.output or "").strip()
    if result.error:
        suffix = f"\n\n> Error: {result.error[:500]}"
        text = f"{text}{suffix}" if text else result.error[:500]
    if not text:
        text = "定时任务已完成。" if result.success else "定时任务执行失败。"
    combined = f"{header} {status}\n{text}"
    return combined[:_MAX_CONTENT_CHARS]


async def deliver_wecom_bot_webhook(job: CronJob, result: JobResult) -> None:
    """POST cron result to a WeCom group bot webhook URL."""
    url = (job.delivery.target or "").strip()
    if not url:
        raise ValueError(f"WeCom bot webhook URL missing for job {job.id}")

    payload = {
        "msgtype": "markdown",
        "markdown": {"content": _build_wecom_markdown(job, result)},
    }
    body = json.dumps(payload, ensure_ascii=False)

    await _retry(
        lambda: _post(url, body),
        label=f"wecom-bot-hook:{job.id}",
    )


async def _post(url: str, body: str) -> None:
    headers = {"Content-Type": "application/json; charset=utf-8"}
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(_READ_TIMEOUT, connect=_CONNECT_TIMEOUT),
    ) as client:
        response = await client.post(url, content=body, headers=headers)
        if response.status_code >= 400:
            raise RuntimeError(f"WeCom bot webhook returned {response.status_code}: {response.text[:200]}")
        try:
            data = response.json()
        except json.JSONDecodeError:
            return
        if isinstance(data, dict):
            errcode = data.get("errcode", 0)
            if errcode != 0:
                errmsg = data.get("errmsg", "unknown error")
                raise RuntimeError(f"WeCom bot webhook errcode={errcode}: {errmsg}")


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
