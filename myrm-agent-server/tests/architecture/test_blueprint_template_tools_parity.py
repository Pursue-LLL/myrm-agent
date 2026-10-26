"""Architecture test: the JIT team blueprints in the chat config panel name real tools and never inherit everything."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from myrm_agent_harness.core.security.tool_registry import TOOL_TO_GROUP

_MYRM_AGENT_ROOT = Path(__file__).resolve().parents[3]
_PANEL = (
    _MYRM_AGENT_ROOT
    / "myrm-agent-frontend"
    / "src"
    / "components"
    / "features"
    / "chat-window"
    / "agent-config-panel"
    / "AgentConfigPanel.tsx"
)

_TEMPLATES_BLOCK = re.compile(r"const BLUEPRINT_TEMPLATES = \[(.*?)\n\];", re.DOTALL)
_MEMBER_NAME = re.compile(r"^ {6}(\w+): \{$", re.MULTILINE)
_TOOLS_LIST = re.compile(r"tools:\s*\[([^\]]*)\]")
_QUOTED = re.compile(r"'([^']+)'")


def _blueprint_block() -> str:
    assert _PANEL.is_file(), f"Missing frontend panel file: {_PANEL}"
    match = _TEMPLATES_BLOCK.search(_PANEL.read_text(encoding="utf-8"))
    assert match, "BLUEPRINT_TEMPLATES block not found in AgentConfigPanel.tsx"
    return match.group(1)


def _members() -> list[str]:
    return _MEMBER_NAME.findall(_blueprint_block())


def _allowlists() -> list[list[str]]:
    return [_QUOTED.findall(raw) for raw in _TOOLS_LIST.findall(_blueprint_block())]


@pytest.mark.architecture
def test_blueprint_scan_finds_every_member() -> None:
    """Calibration: a pattern that stopped matching would turn the checks below into no-ops."""
    members = _members()
    assert len(members) >= 4, f"Expected the shipped blueprint members, found {members}"
    assert len(_allowlists()) == len(members), "Every blueprint member must declare a `tools` list"


@pytest.mark.architecture
def test_blueprint_members_declare_an_explicit_allowlist() -> None:
    """An empty `tools` list means "inherit every parent tool", which is not what a synthesiser should get."""
    empty = [member for member, allowed in zip(_members(), _allowlists(), strict=True) if not allowed]
    assert not empty, f"Blueprint members with an empty tools allowlist inherit every parent tool: {empty}"


@pytest.mark.architecture
def test_blueprint_tools_are_registered_harness_tools() -> None:
    """The child filter matches exact tool names; a UI-style name such as `web_search` leaves the child with no tool."""
    unknown = sorted({name for allowed in _allowlists() for name in allowed} - set(TOOL_TO_GROUP))
    assert not unknown, f"Blueprint tools that are not registered harness tool names: {unknown}"
