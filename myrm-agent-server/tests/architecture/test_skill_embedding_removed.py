"""Architecture gate: the server wires no embedding, rerank or semantic-similarity machinery into skills.

Skill discovery is lexical and skill consolidation groups skills by a shared name prefix and lets an LLM judge each
group (see the harness gate of the same name). The server keeps its embedding configuration for memory and wiki; each
removal below keeps the skill-side server code it names free of the harness classes that were removed and of the
settings that tuned them.

[INPUT]
- app/: read as text and split into words, never imported, so a deleted module cannot fail the gate

[OUTPUT]
- (tests only)

[POS]
Gate against re-adding what the three removals took out of the server: the curator's embedding precondition and
similarity threshold, the embedding engine behind skill search, and the creation-time similarity check.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import pytest

_APP = Path(__file__).resolve().parents[2] / "app"
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_TEXT_SUFFIXES = frozenset({".py", ".pyi", ".md"})


@dataclass(frozen=True)
class _Removal:
    """What a removal leaves behind: nothing that its words, fragments or files name."""

    name: str
    scope: tuple[str, ...]  # files and directories, relative to ``app``, that the words are banned from
    words: frozenset[str]  # whole identifiers that may not appear in scope
    fragments: tuple[str, ...] = ()  # lower-case fragments that no word in scope may contain
    files: tuple[str, ...] = ()  # paths that may not exist


_REMOVALS = (
    _Removal(
        name="curator-embedding-clustering",
        scope=("core/skills/curator", "api/skills/curator.py"),
        words=frozenset({"similarity_threshold", "consolidation_similarity_threshold"}),
        fragments=("embedding",),
    ),
    _Removal(
        name="skill-search-embedding",
        scope=("",),
        words=frozenset({"HybridSkillSearchEngine", "hybrid_engine"}),
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
                "set_similarity_checker",
                "SIMILARITY_THRESHOLD",
                "REASON_SIMILAR_PREFIX",
            }
        ),
        files=("services/skills/similarity_checker.py",),
    ),
)


def _text_files(entry: str) -> list[Path]:
    path = _APP / entry
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
                found[str(file.relative_to(_APP))] = hits
    return found


@pytest.mark.parametrize("removal", [removal for removal in _REMOVALS if removal.files], ids=lambda removal: removal.name)
def test_removed_files_do_not_exist(removal: _Removal) -> None:
    leftover = [path for path in removal.files if (_APP / path).exists()]
    assert not leftover, f"{removal.name}: {leftover}"


@pytest.mark.parametrize("removal", _REMOVALS, ids=lambda removal: removal.name)
def test_removed_names_do_not_appear(removal: _Removal) -> None:
    offences = _offences(removal)
    assert not offences, f"{removal.name}: {offences}"
