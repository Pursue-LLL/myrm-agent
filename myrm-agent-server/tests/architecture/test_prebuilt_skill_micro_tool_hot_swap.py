"""Architecture test for micro-tool-hot-swap prebuilt skill asset."""

from __future__ import annotations

from pathlib import Path

import yaml

_SERVER_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = _SERVER_ROOT / "assets" / "prebuilt_skills" / "in-process-microtool-swapper" / "SKILL.md"


def test_micro_tool_hot_swap_asset_structure() -> None:
    assert SKILL_PATH.exists(), f"Skill file does not exist at {SKILL_PATH}"

    raw_text = SKILL_PATH.read_text(encoding="utf-8")
    parts = raw_text.split("---", 2)
    assert len(parts) >= 3, "Skill file must contain YAML frontmatter delimited by ---"

    frontmatter = yaml.safe_load(parts[1])
    assert frontmatter["name"] == "in-process-microtool-swapper"
    assert "description" in frontmatter and len(frontmatter["description"]) > 10
    assert frontmatter["version"] == "1.0.0"
    assert frontmatter["category"] == "engineering"
    assert "allowed-tools" in frontmatter

    body = parts[2]
    # Check 4 stages exist
    assert "Stage 1: Declarative Micro-Tool Authoring" in body
    assert "Stage 2: In-Memory Hot Registration & Shadowing" in body
    assert "Stage 3: Sub-Millisecond Dispatch & Telemetry" in body
    assert "Stage 4: Hot Unload & Reversion" in body

    # Check Dual-Track Matrix
    assert "Dual-Track Tool Architecture" in body
    assert "Track 1: In-Process Micro-Tool" in body
    assert "Track 2: External MCP / CLI" in body
