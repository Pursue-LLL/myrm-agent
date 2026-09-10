"""Architecture guard: persona-corpus-distillation skill must preserve its core operating contract.

[INPUT]
- assets/prebuilt_skills/persona-corpus-distillation/SKILL.md

[OUTPUT]
- Architecture tests ensuring persona-corpus-distillation skill retains 5-phase distillation pipeline, PII redaction, mental models, voice fingerprint, golden few-shot playbook, and anti-hallucination guardrails

[POS]
Architecture test verifying the operational integrity and contract stability of the persona-corpus-distillation prebuilt skill.
"""

from __future__ import annotations

from pathlib import Path
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SKILL_MD = _REPO_ROOT / "myrm-agent" / "myrm-agent-server" / "assets" / "prebuilt_skills" / "persona-corpus-distillation" / "SKILL.md"

_PHASE_MARKERS = (
    "Phase 1: Ingestion & PII Redaction",
    "Phase 2: Domain Mental Model Extraction",
    "Phase 3: Conversational Voice Fingerprint Profiling",
    "Phase 4: Golden Few-Shot Scenario Synthesis",
    "Phase 5: Self-Contained SKILL.md Packaging",
)

_CONTRACT_MARKERS = (
    # Core pipeline components
    "PII Redaction",
    "Decision Heuristics",
    "Voice Fingerprint",
    "Golden Few-Shot",
    # Safety & Boundaries
    "Anti-Hallucination",
    "Evidence-Based Extraction",
    "Clear Boundary Gating",
    # Tool declarations in frontmatter
    "file_read_tool",
    "file_write_tool",
    "memory_save_tool",
    "memory_search_tool",
)

_MAX_SKILL_CHARS = 12_000


@pytest.fixture(scope="module")
def skill_text() -> str:
    if not _SKILL_MD.is_file():
        pytest.fail(f"Missing persona-corpus-distillation skill: {_SKILL_MD}")
    return _SKILL_MD.read_text(encoding="utf-8")


def test_persona_corpus_distillation_file_exists() -> None:
    assert _SKILL_MD.is_file(), f"File does not exist: {_SKILL_MD}"


def test_persona_corpus_distillation_char_limit(skill_text: str) -> None:
    assert len(skill_text) <= _MAX_SKILL_CHARS, (
        f"persona-corpus-distillation SKILL.md is {len(skill_text)} chars, exceeding {_MAX_SKILL_CHARS}"
    )


def test_persona_corpus_distillation_contains_all_phases(skill_text: str) -> None:
    missing = [p for p in _PHASE_MARKERS if p not in skill_text]
    assert not missing, f"persona-corpus-distillation SKILL.md is missing phases: {missing}"


def test_persona_corpus_distillation_contains_contract_markers(skill_text: str) -> None:
    missing = [m for m in _CONTRACT_MARKERS if m not in skill_text]
    assert not missing, f"persona-corpus-distillation SKILL.md is missing contract markers: {missing}"
