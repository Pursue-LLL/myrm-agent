"""Tests for apply_profile_output_suffixes."""

from app.services.agent.params.profile_output_suffixes import apply_profile_output_suffixes


def test_empty_instructions_ko_formal_only() -> None:
    result = apply_profile_output_suffixes(
        None,
        engine_params={
            "response_locale_policy": {
                "locale": "ko-KR",
                "formality": "formal-polite",
            }
        },
    )
    assert result is not None
    assert "합니다" in result


def test_appends_personality_then_locale() -> None:
    result = apply_profile_output_suffixes(
        "Base prompt",
        personality_style="concise",
        engine_params={
            "response_locale_policy": {
                "locale": "ko-KR",
                "formality": "formal-polite",
            }
        },
    )
    assert result is not None
    assert result.startswith("Base prompt")
    assert "**Communication Style**" in result
    assert result.index("Communication Style") < result.index("합니다")


def test_default_personality_skipped() -> None:
    result = apply_profile_output_suffixes(
        "Only base",
        personality_style="default",
        engine_params=None,
    )
    assert result == "Only base"


def test_invalid_personality_preserves_locale() -> None:
    result = apply_profile_output_suffixes(
        "Base",
        personality_style="nonexistent-style",
        engine_params={"response_locale_policy": {"locale": "ko", "formality": "casual"}},
        agent_id="agent-1",
    )
    assert result is not None
    assert "conversational" in result
    assert "**Communication Style**" not in result
