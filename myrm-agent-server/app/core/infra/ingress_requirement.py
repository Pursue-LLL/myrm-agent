"""Resolve whether public Ingress is required for the current deployment.

[INPUT]
- app.channels.inbound_profile (POS: per-channel inbound/outbound classification)
- app.core.channel_bridge.config_loader::load_user_config_entry (POS: decrypted config entries)
- app.core.infra.ingress::get_public_ingress_base_url (POS: Ingress URL resolver)
- app.core.cron.adapters.setup::get_cron_store (POS: cron job persistence)

[OUTPUT]
- IngressRequirementSnapshot: required flag, reasons, per-channel transport modes
- resolve_ingress_requirement: async evaluator
- supplement_ingress_issues: append CONFIG warning when inbound channel lacks Ingress

[POS]
Server-side single source of truth for System settings and channel Ingress badges.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

from app.channels.inbound_profile import (
    CHANNEL_INBOUND_SPECS,
    IngressTransport,
    resolve_channel_ingress_mode,
)
from app.channels.types import ChannelIssue, IssueKind, IssueSeverity
from app.core.channel_bridge.config_loader import load_user_config_entry
from app.core.infra.ingress import get_public_ingress_base_url

_INGRESS_FIX = "Open Settings → System → Public access to configure Ingress or Quick Tunnel."
_CACHE_TTL_SECONDS = 10.0


@dataclass(frozen=True, slots=True)
class IngressRequirementSnapshot:
    required: bool
    has_public_ingress: bool
    reasons: tuple[str, ...] = ()
    channels: dict[str, IngressTransport] = field(default_factory=dict)


_snapshot_cache: tuple[float, IngressRequirementSnapshot] | None = None


async def _load_channel_credential(config_key: str) -> dict[str, object] | None:
    raw = await load_user_config_entry(config_key)
    if not isinstance(raw, dict):
        return None
    return raw


async def _has_cron_webhook_triggers() -> bool:
    from app.core.cron.adapters.setup import get_cron_store

    store = get_cron_store()
    jobs = await store.list_jobs(limit=200)
    for job in jobs:
        triggers = getattr(job, "triggers", None)
        if triggers is None:
            continue
        webhooks = getattr(triggers, "webhooks", None) or ()
        if len(webhooks) > 0:
            return True
    return False


def invalidate_ingress_requirement_cache() -> None:
    """Clear cached snapshot after credential or cron mutations."""
    global _snapshot_cache
    _snapshot_cache = None


async def _evaluate_ingress_requirement() -> IngressRequirementSnapshot:
    ingress_url = await get_public_ingress_base_url()
    has_ingress = bool(ingress_url.strip())

    config_keys = {
        spec.config_key
        for spec in CHANNEL_INBOUND_SPECS.values()
        if spec.config_key
    }
    loaded = await asyncio.gather(*(_load_channel_credential(key) for key in config_keys))
    creds_by_key = dict(zip(config_keys, loaded, strict=True))

    channels: dict[str, IngressTransport] = {}
    reasons: list[str] = []

    for channel_name, spec in CHANNEL_INBOUND_SPECS.items():
        creds = creds_by_key.get(spec.config_key) if spec.config_key else None
        mode = resolve_channel_ingress_mode(channel_name, creds)
        if mode is not None:
            channels[channel_name] = mode
            if mode == "inbound" and not has_ingress:
                reasons.append(f"channel:{channel_name}")

    from app.config.deploy_mode import get_deployment_capabilities
    from app.services.channels.cp_egress_client import SAAS_CP_CHANNELS

    if get_deployment_capabilities().is_sandbox_instance and not has_ingress:
        from app.core.channel_bridge import channel_gateway

        for name in SAAS_CP_CHANNELS:
            if name in channel_gateway.bus.channels:
                channels.setdefault(name, "inbound")
                reasons.append(f"channel:{name}")

    if await _has_cron_webhook_triggers():
        if not has_ingress:
            reasons.append("cron:webhook")

    required = len(reasons) > 0
    return IngressRequirementSnapshot(
        required=required,
        has_public_ingress=has_ingress,
        reasons=tuple(dict.fromkeys(reasons)),
        channels=channels,
    )


async def resolve_ingress_requirement(*, force: bool = False) -> IngressRequirementSnapshot:
    global _snapshot_cache
    now = time.monotonic()
    if not force and _snapshot_cache is not None:
        cached_at, cached = _snapshot_cache
        if now - cached_at < _CACHE_TTL_SECONDS:
            return cached

    snapshot = await _evaluate_ingress_requirement()
    _snapshot_cache = (now, snapshot)
    return snapshot


def supplement_ingress_issues(
    channel_name: str,
    issues: list[ChannelIssue],
    snapshot: IngressRequirementSnapshot,
) -> list[ChannelIssue]:
    if snapshot.has_public_ingress:
        return issues
    mode = snapshot.channels.get(channel_name)
    if mode != "inbound":
        return issues
    if any(i.kind == IssueKind.CONFIG and "Ingress" in i.message for i in issues):
        return issues
    return [
        *issues,
        ChannelIssue(
            kind=IssueKind.CONFIG,
            severity=IssueSeverity.WARNING,
            message="Public Ingress is required for this channel but not configured.",
            fix=_INGRESS_FIX,
        ),
    ]
