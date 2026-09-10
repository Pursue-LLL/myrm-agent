"""Architecture test for micro-tool-hot-swap prebuilt skill asset."""

from __future__ import annotations

from pathlib import Path

import yaml

SKILL_PATH = Path("assets/prebuilt_skills/micro-tool-hot-swap/SKILL.md")


def test_micro_tool_hot_swap_asset_structure() -> None:
    assert SKILL_PATH.exists(), f"Skill file does not exist at {SKILL_PATH}"

    raw_text = SKILL_PATH.read_text(encoding="utf-8")
    parts = raw_text.split("---", 2)
    assert len(parts) >= 3, "Skill file must contain YAML frontmatter delimited by ---"

    frontmatter = yaml.safe_load(parts[1])
    assert frontmatter["name"] == "micro-tool-hot-swap"
    assert "description" in frontmatter and len(frontmatter["description"]) > 10
    assert frontmatter["version"] == "1.0.0"
    assert frontmatter["category"] == "engineering"
    assert "allowed-tools" in frontmatter

    body = parts[2]
    # Check 4 stages exist
    assert "Stage 1: Functional Schema Declaration" in body
    assert "Stage 2: Dynamic In-Process Mounting" in body
    assert "Stage 3: Sub-Millisecond Execution & Routing" in body
    assert "Stage 4: Dynamic Hot-Swap & Unmount" in body

    # Check Dual-Track Matrix
    assert "Dual-Track Dispatch Matrix" in body
    assert "Track 1: External MCP Server" in body
    assert "Track 2: Native Micro-Tool" in body
