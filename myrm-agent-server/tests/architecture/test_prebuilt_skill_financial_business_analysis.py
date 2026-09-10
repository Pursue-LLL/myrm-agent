"""Architecture guard: financial-business-analysis skill must preserve its core operating contract.

[INPUT]
- assets/prebuilt_skills/financial-business-analysis/SKILL.md

[OUTPUT]
- Architecture tests ensuring financial-business-analysis skill retains official-source gate,
  Python 3-statement reconciliation, 6-dimensional report framework, currency/unit
  normalization, and non-public entity fallback contracts

[POS]
Architecture test verifying the operational integrity and contract stability of the
financial-business-analysis prebuilt skill.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_SERVER_ROOT = Path(__file__).resolve().parents[2]
_SKILL_MD = (
    _SERVER_ROOT
    / "assets"
    / "prebuilt_skills"
    / "financial-business-analysis"
    / "SKILL.md"
)

_CONTRACT_MARKERS = (
    # Tool declarations in frontmatter
    "bash_code_execute_tool",
    "web_search_tool",
    "web_fetch_tool",
    "file_read_tool",
    "file_write_tool",
    # Official source gate
    "SEC EDGAR",
    "CnInfo",
    "HKEXnews",
    # Code-driven reconciliation
    "Python",
    "reconciliation",
    # Non-public entity fallback gate
    "Non-Public Qualitative Fallback",
    # Unit & currency normalization
    "unit_and_currency_normalization",
    # Verification gate
    "three_statement_reconciliation",
    # References wiring
    "references/financial-report-template.md",
    "references/financial-audit-sop.md",
)

_MAX_SKILL_CHARS = 12_000


@pytest.fixture(scope="module")
def skill_text() -> str:
    if not _SKILL_MD.is_file():
        pytest.fail(f"Missing financial-business-analysis skill: {_SKILL_MD}")
    return _SKILL_MD.read_text(encoding="utf-8")


def test_financial_skill_file_exists() -> None:
    assert _SKILL_MD.is_file(), f"File does not exist: {_SKILL_MD}"


def test_financial_skill_char_limit(skill_text: str) -> None:
    assert len(skill_text) <= _MAX_SKILL_CHARS, (
        f"financial-business-analysis SKILL.md is {len(skill_text)} chars, exceeding {_MAX_SKILL_CHARS}"
    )


def test_financial_skill_contains_contract_markers(skill_text: str) -> None:
    missing = [m for m in _CONTRACT_MARKERS if m not in skill_text]
    assert not missing, f"financial-business-analysis SKILL.md is missing contract markers: {missing}"