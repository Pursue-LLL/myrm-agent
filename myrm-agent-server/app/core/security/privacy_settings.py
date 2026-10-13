"""Privacy protection read from the persisted personal settings.

[INPUT]
- app.core.security.pii_actions::coerce_pii_action (POS: safe parsing of a persisted PII action)
- myrm_agent_harness.agent.security.types::PIIAction, PrivacyPolicy (POS: PII action enum and the policy a run enforces)

[OUTPUT]
- PrivacyAgentParams: the GeneralAgentParams privacy fields the persisted settings can supply
- privacy_enabled: whether the persisted settings turn privacy protection on
- privacy_agent_params: the privacy fields for a run that has no web request
- resolve_privacy_params: the privacy fields for a run whose request may carry some of them
- privacy_policy_from_settings: the PrivacyPolicy the persisted settings describe, None while protection is off

[POS]
Business-layer reader of the persisted personal settings for privacy protection: the switch, actions, custom rules and
deep-scan choice, for runs the server starts itself and for requests that carry only some of them. Local-model routing
stays request-only.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TypedDict

from myrm_agent_harness.agent.security.types import PIIAction, PrivacyPolicy

from app.core.security.pii_actions import coerce_pii_action


class PrivacyAgentParams(TypedDict, total=False):
    privacy_enabled: bool
    privacy_s2_action: str
    privacy_s3_action: str
    privacy_deep_scan: bool
    privacy_custom_keywords_s2: list[str]
    privacy_custom_keywords_s3: list[str]
    privacy_custom_patterns_s2: list[str]
    privacy_custom_patterns_s3: list[str]
    privacy_sensitive_tools_s2: list[str]
    privacy_sensitive_tools_s3: list[str]


def privacy_enabled(personal_settings: Mapping[str, object] | None) -> bool:
    """True only for an explicit ``privacyEnabled: true``; a missing or malformed value leaves protection off."""
    return personal_settings is not None and personal_settings.get("privacyEnabled") is True


def _strings(value: object) -> list[str]:
    """The non-empty strings of a persisted rule list; anything else is no rules rather than a crashed run."""
    return [item for item in value if isinstance(item, str) and item] if isinstance(value, list) else []


def _params_from_settings(personal_settings: Mapping[str, object] | None) -> PrivacyAgentParams:
    """Every privacy field the settings describe, whether or not protection is on."""
    settings = personal_settings or {}
    return {
        "privacy_enabled": privacy_enabled(settings),
        "privacy_s2_action": coerce_pii_action(settings.get("privacyS2Action"), PIIAction.WARN).value,
        "privacy_s3_action": coerce_pii_action(settings.get("privacyS3Action"), PIIAction.REDACT).value,
        "privacy_deep_scan": settings.get("privacyDeepScan") is True,
        "privacy_custom_keywords_s2": _strings(settings.get("privacyCustomKeywordsS2")),
        "privacy_custom_keywords_s3": _strings(settings.get("privacyCustomKeywordsS3")),
        "privacy_custom_patterns_s2": _strings(settings.get("privacyCustomPatternsS2")),
        "privacy_custom_patterns_s3": _strings(settings.get("privacyCustomPatternsS3")),
        "privacy_sensitive_tools_s2": _strings(settings.get("privacySensitiveToolsS2")),
        "privacy_sensitive_tools_s3": _strings(settings.get("privacySensitiveToolsS3")),
    }


def privacy_agent_params(personal_settings: Mapping[str, object] | None) -> PrivacyAgentParams:
    """Privacy fields for ``GeneralAgentParams``; empty when protection is off so the field defaults apply."""
    params = _params_from_settings(personal_settings)
    return params if params["privacy_enabled"] else {}


def resolve_privacy_params(personal_settings: Mapping[str, object] | None, requested: PrivacyAgentParams) -> PrivacyAgentParams:
    """Privacy fields for a run: the persisted settings, overlaid by every field the request itself carried.

    What a request says wins, so a client can choose its own actions or switch protection off for one call; what it
    leaves unsaid follows the settings, so a client that sends nothing is still protected. The deep-scan choice
    outlives the master switch: goal-learning extraction reads it with protection off too.
    """
    merged: PrivacyAgentParams = {**_params_from_settings(personal_settings), **requested}
    return merged if merged["privacy_enabled"] else {"privacy_deep_scan": merged["privacy_deep_scan"]}


def privacy_policy_from_settings(personal_settings: Mapping[str, object] | None) -> PrivacyPolicy | None:
    """The policy the persisted settings describe; None while protection is off."""
    params = privacy_agent_params(personal_settings)
    if not params:
        return None
    return PrivacyPolicy(
        enabled=True,
        s2_action=PIIAction(params["privacy_s2_action"]),
        s3_action=PIIAction(params["privacy_s3_action"]),
        deep_scan=params["privacy_deep_scan"],
        custom_keywords_s2=tuple(params["privacy_custom_keywords_s2"]),
        custom_keywords_s3=tuple(params["privacy_custom_keywords_s3"]),
        custom_patterns_s2=tuple(params["privacy_custom_patterns_s2"]),
        custom_patterns_s3=tuple(params["privacy_custom_patterns_s3"]),
        sensitive_tools_s2=tuple(params["privacy_sensitive_tools_s2"]),
        sensitive_tools_s3=tuple(params["privacy_sensitive_tools_s3"]),
    )


__all__ = [
    "PrivacyAgentParams",
    "privacy_agent_params",
    "privacy_enabled",
    "privacy_policy_from_settings",
    "resolve_privacy_params",
]
