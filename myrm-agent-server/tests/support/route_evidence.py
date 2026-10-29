"""Does the evidence of a registered external route consumer still point at the route?

[INPUT]
- tests/architecture/data/route_external_consumers.txt: `METHOD /path | caller (file:line[-line] [`anchor`])`

[OUTPUT]
- Citation / parse_citation(): the file, line range and optional anchor a piece of evidence ends with
- check_evidence(): `EvidenceCheck(skipped, problem)` of one entry against the checkouts the tests can see
- CHECKOUT_ROOTS: where a cited path is looked up, in order

[POS]
「外部调用方登记」的证据校验：登记行引用的 file:line 会随文件改动漂移，行号还在、内容早已不是那一行，登记就成了
没人核对的断言。这里只回答一个问题：被引用的行里有没有这条路由——有它最后一段静态路径（整词），或者登记里
显式写出的锚点（调用方并不拼写路径时，如 HTML 表单的空 action）。

A citation path is relative to the open-source repository when the file lives in it, otherwise to the directory that
holds it next to the other repositories. A citation into a tree this checkout does not have is skipped, never
passed: the result says so, and the test counts what it actually verified.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

OPEN_SOURCE_ROOT = Path(__file__).resolve().parents[3]
CHECKOUT_ROOTS: tuple[Path, ...] = (OPEN_SOURCE_ROOT, OPEN_SOURCE_ROOT.parent)

_CITATION = re.compile(r"\((?P<path>[^():\s]+):(?P<first>\d+)(?:-(?P<last>\d+))?(?: `(?P<anchor>[^`]+)`)?\)$")


@dataclass(frozen=True)
class Citation:
    path: str
    first: int
    last: int
    anchor: str | None


class EvidenceCheck(NamedTuple):
    """`skipped`: the cited tree is not part of this checkout; `problem`: why the evidence no longer holds."""

    skipped: bool = False
    problem: str | None = None


def parse_citation(evidence: str) -> Citation | None:
    """The `(file:line[-line] [`anchor`])` a piece of evidence ends with."""
    match = _CITATION.search(evidence.strip())
    if match is None:
        return None
    first = int(match["first"])
    return Citation(match["path"], first, int(match["last"] or first), match["anchor"])


def route_word(route_path: str) -> str | None:
    """The last static segment of a route path, the word a caller of the route has to spell."""
    static = [segment for segment in route_path.split("/") if segment and not segment.startswith("{")]
    return static[-1] if static else None


def _spells(text: str, word: str) -> bool:
    return re.search(rf"(?<![\w-]){re.escape(word)}(?![\w-])", text) is not None


def check_evidence(method: str, route_path: str, evidence: str, roots: tuple[Path, ...] = CHECKOUT_ROOTS) -> EvidenceCheck:
    citation = parse_citation(evidence)
    if citation is None:
        return EvidenceCheck(problem="evidence must end with (file:line), (file:first-last) or (file:line `anchor`)")
    cited = next((root / citation.path for root in roots if (root / citation.path).is_file()), None)
    if cited is None:
        top = citation.path.split("/", 1)[0]
        if any((root / top).exists() for root in roots):
            return EvidenceCheck(problem=f"{citation.path} does not exist")
        return EvidenceCheck(skipped=True)
    lines = cited.read_text(encoding="utf-8", errors="replace").splitlines()
    if citation.last > len(lines):
        return EvidenceCheck(problem=f"{citation.path}:{citation.last} is past the end of the file ({len(lines)} lines)")
    text = "\n".join(lines[citation.first - 1 : citation.last])
    if citation.anchor is not None:
        if citation.anchor in text:
            return EvidenceCheck()
        return EvidenceCheck(problem=f"{citation.path}:{citation.first}-{citation.last} does not contain `{citation.anchor}`")
    word = route_word(route_path)
    if word is None:
        return EvidenceCheck(problem=f"{method} {route_path} has no static segment to look for; cite an `anchor`")
    if _spells(text, word):
        return EvidenceCheck()
    return EvidenceCheck(problem=f"{citation.path}:{citation.first}-{citation.last} does not spell `{word}`")
