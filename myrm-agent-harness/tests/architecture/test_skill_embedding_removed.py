"""Architecture gate: skills carry no embedding, rerank or semantic-similarity machinery.

Skill discovery is lexical: BM25 over a skill's name and description, a synonym table, and a tool text that asks the
agent for English keywords. Skill consolidation groups skills by a shared name prefix and lets an LLM judge each group.
Embeddings belong to memory, wiki and retrieval and stay there; each removal below keeps the skill modules it names
free of them, in code, comments, docstrings and the architecture notes that sit beside the code.

[INPUT]
- src/myrm_agent_harness: read as text and split into words, never imported, so a deleted module cannot fail the gate

[OUTPUT]
- (tests only)

[POS]
Gate against re-adding what the three removals took out: the curator's embedding clustering and similarity threshold,
the embedding half of skill search, and the creation-time similarity check.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import pytest

_PACKAGE = Path(__file__).resolve().parents[2] / "src" / "myrm_agent_harness"
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_TEXT_SUFFIXES = frozenset({".py", ".pyi", ".md"})


@dataclass(frozen=True)
class _Removal:
    """What a removal leaves behind: nothing that its words, fragments or files name."""

    name: str
    scope: tuple[str, ...]  # files and directories, relative to the package, that the words are banned from
    words: frozenset[str]  # whole identifiers that may not appear in scope
    fragments: tuple[str, ...] = ()  # lower-case fragments that no word in scope may contain
    files: tuple[str, ...] = ()  # paths that may not exist


_REMOVALS = (
    _Removal(
        name="curator-embedding-clustering",
        scope=("agent/skills/curator", "backends/skills/curator_config.py"),
        words=frozenset(
            {
                "similarity_threshold",
                "consolidation_similarity_threshold",
                "_DEFAULT_SIMILARITY_THRESHOLD",
                "_DEFAULT_CONSOLIDATION_SIMILARITY_THRESHOLD",
                "avg_similarity",
                "representative_keywords",
                "numpy",
            }
        ),
        fragments=("embedding",),
    ),
    _Removal(
        name="skill-search-embedding",
        scope=(
            "agent/meta_tools/__init__.py",
            "agent/meta_tools/discover_capability",
            "agent/meta_tools/skills/search",
            "agent/skill_agent",
            "agent/_internals/skill_catalog_turn.py",
            "agent/_factory/builder.py",
        ),
        words=frozenset({"HybridSkillSearchEngine", "SearchMetadata", "hybrid_engine", "numpy"}),
        fragments=("embedding",),
        files=("agent/meta_tools/skills/search/hybrid_engine.py",),
    ),
    _Removal(
        name="skill-creation-similarity",
        scope=("",),
        words=frozenset(
            {
                "SkillSimilarityChecker",
                "SimilarSkillInfo",
                "HybridSimilarityChecker",
                "similarity_checker",
                "_similarity_checker",
            }
        ),
        files=("backends/skills/similarity.py",),
    ),
)

# Removals not yet carried out; each step of the work deletes its own entry when it lands.
_PENDING = {removal.name for removal in _REMOVALS}


def _params(removals: tuple[_Removal, ...]) -> list[object]:
    return [
        pytest.param(
            removal,
            id=removal.name,
            marks=pytest.mark.xfail(strict=True, reason="removal not carried out yet")
            if removal.name in _PENDING
            else (),
        )
        for removal in removals
    ]


def _text_files(entry: str) -> list[Path]:
    path = _PACKAGE / entry
    if path.is_file():
        return [path]
    if not path.is_dir():
        return []
    return sorted(file for file in path.rglob("*") if file.suffix in _TEXT_SUFFIXES and "__pycache__" not in file.parts)


@cache
def _words(file: Path) -> frozenset[str]:
    return frozenset(_WORD.findall(file.read_text(encoding="utf-8")))


def _offences(removal: _Removal) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for entry in removal.scope:
        for file in _text_files(entry):
            words = _words(file)
            hits = sorted(
                (words & removal.words)
                | {word for word in words if any(fragment in word.lower() for fragment in removal.fragments)}
            )
            if hits:
                found[str(file.relative_to(_PACKAGE))] = hits
    return found


@pytest.mark.parametrize("removal", _params(tuple(removal for removal in _REMOVALS if removal.files)))
def test_removed_files_do_not_exist(removal: _Removal) -> None:
    leftover = [path for path in removal.files if (_PACKAGE / path).exists()]
    assert not leftover, f"{removal.name}: {leftover}"


@pytest.mark.parametrize("removal", _params(_REMOVALS))
def test_removed_names_do_not_appear(removal: _Removal) -> None:
    offences = _offences(removal)
    assert not offences, f"{removal.name}: {offences}"
