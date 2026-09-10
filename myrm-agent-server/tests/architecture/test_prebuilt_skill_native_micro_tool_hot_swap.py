"""Architecture guard: native-micro-tool-hot-swap skill must preserve its core operating contract.

[INPUT]
- assets/prebuilt_skills/native-micro-tool-hot-swap/SKILL.md

[OUTPUT]
- Architecture tests ensuring native-micro-tool-hot-swap skill retains dual-track architecture, 4 ToolLayers, and @agent_tool decorator schemas.

[POS]
Architecture test verifying the operational integrity and contract stability of the native-micro-tool-hot-swap prebuilt skill.
"""

from __future__ import annotations

from pathlib import Path
import pytest

_SKILL_MD = (
    Path(__file__).resolve().parents[3]
    / "assets"
    / "prebuilt_skills"
    / "native-micro-tool-hot-swap"
    / "SKILL.md"
)

_LAYER_MARKERS = (
    "Layer 1: CORE",
    "Layer 2: HIGH_PRIORITY",
    "Layer 3: EXTENDED",
    "Layer 4: EXTERNAL",
)

_SCHEMA_MARKERS = (
    "Dual-Track Architecture Comparison",
    "@agent_tool",
    "Standard Execution SOP",
)

_MAX_SKILL_CHARS = 12_000


@pytest.fixture(scope="module")
def skill_text() -> str:
    if not _SKILL_MD.is_file():
        pytest.fail(f"Missing native-micro-tool-hot-swap skill: {_SKILL_MD}")
    return _SKILL_MD.read_text(encoding="utf-8")


def test_native_micro_tool_hot_swap_file_exists() -> None:
    assert _SKILL_MD.is_file(), f"File does not exist: {_SKILL_MD}"


def test_native_micro_tool_hot_swap_char_limit(skill_text: str) -> None:
    assert len(skill_text) <= _MAX_SKILL_CHARS, (
        f"native-micro-tool-hot-swap SKILL.md is {len(skill_text)} chars, exceeding {_MAX_SKILL_CHARS}"
    )


def test_native_micro_tool_hot_swap_contains_layer_markers(skill_text: str) -> None:
    missing = [l for l in _LAYER_MARKERS if l not in skill_text]
    assert not missing, f"native-micro-tool-hot-swap SKILL.md is missing layer markers: {missing}"


def test_native_micro_tool_hot_swap_contains_schema_markers(skill_text: str) -> None:
    missing = [s for s in _SCHEMA_MARKERS if s not in skill_text]
    assert not missing, f"native-micro-tool-hot-swap SKILL.md is missing schema markers: {missing}"
