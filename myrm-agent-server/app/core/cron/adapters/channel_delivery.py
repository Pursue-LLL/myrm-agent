"""ResultDelivery implementation via the Channel Gateway.

Routes cron job results through the application's existing
``ChannelGateway`` infrastructure as ``OutboundMessage`` objects.

Webhook delivery is delegated to the framework's ``WebhookDelivery``.
Feishu/Lark custom bot hook URLs use ``feishu_bot_webhook`` (``msg_type=text`` JSON).
WeCom group bot hook URLs use ``wecom_bot_webhook`` (``msgtype=markdown`` JSON).
Channel delivery uses the channel's own ``send_with_retry`` for
synchronous error propagation (delivery_status=FAILED on failure).
"""

from __future__ import annotations

import logging
import time

from myrm_agent_harness.toolkits.cron.delivery import WebhookDelivery
from myrm_agent_harness.toolkits.cron.types import CronJob, JobResult

from app.channels import OutboundMessage
from app.channels.core.bus import downgrade_components
from app.channels.reliability.retry import send_with_retry
from app.channels.types.status import ChannelStatus

from .feishu_bot_webhook import deliver_feishu_bot_webhook, is_feishu_bot_hook_url
from .wecom_bot_webhook import deliver_wecom_bot_webhook, is_wecom_bot_hook_url

logger = logging.getLogger(__name__)

_webhook_delivery = WebhookDelivery(user_agent="MyrmAgent-Cron/1.0")


class ChannelResultDelivery:
    """Delivers cron results through ChannelGateway or webhook.

    Webhook delivery delegates to the framework's ``WebhookDelivery``.
    Channel delivery uses ``send_with_retry`` for synchronous error
    propagation.  Exceptions propagate to the scheduler so it can record
    ``delivery_status = FAILED`` in the CronRun record.
    """

    async def deliver(self, job: CronJob, result: JobResult) -> None:
        if job.delivery.channel == "silent":
            return

        target = (job.delivery.target or "").strip()

        if job.delivery.channel == "webhook":
            if is_feishu_bot_hook_url(target):
                await deliver_feishu_bot_webhook(job, result)
            elif is_wecom_bot_hook_url(target):
                await deliver_wecom_bot_webhook(job, result)
            else:
                await _webhook_delivery.deliver(job, result)
            return

        if job.delivery.channel == "feishu" and is_feishu_bot_hook_url(target):
            await deliver_feishu_bot_webhook(job, result)
            return

        if job.delivery.channel == "wecom" and is_wecom_bot_hook_url(target):
            await deliver_wecom_bot_webhook(job, result)
            return

        await self._deliver_channel(job, result)

    async def _deliver_channel(self, job: CronJob, result: JobResult) -> None:
        from app.core.channel_bridge import channel_gateway

        content = result.output or ""
        if result.error:
            content += f"\n\n**Error:** {result.error[:500]}"

        recipient_id = self._resolve_recipient(job)

        meta: dict[str, object] = dict(result.metadata) if result.metadata else {}
        meta["job_name"] = job.name
        meta["success"] = result.success

        msg = OutboundMessage(
            channel=job.delivery.channel,
            recipient_id=recipient_id,
            content=content,
            user_id=job.user_id,
            metadata=meta,
        )

        channel = channel_gateway.bus.channels.get(msg.channel)
        if not channel:
            raise RuntimeError(f"No channel registered for '{msg.channel}'")
        if channel.status in (ChannelStatus.DISABLED, ChannelStatus.STOPPED):
            raise RuntimeError(f"Channel '{msg.channel}' is {channel.status}")

        msg = downgrade_components(msg, channel)
        t0 = time.monotonic()
        try:
            await send_with_retry(
                channel.send,
                msg,
                config=channel.retry_config,
                should_retry=channel.should_retry,
                extract_retry_after=channel.extract_retry_after,
                label=f"cron-delivery:{msg.channel}",
            )
            channel.activity.record_outbound(latency_ms=(time.monotonic() - t0) * 1000)
        except BaseException:
            channel.activity.record_error()
            raise

    @staticmethod
    def _resolve_recipient(job: CronJob) -> str:
        if job.delivery.target:
            return str(job.delivery.target)
        if job.delivery.channel == "chat" and job.chat_id:
            return str(job.chat_id)
        raise ValueError(f'Cron job {job.id}: delivery target is required for channel "{job.delivery.channel}"')
