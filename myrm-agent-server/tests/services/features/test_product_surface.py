"""Product surface SSOT tests."""

from __future__ import annotations

from app.services.features.product_surface import (
    HIDDEN_BUILTIN_AGENT_IDS,
    HIDDEN_PREBUILT_TEMPLATE_IDS,
    is_hidden_builtin_agent,
    is_hidden_prebuilt_template,
)


def test_hidden_builtin_agent_ids() -> None:
    assert "builtin-researcher" in HIDDEN_BUILTIN_AGENT_IDS
    assert "builtin-deep-search" in HIDDEN_BUILTIN_AGENT_IDS
    assert is_hidden_builtin_agent("builtin-researcher")
    assert not is_hidden_builtin_agent("builtin-general")


def test_hidden_prebuilt_template_ids() -> None:
    assert "research_analysis_squad" in HIDDEN_PREBUILT_TEMPLATE_IDS
    assert is_hidden_prebuilt_template("research_analysis_squad")
    assert not is_hidden_prebuilt_template("general_assistant")
