"""Architecture guard: ast-grep-search skill must preserve its core operating contract.

[INPUT]
- assets/prebuilt_skills/ast-grep-search/SKILL.md

[OUTPUT]
- Architecture tests ensuring ast-grep-search skill retains structural AST matching,
  metavariables ($VAR, $$$ARGS), non-destructive dry-run rules, and multi-language support.

[POS]
Architecture test verifying the operational integrity and contract stability of the ast-grep-search prebuilt skill.
"""

from __future__ import annotations

from pathlib import Path
import pytest

_SKILL_MD = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "prebuilt_skills"
    / "ast-grep-search"
    / "SKILL.md"
)

_CORE_MODULE_MARKERS = (
    "ast-grep-search",
    "Structural syntax-aware AST code search",
    "Concrete Syntax Tree vs Regex Search",
    "$VAR",
    "$$$ARGS",
    "Concrete Syntax Tree",
)

_CONTRACT_MARKERS = (
    # Tool definitions
    "bash_code_execute_tool",
    "file_read_tool",
    "file_write_tool",
    # Verification steps
    "ast_metavariables_used",
    "non_destructive_first",
)

_MAX_SKILL_CHARS = 12_000


@pytest.fixture(scope="module")
def skill_text() -> str:
    if not _SKILL_MD.is_file():
        pytest.fail(f"Missing ast-grep-search skill: {_SKILL_MD}")
    return _SKILL_MD.read_text(encoding="utf-8")


def test_ast_grep_search_file_exists() -> None:
    assert _SKILL_MD.is_file(), f"File does not exist: {_SKILL_MD}"


def test_ast_grep_search_char_limit(skill_text: str) -> None:
    assert len(skill_text) <= _MAX_SKILL_CHARS, (
        f"ast-grep-search SKILL.md is {len(skill_text)} chars, exceeding {_MAX_SKILL_CHARS}"
    )


def test_ast_grep_search_contains_core_markers(skill_text: str) -> None:
    missing = [m for m in _CORE_MODULE_MARKERS if m not in skill_text]
    assert not missing, f"ast-grep-search SKILL.md is missing core markers: {missing}"


def test_ast_grep_search_contains_contract_markers(skill_text: str) -> None:
    missing = [m for m in _CONTRACT_MARKERS if m not in skill_text]
    assert not missing, f"ast-grep-search SKILL.md is missing contract markers: {missing}"
