#!/usr/bin/env python3
"""Validate module-level _ARCH.md file tables, markdown paths, and brand doc citations.

Three independent checks:

1. **_ARCH inventory** — module-level ``_ARCH.md`` file tables must list sibling
   ``.py`` files (bidirectional: every py file listed, every listed py on disk).
2. **markdown path refs** (``--md-refs``) — backtick-wrapped relative paths and
   inline ``[label](path)`` links in any ``*.md`` under the scanned root must
   resolve to a real file/directory. Resolution rules live in
   :mod:`scripts.md_ref_validator` (explicit relatives, cross-repo aliases, and
   source-root module shortcuts).
3. **brand doc repo refs** (``--repo-refs``) — code paths cited by
   ``myrm-agent-brand/**/*.md(x)`` (``myrm-agent/...``, ``myrm-control-plane/...``)
   must exist in the workspace. Skipped when the brand repo is not checked out, so
   a standalone harness clone stays green.

Only parses markdown **table rows** (lines starting with ``|``) in ``_ARCH.md`` —
prose mentions of ``other_module.py`` are ignored by check 1; checks 2 and 3 also
scan prose so that refactor-orphaned paths surface in CI.

Usage:
    python scripts/validate_arch_inventory.py
    python scripts/validate_arch_inventory.py --root src/myrm_agent_harness
    python scripts/validate_arch_inventory.py --root src/myrm_agent_harness/agent
    python scripts/validate_arch_inventory.py --md-refs
    python scripts/validate_arch_inventory.py --repo-refs
    python scripts/validate_arch_inventory.py --json

Exit codes:
    0: All checked directories consistent
    1: Missing/stale _ARCH entries, broken markdown paths, or broken brand citations
    2: Internal error
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from md_ref_validator import PRUNE_DIR_NAMES, MdRefReport, scan_md_refs

_REPO_ROOT = Path(__file__).resolve().parent.parent
_MONOREPO_ROOT = Path(__file__).resolve().parent.parent.parent
# Workspace root holding every product repo (open-perplexity/ by default).
_WORKSPACE_ROOT = _REPO_ROOT.parent.parent
_BRAND_ROOT = _WORKSPACE_ROOT / "myrm-agent-brand"
_TABLE_HEADER_CELLS = frozenset({"File", "Module", "Submodule", "文件"})

# Cross-repo documentation references: brand sites cite product sources by monorepo-relative
# path. When a cited file is deleted or renamed the prose keeps reading as if it were still
# evidence, so the reference has to be checked against the monorepo tree.
_REPO_REF_PREFIXES: tuple[str, ...] = (
    "myrm-agent/",
    "myrm-agent-harness/",
    "myrm-control-plane/",
    "myrm-agent-brand/",
)
_REPO_REF_SUFFIXES: tuple[str, ...] = (
    ".py",
    ".ts",
    ".tsx",
    ".rs",
    ".json",
    ".md",
    ".mdx",
    ".yaml",
    ".toml",
    ".sh",
)
_CODEPATH_SPAN_RE = re.compile(r"`([^`\n]+)`")
# Elided or templated paths are documentation shorthand, not evidence.
_REPO_REF_SKIP_CHARS: tuple[str, ...] = ("<", ">", "*", "...", "://", "|", " ")


@dataclass(frozen=True)
class RepoRefError:
    md_path: Path
    line: int
    ref: str


def _iter_doc_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if path.suffix not in {".md", ".mdx"} or not path.is_file():
            continue
        if any(part in PRUNE_DIR_NAMES for part in path.parts):
            continue
        files.append(path)
    return files


def scan_repo_refs(brand_root: Path, monorepo_root: Path) -> list[RepoRefError]:
    """Return brand-doc code references that point at files absent from the monorepo."""
    errors: list[RepoRefError] = []
    for md_path in _iter_doc_files(brand_root):
        for line_no, line in enumerate(md_path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
            for raw in _CODEPATH_SPAN_RE.findall(line):
                ref = raw.strip().split("#", 1)[0]
                if not ref.startswith(_REPO_REF_PREFIXES) or not ref.endswith(_REPO_REF_SUFFIXES):
                    continue
                if any(token in ref for token in _REPO_REF_SKIP_CHARS):
                    continue
                if not (monorepo_root / ref).exists():
                    errors.append(RepoRefError(md_path=md_path, line=line_no, ref=ref))
    return errors



@dataclass(frozen=True)
class DirReport:
    directory: Path
    py_files: tuple[str, ...]
    arch_path: Path
    listed: frozenset[str]
    missing_in_arch: tuple[str, ...]
    extra_in_arch: tuple[str, ...]


def _collect_py_files(directory: Path) -> list[str]:
    return sorted(p.name for p in directory.iterdir() if p.is_file() and p.suffix == ".py")


def first_table_cell(line: str) -> str | None:
    stripped = line.strip()
    if not stripped.startswith("|"):
        return None
    cells = [cell.strip() for cell in stripped.split("|")]
    if len(cells) < 3:
        return None
    return cells[1].strip("`").strip()


def is_inventory_file_cell(first: str) -> bool:
    """Return True when the first table cell names a single sibling .py file."""
    if first == "__init__.py":
        return True
    if not first.endswith(".py"):
        return False
    if "/" in first or "\\" in first:
        return False
    # Comparison/prose rows often list multiple paths in one cell.
    if "," in first:
        return False
    stem = first[: -len(".py")]
    return stem.isidentifier()


def _listed_py_in_arch(arch_path: Path) -> set[str]:
    listed: set[str] = set()
    for line in arch_path.read_text(encoding="utf-8").splitlines():
        first = first_table_cell(line)
        if first is None:
            continue
        if first in _TABLE_HEADER_CELLS:
            continue
        if first.startswith("---") or first.startswith("—"):
            continue
        if is_inventory_file_cell(first):
            listed.add(first)
    return listed


def scan_directory(directory: Path) -> DirReport | None:
    arch_path = directory / "_ARCH.md"
    if not arch_path.is_file():
        return None
    py_files = _collect_py_files(directory)
    listed = _listed_py_in_arch(arch_path)
    py_set = set(py_files)
    missing = tuple(sorted(py_set - listed))
    extra = tuple(sorted(listed - py_set))
    return DirReport(
        directory=directory,
        py_files=tuple(py_files),
        arch_path=arch_path,
        listed=frozenset(listed),
        missing_in_arch=missing,
        extra_in_arch=extra,
    )


def scan_tree(root: Path) -> list[DirReport]:
    reports: list[DirReport] = []
    for arch in sorted(root.rglob("_ARCH.md")):
        if any(part in PRUNE_DIR_NAMES for part in arch.parts):
            continue
        report = scan_directory(arch.parent)
        if report is not None and report.py_files:
            reports.append(report)
    return reports


def _rel_to_repo(path: Path) -> Path:
    try:
        return path.relative_to(_REPO_ROOT)
    except ValueError:
        return path


def _rel_to_workspace(path: Path) -> Path:
    """Repo-relative label for paths outside the harness repo (e.g. brand docs)."""
    try:
        return path.relative_to(_WORKSPACE_ROOT)
    except ValueError:
        return path


def _format_reports(reports: list[DirReport], *, root_label: str) -> str:
    lines = ["=" * 72, f"_ARCH.md inventory validation ({root_label})", "=" * 72]
    failed = False
    for report in reports:
        rel = _rel_to_repo(report.directory)
        if report.missing_in_arch or report.extra_in_arch:
            failed = True
            lines.append(f"\nFAIL {rel}")
            if report.missing_in_arch:
                lines.append(f"  missing in _ARCH: {', '.join(report.missing_in_arch)}")
            if report.extra_in_arch:
                lines.append(f"  listed but not on disk: {', '.join(report.extra_in_arch)}")
        else:
            lines.append(f"OK   {rel} ({len(report.py_files)} py files)")
    lines.append("")
    lines.append("PASS" if not failed else "FAIL - fix _ARCH.md file tables")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate _ARCH.md py file inventories")
    parser.add_argument(
        "--root",
        type=Path,
        default=_REPO_ROOT / "src" / "myrm_agent_harness",
        help="Package subtree to scan (default: entire src/myrm_agent_harness/)",
    )
    parser.add_argument(
        "--md-refs",
        action="store_true",
        help="Also validate backtick spans and inline links in *.md under the root",
    )
    parser.add_argument(
        "--repo-refs",
        action="store_true",
        help="Validate cross-repo code references cited by myrm-agent-brand docs (skipped when absent)",
    )
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    if not root.is_dir():
        print(f"ERROR: not a directory: {root}", file=sys.stderr)
        return 2

    # The _ARCH.md table inventory reflects this repo's own source-tree table
    # convention (harness lists __init__.py; other repos generate tables
    # differently), so table validation only applies inside src/. Cross-repo and
    # repo-root scans are supported exclusively for markdown path reference
    # validation.
    src_root = _REPO_ROOT / "src"
    scan_tables = root.is_relative_to(src_root)
    if not scan_tables and not (args.md_refs or args.repo_refs):
        print(f"ERROR: table inventory validation only supports roots inside {src_root}", file=sys.stderr)
        return 2

    reports = scan_tree(root) if scan_tables else []
    has_fail = any(r.missing_in_arch or r.extra_in_arch for r in reports)

    md_reports: list[MdRefReport] = []
    if args.md_refs:
        md_reports = scan_md_refs(root, _MONOREPO_ROOT, _REPO_ROOT)
        has_fail = has_fail or bool(md_reports)

    repo_ref_errors: list[RepoRefError] = []
    repo_refs_skipped = False
    if args.repo_refs:
        if _BRAND_ROOT.is_dir():
            repo_ref_errors = scan_repo_refs(_BRAND_ROOT, _WORKSPACE_ROOT)
            has_fail = has_fail or bool(repo_ref_errors)
        else:
            repo_refs_skipped = True

    if args.json:
        payload = [
            {
                "directory": str(_rel_to_repo(r.directory)),
                "py_files": list(r.py_files),
                "missing_in_arch": list(r.missing_in_arch),
                "extra_in_arch": list(r.extra_in_arch),
            }
            for r in reports
        ]
        if args.md_refs:
            payload.append(
                {
                    "md_refs": [
                        {
                            "md": str(_rel_to_repo(r.md_path)),
                            "broken": [{"ref": ref, "line": line} for ref, line in r.broken_refs],
                        }
                        for r in md_reports
                    ]
                }
            )
        if args.repo_refs:
            payload.append(
                {
                    "repo_refs": {
                        "skipped": repo_refs_skipped,
                        "broken": [
                            {
                                "md": str(_rel_to_workspace(error.md_path)),
                                "line": error.line,
                                "ref": error.ref,
                            }
                            for error in repo_ref_errors
                        ],
                    }
                }
            )
        print(json.dumps({"ok": not has_fail, "reports": payload}, indent=2))
    else:
        root_label = _rel_to_repo(root).as_posix()
        if reports:
            print(_format_reports(reports, root_label=root_label))
        if args.md_refs:
            print("=" * 72)
            if md_reports:
                print("FAIL - broken markdown path references")
                for report in md_reports:
                    rel = _rel_to_repo(report.md_path)
                    for ref, line_no in report.broken_refs:
                        print(f"  {rel}:{line_no}: `{ref}` not found")
            else:
                print(f"PASS - markdown path references resolve ({root_label})")
        if args.repo_refs:
            print("=" * 72)
            if repo_refs_skipped:
                print(f"SKIP - brand docs not checked out next to the harness ({_BRAND_ROOT})")
            elif repo_ref_errors:
                print("FAIL - brand docs cite code paths that do not exist")
                for error in repo_ref_errors:
                    rel = _rel_to_workspace(error.md_path)
                    print(f"  {rel}:{error.line}: `{error.ref}` not found")
            else:
                print("PASS - brand doc code references resolve")

    return 1 if has_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
