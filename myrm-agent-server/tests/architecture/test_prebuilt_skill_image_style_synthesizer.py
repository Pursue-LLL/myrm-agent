"""Architecture guard: image-style-synthesizer skill must preserve its core operating contract.

[INPUT]
- assets/prebuilt_skills/image-style-synthesizer/SKILL.md

[OUTPUT]
- Architecture tests ensuring image-style-synthesizer skill retains 6D visual schema, typography gate, commercial presets, and tool invocation contracts

[POS]
Architecture test verifying the operational integrity and contract stability of the image-style-synthesizer prebuilt skill.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_SKILL_MD = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "prebuilt_skills"
    / "image-style-synthesizer"
    / "SKILL.md"
)

_CONTRACT_MARKERS = (
    # Core operating dimensions
    "Visual Intent Extraction",
    "Atomic Schema Compilation",
    "Typography & Negative Safety Gating",
    "Image Tool Invocation",
    # Specific schema fields
    "subject:",
    "style:",
    "lighting:",
    "material:",
    "composition:",
    "negative:",
    # Commercial presets
    "3D Claymorphism / Neumorphism",
    "Enterprise Isometric Tech",
    "Minimalist Flat Vector",
    # Typography & safety gating rules
    "Typography Restriction Gate",
    "<= 3 words",
    # Tool declarations in frontmatter
    "image_tool",
    "file_write_tool",
)

_MAX_SKILL_CHARS = 12_000


@pytest.fixture(scope="module")
def skill_text() -> str:
    if not _SKILL_MD.is_file():
        pytest.fail(f"Missing image-style-synthesizer skill: {_SKILL_MD}")
    return _SKILL_MD.read_text(encoding="utf-8")


@pytest.mark.architecture
def test_frontmatter_declares_skill_name(skill_text: str) -> None:
    assert "name: image-style-synthesizer" in skill_text


@pytest.mark.architecture
def test_frontmatter_has_description(skill_text: str) -> None:
    assert "description:" in skill_text
    assert "prompt-as-code" in skill_text.split("description:")[1][:250].lower()


@pytest.mark.architecture
def test_frontmatter_declares_semver_version(skill_text: str) -> None:
    assert re.search(r"^version: \d+\.\d+\.\d+$", skill_text, re.MULTILINE), (
        "image-style-synthesizer SKILL.md must declare a semver 'version: x.y.z'"
    )


@pytest.mark.architecture
@pytest.mark.parametrize("marker", _CONTRACT_MARKERS)
def test_contract_marker_present(skill_text: str, marker: str) -> None:
    assert marker in skill_text, (
        f"Required contract marker missing from image-style-synthesizer SKILL.md: {marker!r}"
    )


@pytest.mark.architecture
def test_skill_size_within_budget(skill_text: str) -> None:
    assert len(skill_text) <= _MAX_SKILL_CHARS, (
        f"image-style-synthesizer SKILL.md is {len(skill_text)} chars, exceeding budget {_MAX_SKILL_CHARS}"
    )


@pytest.mark.architecture
def test_channel_router_design_image_command_registered() -> None:
    from app.channels.routing.command_defs import SYSTEM_COMMANDS, CommandKind

    design_cmd = next((c for c in SYSTEM_COMMANDS if c.name == "design-image"), None)
    assert design_cmd is not None, "Missing /design-image command in SYSTEM_COMMANDS"
    assert design_cmd.kind == CommandKind.SKILL
    assert "image-style-synthesizer" in design_cmd.skill_ids
    assert "image-design" in design_cmd.aliases
    assert "prompt-image" in design_cmd.aliases
    assert "style-image" in design_cmd.aliases
