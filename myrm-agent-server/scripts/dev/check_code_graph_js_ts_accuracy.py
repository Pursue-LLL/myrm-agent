#!/usr/bin/env python3
"""Measure the JS/TS code graph extractor against the TypeScript compiler on a source tree.

The files are the ones the code graph would index under ROOT. For each file the symbols, calls and class
inheritances of ``JsTsTreeSitterExtractor`` are compared with what ``code_graph_ts_reference.mjs`` derives from the
compiler's own syntax tree under the same rules. A fact counts as matched only when all its fields are equal; a call
is (line of the called name, callee text, caller, argument count), so a wrong attribution shows up as one missed and
one extra call.

Run it after changing the extractor or the tree-sitter grammar versions; it is a measurement, not a gate.

Usage:
    uv run python scripts/dev/check_code_graph_js_ts_accuracy.py ROOT [--typescript DIR] [--show N]

Needs ``node`` and a TypeScript package (default: the frontend's ``node_modules/typescript``).
"""

from __future__ import annotations

import argparse
import json
import shutil
import stat
import subprocess
import sys
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import NotRequired, TypedDict, cast

import tree_sitter_typescript
from tree_sitter import Language, Parser

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from myrm_agent_harness.toolkits.filesystem_suggest import WorkspacePathIndexer  # noqa: E402

from app.services.code_graph.js_ts_extractor import JsTsTreeSitterExtractor  # noqa: E402
from app.services.code_graph.models import SymbolKind, module_name_for  # noqa: E402
from app.services.code_graph.service import MAX_SOURCE_BYTES, SOURCE_SUFFIXES, CodeGraphService  # noqa: E402

_REFERENCE = Path(__file__).with_name("code_graph_ts_reference.mjs")
_DEFAULT_TYPESCRIPT = Path(__file__).resolve().parents[3] / "myrm-agent-frontend" / "node_modules" / "typescript"

# One parser per dialect, to ask tree-sitter whether it could read a file without errors.
_PARSERS = {
    tsx: Parser(Language(tree_sitter_typescript.language_tsx() if tsx else tree_sitter_typescript.language_typescript()))
    for tsx in (False, True)
}

Fact = tuple[str | int, ...]
# What is compared, by kind: symbols are (qualified name, kind, line of the name, last line), calls are
# (line of the called name, callee text, caller, argument count), inheritances are (class, base text, line).
Facts = dict[str, Counter[Fact]]
KINDS = ("symbols", "calls", "inheritances")


class ReferenceRow(TypedDict):
    path: str
    error: NotRequired[str]
    symbols: NotRequired[list[list[str | int]]]
    calls: NotRequired[list[list[str | int]]]
    inheritances: NotRequired[list[list[str | int]]]


@dataclass
class Tally:
    """Totals of one kind of fact over all files."""

    reference: int = 0
    extractor: int = 0
    missed: int = 0
    missed_in_unreadable_files: int = 0
    extra: int = 0
    examples: list[str] = field(default_factory=list)

    @property
    def recall(self) -> float:
        return 1.0 if not self.reference else (self.reference - self.missed) / self.reference

    @property
    def precision(self) -> float:
        return 1.0 if not self.extractor else (self.extractor - self.extra) / self.extractor


def _source_files(root: Path) -> list[str]:
    """The files ``CodeGraphService`` would parse with the JS/TS extractor."""
    WorkspacePathIndexer.clear_cache(root)
    listing = WorkspacePathIndexer.list_files(root)
    if WorkspacePathIndexer.is_truncated(listing):
        print("warning: the file listing reached its cap, so part of the tree is not measured", file=sys.stderr)
    files: list[str] = []
    for rel_path in listing:
        parts = PurePosixPath(rel_path)
        if parts.suffix == ".py" or parts.suffix not in SOURCE_SUFFIXES:
            continue
        if CodeGraphService.EXCLUDE_DIRS.intersection(parts.parts):
            continue
        try:
            info = (root / rel_path).lstat()
        except OSError:
            continue
        if stat.S_ISREG(info.st_mode) and info.st_size <= MAX_SOURCE_BYTES:
            files.append(rel_path)
    return files


