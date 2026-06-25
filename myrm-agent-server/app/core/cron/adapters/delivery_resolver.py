"""Cron webhook URL → DeliveryConfig mapping (Myrm channel product rules).

[INPUT]
- myrm_agent_harness.toolkits.cron.types::DeliveryConfig

[OUTPUT]
- resolve_cron_delivery: map webhook URL to DeliveryConfig for cron_manage_tool

[POS]
Business-layer cron delivery resolver. Non-empty webhook URLs use the generic
``webhook`` channel; Feishu/Lark bot hook formatting is handled at delivery
time in ``feishu_bot_webhook.py`` (not via FeishuChannel OAuth).
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.cron.types import DeliveryConfig


def resolve_cron_delivery(webhook_url: str) -> DeliveryConfig:
    """Map a webhook URL to a DeliveryConfig for scheduled task notifications."""
    if not webhook_url.strip():
        return DeliveryConfig(channel="chat")
    return DeliveryConfig(channel="webhook", target=webhook_url)
