"""Built-in agents that carry a communication style carry its text in their system prompt."""

from __future__ import annotations

import pytest

from app.services.agent.builtin_agent_specs import _BUILTIN_AGENTS
from app.services.agent.builtin_specs.concise_reply_style import CONCISE_REPLY_STYLE

# One sentence of each style text; every agent below must carry exactly one of them, in the style it was built with.
_CREATIVE = "Think outside the box."
_DETAILED = "Provide comprehensive, detailed explanations."
_FRIENDLY = "Be warm, friendly, and encouraging."

_STYLE_TEXT_BY_AGENT: dict[str, str] = {
    **dict.fromkeys(("builtin-writer", "builtin-newsletter", "builtin-designer", "builtin-video-studio"), _CREATIVE),
    **dict.fromkeys(("builtin-researcher", "builtin-data-analyst", "builtin-seo", "builtin-social_intelligence"), _DETAILED),
    **dict.fromkeys(("builtin-social-media", "builtin-tutor", "builtin-career", "builtin-travel"), _FRIENDLY),
    **dict.fromkeys(
        ("builtin-developer", "builtin-economy", "builtin-meeting", "builtin-automation", "builtin-cli_visual"),
        CONCISE_REPLY_STYLE,
    ),
}
_ALL_STYLE_TEXTS = (_CREATIVE, _DETAILED, _FRIENDLY, CONCISE_REPLY_STYLE)
_PROMPT_BY_ID = {spec.id: spec.system_prompt for spec in _BUILTIN_AGENTS}


@pytest.mark.parametrize(("agent_id", "style_text"), sorted(_STYLE_TEXT_BY_AGENT.items()))
def test_agent_carries_its_style_text_once(agent_id: str, style_text: str) -> None:
    assert _PROMPT_BY_ID[agent_id].count(style_text) == 1
    other_texts = [text for text in _ALL_STYLE_TEXTS if text != style_text]
    assert not [text for text in other_texts if text in _PROMPT_BY_ID[agent_id]]


def test_other_agents_carry_no_style_text() -> None:
    styled = [
        agent_id
        for agent_id, prompt in _PROMPT_BY_ID.items()
        if agent_id not in _STYLE_TEXT_BY_AGENT and any(text in prompt for text in _ALL_STYLE_TEXTS)
    ]
    assert not styled


def test_no_builtin_prompt_carries_the_communication_style_block() -> None:
    assert not [agent_id for agent_id, prompt in _PROMPT_BY_ID.items() if "Communication Style" in prompt]


def test_concise_style_is_scoped_to_chat_replies() -> None:
    """Terse wording must not leak into files, commits, or messages written for other people."""
    assert CONCISE_REPLY_STYLE.startswith("The terse style below applies to your chat replies only")
