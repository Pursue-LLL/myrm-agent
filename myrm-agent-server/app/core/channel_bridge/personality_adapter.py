"""Personality provider adapter for the channel routing layer.

Bridges business-layer personality templates to the framework-layer
PersonalityProvider protocol used by AgentRouter's /personality command.
"""

from __future__ import annotations

from app.ai_agents.personality_templates import (
    PERSONALITY_TEMPLATES,
    PersonalityStyle,
    PersonalityTemplate,
)


class AppPersonalityProvider:
    """Adapts business-layer PersonalityTemplate to framework-layer PersonalityProvider protocol."""

    def list_all(self) -> list[PersonalityTemplate]:
        return list(PERSONALITY_TEMPLATES.values())

    def get(self, style: str) -> PersonalityTemplate | None:
        if style not in PERSONALITY_TEMPLATES:
            return None
        key: PersonalityStyle = style  # narrowed by membership on Literal-keyed dict
        return PERSONALITY_TEMPLATES[key]