def _read_sources(root: Path, files: list[str]) -> dict[str, str]:
    """Every file is read once, so both sides see the same text even while the tree is being edited."""
    sources: dict[str, str] = {}
    for rel_path in files:
        try:
            # utf-8-sig drops a leading BOM, as the indexer does.
            sources[rel_path] = (root / rel_path).read_text(encoding="utf-8-sig", errors="ignore")
        except OSError:
            continue
    return sources


def _reference_rows(sources: dict[str, str], typescript: Path) -> Iterator[ReferenceRow]:
    node = shutil.which("node")
    if node is None:
        raise SystemExit("node is required to run the TypeScript compiler")
    request = json.dumps([{"path": path, "module": module_name_for(path), "source": source} for path, source in sources.items()])
    done = subprocess.run([node, str(_REFERENCE), str(typescript)], input=request, capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise SystemExit(f"the TypeScript reference run failed: {done.stderr.strip()}")
    for line in done.stdout.splitlines():
        yield cast(ReferenceRow, json.loads(line))


def _reference_facts(row: ReferenceRow) -> Facts:
    return {
        "symbols": Counter(tuple(fact) for fact in row.get("symbols", [])),
        "calls": Counter(tuple(fact) for fact in row.get("calls", [])),
        "inheritances": Counter(tuple(fact) for fact in row.get("inheritances", [])),
    }


def _extractor_facts(code: str, rel_path: str) -> Facts:
    extractor = JsTsTreeSitterExtractor(rel_path, code)
    extractor.extract()
    return {
        "symbols": Counter(
            (s.qualified_name, s.kind.value, s.line_start, s.line_end)
            for s in extractor.symbols
            if s.kind is not SymbolKind.MODULE
        ),
        "calls": Counter((c.call_site.line, c.callee, c.caller, c.call_site.arg_count) for c in extractor.calls),
        "inheritances": Counter((i.sub_type, i.super_type, i.line) for i in extractor.inheritances),
    }


def _compare(
    tally: Tally, reference: Counter[Fact], extractor: Counter[Fact], where: str, *, unreadable: bool, show: int
) -> None:
    missed, extra = reference - extractor, extractor - reference
    tally.reference += reference.total()
    tally.extractor += extractor.total()
    tally.missed += missed.total()
    tally.extra += extra.total()
    if unreadable:
        tally.missed_in_unreadable_files += missed.total()
    note = " [tree-sitter error]" if unreadable else ""
    for label, diff in (("missed", missed), ("extra", extra)):
        for fact in diff:
            if len(tally.examples) < show:
                tally.examples.append(f"{label} {where}{note}: {fact}")


def _report(kind: str, tally: Tally) -> None:
    print(
        f"{kind:<13} reference {tally.reference:>8,}  extractor {tally.extractor:>8,}  "
        f"recall {tally.recall:8.2%}  precision {tally.precision:8.2%}  "
        f"missed {tally.missed:,} ({tally.missed_in_unreadable_files:,} in files tree-sitter reports errors in)  "
        f"extra {tally.extra:,}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("root", type=Path, help="source tree to measure")
    parser.add_argument("--typescript", type=Path, default=_DEFAULT_TYPESCRIPT, help="TypeScript package directory")
    parser.add_argument("--show", type=int, default=10, help="how many differences to print per kind")
    args = parser.parse_args()

    root: Path = args.root.expanduser().resolve()
    sources = _read_sources(root, _source_files(root))
    tallies = {kind: Tally() for kind in KINDS}
    unreadable_files = 0
    failed: list[str] = []
    for row in _reference_rows(sources, args.typescript):
        if "error" in row:
            failed.append(f"{row['path']}: {row['error']}")
            continue
        code = sources[row["path"]]
        unreadable = _PARSERS[not row["path"].endswith(".ts")].parse(code.encode("utf-8")).root_node.has_error
        unreadable_files += unreadable
        reference, extractor = _reference_facts(row), _extractor_facts(code, row["path"])
        for kind in KINDS:
            _compare(tallies[kind], reference[kind], extractor[kind], row["path"], unreadable=unreadable, show=args.show)

    print(
        f"{root}: {len(sources):,} files, {unreadable_files:,} that tree-sitter reports syntax errors in, "
        f"{len(failed):,} the reference run failed on"
    )
    for kind, tally in tallies.items():
        _report(kind, tally)
    for tally in tallies.values():
        for example in tally.examples:
            print(f"  {example}")
    for failure in failed[: args.show]:
        print(f"  reference failed on {failure}")


if __name__ == "__main__":
    main()
