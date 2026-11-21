"""Cron webhook URL → DeliveryConfig mapping and the channels that deliver nowhere outside (Myrm channel product rules).

[INPUT]
- myrm_agent_harness.toolkits.cron.types::DeliveryConfig

[OUTPUT]
- resolve_cron_delivery: map webhook URL to DeliveryConfig for cron_manage_tool
- NON_OUTBOUND_CHANNELS: the delivery channels that send nothing to an outside destination

[POS]
Business-layer cron delivery rules. Non-empty webhook URLs use the generic
``webhook`` channel; Feishu/Lark bot hook formatting is handled at delivery
time in ``feishu_bot_webhook.py`` (not via FeishuChannel OAuth). Webhook
deliveries get a fresh HMAC secret so Agent-created tasks are
signature-verifiable from the first delivery.
"""

from __future__ import annotations

import secrets

from myrm_agent_harness.toolkits.cron.types import DeliveryConfig

# Channels that send nothing outside the application: they need no address, take no test delivery and have no
# destination whose health could be judged. The harness only knows ``none`` as "do not deliver"; the rest is product.
NON_OUTBOUND_CHANNELS: frozenset[str] = frozenset({"chat", "silent", "none"})


def resolve_cron_delivery(webhook_url: str) -> DeliveryConfig:
    """Map a webhook URL to a DeliveryConfig for scheduled task notifications."""
    if not webhook_url.strip():
        return DeliveryConfig(channel="chat")
    return DeliveryConfig(
        channel="webhook",
        target=webhook_url,
        secret=secrets.token_hex(32),
    )
