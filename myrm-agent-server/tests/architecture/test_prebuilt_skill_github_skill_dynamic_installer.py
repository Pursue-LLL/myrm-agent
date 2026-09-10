"""Architecture guard: github-skill-dynamic-installer skill contract & sandbox audit integrity.

[INPUT]
- assets/prebuilt_skills/github-skill-dynamic-installer/SKILL.md

[OUTPUT]
- Architecture tests ensuring github-skill-dynamic-installer retains the 4-phase installation SOP,
  4 mandatory security gates, frontmatter contract validation, and zero-config dynamic hot-mounting receipt.

[POS]
Architecture test verifying the operational integrity and contract stability of github-skill-dynamic-installer.
"""

from __future__ import annotations

from pathlib import Path
import pytest
import yaml

_SKILL_MD = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "prebuilt_skills"
    / "github-skill-dynamic-installer"
    / "SKILL.md"
)

_CORE_SECURITY_GATES = (
    "Command Safety",
    "Secret Leak Prevention",
    "Prompt Injection Defense",
    "ID Collision Gate",
)

_CONTRACT_MARKERS = (
    "Phase 1: URL Validation & Ephemeral Ingestion",
    "Phase 2: Multi-Layer Security & Static Audit",
    "Phase 3: Frontmatter Schema & Contract Validation",
    "Phase 4: Dynamic Hot-Mounting & Registry Activation",
    "Ephemeral Shallow Clone",
    "Zero-config",
)

_MAX_SKILL_CHARS = 12_000


@pytest.fixture(scope="module")
def skill_parts() -> tuple[dict, str]:
    if not _SKILL_MD.is_file():
        pytest.fail(f"Missing github-skill-dynamic-installer skill: {_SKILL_MD}")
    content = _SKILL_MD.read_text(encoding="utf-8")
    assert content.startswith("---"), "SKILL.md must start with YAML frontmatter"
    parts = content.split("---", 2)
    assert len(parts) >= 3, "SKILL.md must contain valid closing frontmatter"
    frontmatter = yaml.safe_load(parts[1])
    body = parts[2]
    return frontmatter, body


def test_github_installer_file_exists() -> None:
    assert _SKILL_MD.is_file(), f"File does not exist: {_SKILL_MD}"


def test_github_installer_char_limit(skill_parts: tuple[dict, str]) -> None:
    _, body = skill_parts
    assert len(body) <= _MAX_SKILL_CHARS, (
        f"github-skill-dynamic-installer body is {len(body)} chars, exceeding {_MAX_SKILL_CHARS}"
    )


def test_github_installer_frontmatter(skill_parts: tuple[dict, str]) -> None:
    frontmatter, _ = skill_parts
    assert frontmatter.get("name") == "github-skill-dynamic-installer"
    assert frontmatter.get("version") == "1.0.0"
    tags = frontmatter.get("tags") or []
    assert "github-installer" in tags or "skill-installer" in tags
    contract = frontmatter.get("contract") or {}
    assert "steps" in contract and len(contract["steps"]) >= 4
    assert "potential_traps" in contract and len(contract["potential_traps"]) >= 2
    assert "verification_steps" in contract and len(contract["verification_steps"]) >= 2


def test_github_installer_security_gates(skill_parts: tuple[dict, str]) -> None:
    _, body = skill_parts
    missing = [gate for gate in _CORE_SECURITY_GATES if gate not in body]
    assert not missing, f"github-skill-dynamic-installer is missing security gates: {missing}"


def test_github_installer_contract_markers(skill_parts: tuple[dict, str]) -> None:
    _, body = skill_parts
    missing = [m for m in _CONTRACT_MARKERS if m not in body]
    assert not missing, f"github-skill-dynamic-installer is missing contract markers: {missing}"
