"""Resolve BCP-47 locale for harness LLM tool descriptions.

[INPUT]
- myrm_agent_harness.utils.locale::resolve_locale (POS: shared locale string handling)

[OUTPUT]
- resolve_tool_description_locale: BCP-47 locale for harness tool description SSOT

[POS]
Server bridge for Turn1 tool schema locale. Binds agent/channel locale into harness
``description_locale`` without duplicating locale priority rules.
"""

from __future__ import annotations

from myrm_agent_harness.utils.locale import resolve_locale


def resolve_tool_description_locale(
    *,
    agent_locale: str | None = None,
    user_locale: str | None = None,
    channel: str | None = None,
) -> str:
    """Resolve locale for memory/web_search tool description SSOT."""
    return resolve_locale(
        explicit=agent_locale,
        user_locale=user_locale,
        channel=channel,
    )
