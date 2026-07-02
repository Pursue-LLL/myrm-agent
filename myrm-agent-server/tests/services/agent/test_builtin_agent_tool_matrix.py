"""Built-in agent tool matrix regression tests."""

from __future__ import annotations

from app.services.agent.builtin_initializer import (
    _BUILTIN_AGENTS,
    _TOOL_CODING,
    _TOOL_DESIGN,
    _TOOL_MINIMAL,
    _TOOL_RESEARCH,
)


def test_all_builtin_agents_declare_enabled_tools() -> None:
    missing = [spec.id for spec in _BUILTIN_AGENTS if spec.enabled_builtin_tools is None]
    assert missing == [], f"Builtin agents missing enabled_builtin_tools: {missing}"


def test_developer_has_shell_and_file_ops() -> None:
    developer = next(spec for spec in _BUILTIN_AGENTS if spec.id == "builtin-developer")
    assert developer.enabled_builtin_tools == _TOOL_CODING
    assert "code_execute" in developer.enabled_builtin_tools
    assert "file_ops" in developer.enabled_builtin_tools


def test_designer_uses_canonical_image_generation_id() -> None:
    designer = next(spec for spec in _BUILTIN_AGENTS if spec.id == "builtin-designer")
    assert designer.enabled_builtin_tools == _TOOL_DESIGN
    assert "image_generation" in designer.enabled_builtin_tools
    assert "image_gen" not in (designer.enabled_builtin_tools or ())


def test_cli_visual_matches_coding_tools() -> None:
    cli = next(spec for spec in _BUILTIN_AGENTS if spec.id == "builtin-cli_visual")
    assert cli.enabled_builtin_tools == _TOOL_CODING


def test_research_analyst_has_answer_tool() -> None:
    researcher = next(spec for spec in _BUILTIN_AGENTS if spec.id == "builtin-researcher")
    assert researcher.enabled_builtin_tools == _TOOL_RESEARCH


def test_general_assistant_stays_minimal() -> None:
    general = next(spec for spec in _BUILTIN_AGENTS if spec.id == "builtin-general")
    assert general.enabled_builtin_tools == _TOOL_MINIMAL
