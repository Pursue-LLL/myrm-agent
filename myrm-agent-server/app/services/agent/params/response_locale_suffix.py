"""Response-locale suffix injection.

[INPUT]
- myrm_agent_harness.utils.response_locale::build_response_locale_suffix (POS: Agent output locale/formality suffix from engine_params)

[OUTPUT]
- apply_response_locale_suffix(): append the response-locale suffix to the user_instructions tail
  (prompt-cache safe; not system_prompt prefix).

[POS]
Server SSOT for the profile-driven response language constraint. Used by Web, Channel, Cron,
Kanban, Eval, Voice (agent_bridge + realtime + gemini_live), Subagent, and
Goal stream continuation entry points.
"""

from __future__ import annotations

from myrm_agent_harness.utils.response_locale import build_response_locale_suffix


def apply_response_locale_suffix(
    user_instructions: str | None,
    *,
    engine_params: dict[str, object] | None,
) -> str | None:
    """Append the response-locale suffix to the user_instructions tail."""
    locale_suffix = build_response_locale_suffix(engine_params)
    if not locale_suffix:
        return user_instructions
    return f"{user_instructions}{locale_suffix}" if user_instructions else locale_suffix.strip()
