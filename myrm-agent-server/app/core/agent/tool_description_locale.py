"""Resolve BCP-47 locale for harness LLM tool descriptions.

[INPUT]
- myrm_agent_harness.utils.locale::resolve_locale (POS: shared locale string handling)

[OUTPUT]
- resolve_agent_params_locale: BCP-47 locale for GeneralAgentParams and tool descriptions
- resolve_tool_description_locale: BCP-47 locale for harness tool description SSOT

[POS]
Server bridge for Turn1 tool schema locale. Binds agent/channel locale into harness
``description_locale`` without duplicating locale priority rules.
"""

from __future__ import annotations

from myrm_agent_harness.utils.locale import resolve_locale


def resolve_agent_params_locale(
    *,
    explicit: str | None = None,
    personal_settings: dict[str, object] | None = None,
    channel: str | None = None,
) -> str:
    """Resolve locale for ``GeneralAgentParams.locale`` and harness tool descriptions."""
    user_locale: str | None = None
    if personal_settings:
        for key in ("locale", "language"):
            raw = personal_settings.get(key)
            if raw:
                user_locale = str(raw)
                break
    return resolve_locale(
        explicit=explicit,
        user_locale=user_locale,
        channel=channel,
    )


def resolve_tool_description_locale(
    *,
    agent_locale: str | None = None,
    user_locale: str | None = None,
    channel: str | None = None,
) -> str:
    """Resolve locale for memory/web_search/web_fetch/cron tool description SSOT."""
    return resolve_agent_params_locale(
        explicit=agent_locale,
        personal_settings={"locale": user_locale} if user_locale else None,
        channel=channel,
    )
