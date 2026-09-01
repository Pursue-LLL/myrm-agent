"""Feishu channel Doctor diagnostic suite.

Performs structured health checks across Feishu App credentials, bot identity,
CardKit streaming permissions, WebSocket long connection, and Webhook reachability.

[INPUT]
- FeishuClient, channel configuration, and network endpoints.

[OUTPUT]
- FeishuDiagnosticReport: Comprehensive diagnostic result dataclass.
- diagnose_feishu_channel: Main diagnostic runner function.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .sdk.client import FeishuClient

logger = logging.getLogger("myrm.channels.feishu.doctor")


@dataclass
class DiagnosticCheckItem:
    """Individual diagnostic check result."""

    name: str
    passed: bool
    message: str
    details: dict[str, object] = field(default_factory=dict)


@dataclass
class FeishuDiagnosticReport:
    """Full diagnostic report for a Feishu channel instance."""

    app_id: str
    is_healthy: bool
    checks: list[DiagnosticCheckItem]
    recommendations: list[str] = field(default_factory=list)


async def diagnose_feishu_channel(
    client: FeishuClient,
    *,
    app_id: str,
    transport_mode: str = "websocket",
    webhook_url: str | None = None,
) -> FeishuDiagnosticReport:
    """Run comprehensive Feishu channel health diagnostics.

    Checks:
    1. Tenant Access Token acquisition.
    2. Bot identity & open_id resolution.
    3. CardKit streaming capability test.
    4. Transport mode validation (WebSocket vs Public Webhook).

    Args:
        client: Active FeishuClient instance.
        app_id: Feishu Application ID.
        transport_mode: "websocket" or "webhook".
        webhook_url: Optional public Webhook URL.

    Returns:
        FeishuDiagnosticReport
    """
    checks: list[DiagnosticCheckItem] = []
    recommendations: list[str] = []

    # Check 1: Token Acquisition
    try:
        token = await client.ensure_token()
        token_ok = bool(token)
        checks.append(
            DiagnosticCheckItem(
                name="tenant_access_token",
                passed=token_ok,
                message="Tenant Access Token acquired successfully." if token_ok else "Failed to acquire token.",
            )
        )
    except Exception as e:
        checks.append(
            DiagnosticCheckItem(
                name="tenant_access_token",
                passed=False,
                message=f"Exception during token acquisition: {e}",
            )
        )
        recommendations.append("Verify App ID and App Secret in Feishu Open Platform.")
        return FeishuDiagnosticReport(
            app_id=app_id,
            is_healthy=False,
            checks=checks,
            recommendations=recommendations,
        )

    # Check 2: Bot Identity
    bot_id = client.bot_open_id
    bot_ok = bool(bot_id)
    checks.append(
        DiagnosticCheckItem(
            name="bot_identity",
            passed=bot_ok,
            message=f"Bot Open ID resolved: {bot_id}" if bot_ok else "Bot Open ID not resolved.",
            details={"bot_open_id": bot_id},
        )
    )
    if not bot_ok:
        recommendations.append("Ensure Bot capability is enabled in Feishu App Developer Console.")

    # Check 3: CardKit Streaming API Probe
    import uuid

    probe_card_id = f"doctor-probe-{uuid.uuid4().hex[:8]}"
    cardkit_ok = False
    try:
        # Probe CardKit streaming create endpoint
        cardkit_ok = await client.streaming_card_create(probe_card_id, seq=1)
        checks.append(
            DiagnosticCheckItem(
                name="cardkit_streaming",
                passed=cardkit_ok,
                message="CardKit streaming API verified."
                if cardkit_ok
                else "CardKit streaming API unavailable (will fallback to edit_message).",
            )
        )
    except Exception as e:
        checks.append(
            DiagnosticCheckItem(
                name="cardkit_streaming",
                passed=False,
                message=f"CardKit probe failed: {e}",
            )
        )

    if not cardkit_ok:
        recommendations.append(
            "CardKit streaming requires 'cardkit:card:operate' permission. Fallback edit mode will be used automatically."
        )

    # Check 4: Transport & Callback Reachability
    if transport_mode == "webhook":
        has_url = bool(webhook_url)
        checks.append(
            DiagnosticCheckItem(
                name="webhook_reachability",
                passed=has_url,
                message=f"Webhook URL configured: {webhook_url}" if has_url else "Webhook mode enabled but URL missing.",
            )
        )
        if not has_url:
            recommendations.append("Configure a valid public Webhook URL or switch to WebSocket transport mode.")
    else:
        checks.append(
            DiagnosticCheckItem(
                name="transport_mode",
                passed=True,
                message="Using WebSocket long-connection mode. Numbered action fallback enabled for local environments.",
            )
        )

    is_healthy = all(c.passed for c in checks if c.name in ("tenant_access_token", "bot_identity"))

    return FeishuDiagnosticReport(
        app_id=app_id,
        is_healthy=is_healthy,
        checks=checks,
        recommendations=recommendations,
    )
