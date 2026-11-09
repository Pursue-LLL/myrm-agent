"""Tests for apply_response_locale_suffix."""

from app.services.agent.params.response_locale_suffix import apply_response_locale_suffix

_KO_FORMAL: dict[str, object] = {"response_locale_policy": {"locale": "ko-KR", "formality": "formal-polite"}}


def test_empty_instructions_get_the_locale_suffix_only() -> None:
    result = apply_response_locale_suffix(None, engine_params=_KO_FORMAL)

    assert result is not None
    assert "합니다" in result


def test_suffix_follows_the_existing_instructions() -> None:
    result = apply_response_locale_suffix("Base prompt", engine_params=_KO_FORMAL)

    assert result is not None
    assert result.startswith("Base prompt")
    assert "합니다" in result


def test_casual_policy_is_rendered() -> None:
    result = apply_response_locale_suffix(
        "Base",
        engine_params={"response_locale_policy": {"locale": "ko", "formality": "casual"}},
    )

    assert result is not None
    assert "conversational" in result


def test_without_locale_policy_instructions_are_returned_unchanged() -> None:
    assert apply_response_locale_suffix("Base", engine_params=None) == "Base"
    assert apply_response_locale_suffix("Base", engine_params={}) == "Base"
    assert apply_response_locale_suffix(None, engine_params=None) is None
