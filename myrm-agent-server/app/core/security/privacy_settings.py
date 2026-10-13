"""Privacy protection read from the persisted personal settings.

[INPUT]
- app.core.security.pii_actions::coerce_pii_action (POS: safe parsing of a persisted PII action)
- myrm_agent_harness.api.security::redact_pii (POS: type-aware PII masking)
- myrm_agent_harness.agent.security.types::PIIAction (POS: PII action enum)

[OUTPUT]
- PrivacyAgentParams: the GeneralAgentParams privacy fields the persisted settings can supply
- privacy_enabled: whether the persisted settings turn privacy protection on
- privacy_agent_params: the privacy fields for a run that has no web request
- mask_pii_when_enabled: mask PII in text bound for an auxiliary LLM call when protection is on

[POS]
Business-layer bridge from the persisted personal settings to privacy protection. The web chat carries the settings
in every request; a run started by the server (IM channel, cron, voice, goal, wakeup) and every auxiliary LLM call
(chat title, follow-up suggestions, offline compaction) has no request, so they read the same switch and actions
here. Only the four persisted fields are available to them (enabled, S2 action, S3 action, deep scan); custom
keywords, patterns, sensitive tools and local-model routing stay request-only.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TypedDict

from myrm_agent_harness.agent.security.types import PIIAction
from myrm_agent_harness.api.security import redact_pii

from app.core.security.pii_actions import coerce_pii_action


class PrivacyAgentParams(TypedDict, total=False):
    privacy_enabled: bool
    privacy_s2_action: str
    privacy_s3_action: str
    privacy_deep_scan: bool


def privacy_enabled(personal_settings: Mapping[str, object] | None) -> bool:
    """True only for an explicit ``privacyEnabled: true``; a missing or malformed value leaves protection off."""
    return personal_settings is not None and personal_settings.get("privacyEnabled") is True


def privacy_agent_params(personal_settings: Mapping[str, object] | None) -> PrivacyAgentParams:
    """Privacy fields for ``GeneralAgentParams``; empty when protection is off so the field defaults apply."""
    if personal_settings is None or not privacy_enabled(personal_settings):
        return {}
    return {
        "privacy_enabled": True,
        "privacy_s2_action": coerce_pii_action(personal_settings.get("privacyS2Action"), PIIAction.WARN).value,
        "privacy_s3_action": coerce_pii_action(personal_settings.get("privacyS3Action"), PIIAction.REDACT).value,
        "privacy_deep_scan": personal_settings.get("privacyDeepScan") is True,
    }


def mask_pii_when_enabled(text: str, personal_settings: Mapping[str, object] | None) -> str:
    """Mask PII (and credentials) in ``text`` when protection is on; an auxiliary call cannot ask the user, so every
    action masks."""
    if not privacy_enabled(personal_settings):
        return text
    return redact_pii(text)[0]


__all__ = ["PrivacyAgentParams", "mask_pii_when_enabled", "privacy_agent_params", "privacy_enabled"]
