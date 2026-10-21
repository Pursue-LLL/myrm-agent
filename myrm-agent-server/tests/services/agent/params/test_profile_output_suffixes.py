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


def test_renderer_failure_is_fail_open(monkeypatch) -> None:
    """风格渲染抛错时必须 fail-open：保留原指令、不注入风格块、不向上抛异常。"""
    import app.ai_agents.personality_templates as personality_templates

    def _boom(_style: str | None) -> str | None:
        raise RuntimeError("render boom")

    monkeypatch.setattr(personality_templates, "render_personality_block", _boom)

    result = apply_profile_output_suffixes("Base", personality_style="concise", agent_id="agent-x")

    assert result == "Base"


def test_default_style_without_locale_returns_input_unchanged() -> None:
    """默认风格且无 locale 策略时原样返回（覆盖 elif 的 False 分支）。"""
    result = apply_profile_output_suffixes("Base", personality_style="professional")

    assert result == "Base"
