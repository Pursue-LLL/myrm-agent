"""Architecture guard: meeting-minutes-extractor skill multi-connector declaration & preflight contract.

[INPUT]
- assets/prebuilt_skills/meeting-minutes-extractor/SKILL.md

[OUTPUT]
- Architecture tests ensuring meeting-minutes-extractor skill declares required_oauth_issuers
  and required_mcp_servers, and enforces minimal-mount and graceful degradation disciplines.

[POS]
Architecture test verifying the operational integrity and connector preflight stability of meeting-minutes-extractor.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_SKILL_MD = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "prebuilt_skills"
    / "meeting-minutes-extractor"
    / "SKILL.md"
)

_REQUIRED_OAUTH_ISSUERS = ("google_workspace",)
_REQUIRED_MCP_SERVERS = ("notion", "linear")

_CONTRACT_MARKERS = (
    "Connector Dependency Declaration",
    "Minimal-Mount Discipline",
    "Connector Preflight & Graceful Degradation",
    "Executive Summary",
    "Action Items Table",
)

_MAX_SKILL_CHARS = 12_000


@pytest.fixture(scope="module")
def skill_parts() -> tuple[dict, str]:
    if not _SKILL_MD.is_file():
        pytest.fail(f"Missing meeting-minutes-extractor skill: {_SKILL_MD}")
    content = _SKILL_MD.read_text(encoding="utf-8")
    assert content.startswith("---"), "SKILL.md must start with YAML frontmatter"
    parts = content.split("---", 2)
    assert len(parts) >= 3, "SKILL.md must contain valid closing frontmatter"
    frontmatter = yaml.safe_load(parts[1])
    body = parts[2]
    return frontmatter, body


def test_meeting_minutes_file_exists() -> None:
    assert _SKILL_MD.is_file(), f"File does not exist: {_SKILL_MD}"


def test_meeting_minutes_char_limit(skill_parts: tuple[dict, str]) -> None:
    _, body = skill_parts
    assert len(body) <= _MAX_SKILL_CHARS, (
        f"meeting-minutes-extractor body is {len(body)} chars, exceeding {_MAX_SKILL_CHARS}"
    )


def test_meeting_minutes_multi_connector_declaration(skill_parts: tuple[dict, str]) -> None:
    frontmatter, _ = skill_parts
    assert frontmatter.get("name") == "meeting-minutes-extractor"
    
    # Assert multi-issuer declaration
    declared_issuers = frontmatter.get("required_oauth_issuers") or []
    for issuer in _REQUIRED_OAUTH_ISSUERS:
        assert issuer in declared_issuers, f"Missing required_oauth_issuer: {issuer}"

    # Assert multi-mcp declaration
    declared_mcps = frontmatter.get("required_mcp_servers") or []
    for mcp in _REQUIRED_MCP_SERVERS:
        assert mcp in declared_mcps, f"Missing required_mcp_servers: {mcp}"


def test_meeting_minutes_contract_markers(skill_parts: tuple[dict, str]) -> None:
    _, body = skill_parts
    missing = [m for m in _CONTRACT_MARKERS if m not in body]
    assert not missing, f"meeting-minutes-extractor is missing contract markers: {missing}"
