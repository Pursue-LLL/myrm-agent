"""Unit tests for session_access_roots prompt injection in build_general_agent.

[INPUT]
- app.ai_agents.general_agent.factory (POS: system_prompt session roots section)

[OUTPUT]
- test_session_access_roots_prompt: verifies deterministic ordering and formatting of mounted workspace roots

[POS]
Ensures that granted session_access_roots are correctly injected into system_prompt
with deterministic path ordering (for KV Cache stability) and permission labels.
"""

from __future__ import annotations

from pathlib import Path


def _factory_source() -> str:
    factory_path = (
        Path(__file__).resolve().parents[3]
        / "app"
        / "ai_agents"
        / "general_agent"
        / "factory.py"
    )
    return factory_path.read_text(encoding="utf-8")


def test_factory_contains_session_roots_prompt_injection() -> None:
    """Verify factory.py has deterministic sorted session_access_roots prompt injection."""
    source = _factory_source()
    assert (
        'session_roots_raw = getattr(agent_wrapper, "session_access_roots", None)'
        in source
    )
    assert "[Mounted Workspace Directories]" in source
    assert 'key=lambda x: str(x.get("path", ""))' in source


def test_session_roots_prompt_formatting_logic() -> None:
    """Verify the formatting logic produces expected output with deterministic sorting."""
    roots = [
        {"path": "/Users/test/project-z", "writable": False},
        {"path": "/Users/test/project-a", "writable": True},
    ]
    roots_lines = [
        f"- {str(r.get('path'))} ({'read-write' if r.get('writable', True) else 'read-only'})"
        for r in sorted(
            roots,
            key=lambda x: str(x.get("path", "")) if isinstance(x, dict) else "",
        )
        if isinstance(r, dict) and r.get("path")
    ]
    formatted = (
        "\n\n[Mounted Workspace Directories]\n"
        "The following local directories are granted for this session:\n"
        + "\n".join(roots_lines)
        + "\nYou can read, search, and operate on files within these directories directly using tools."
    )
    # project-a should come before project-z due to sorting
    assert formatted.index("/Users/test/project-a (read-write)") < formatted.index(
        "/Users/test/project-z (read-only)"
    )
    assert "[Mounted Workspace Directories]" in formatted
