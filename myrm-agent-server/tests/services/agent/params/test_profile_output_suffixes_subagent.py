"""Subagent path: locale suffix without duplicating personality on system_prompt."""

from app.services.agent.params.profile_output_suffixes import apply_profile_output_suffixes


def test_locale_only_when_personality_style_none() -> None:
    """Subagents apply personality on system_prompt; suffix adds locale only."""
    result = apply_profile_output_suffixes(
        "Subagent base prompt",
        personality_style=None,
        engine_params={
            "response_locale_policy": {
                "locale": "ko-KR",
                "formality": "formal-polite",
            }
        },
    )
    assert result is not None
    assert result.startswith("Subagent base prompt")
    assert "합니다" in result
    assert "**Communication Style**" not in result
