#!/usr/bin/env python3
"""Fail CI when a relative or alias import specifier points at nothing on disk.

TypeScript cannot catch this class of bug: Node's ``require`` is typed
``(id: string) => any`` and ``await import(str)`` erases the specifier, so
``tsc --noEmit`` happily accepts ``require('./sandbox')`` after ``sandbox.ts``
is deleted. Only the bundler notices — at runtime, as a hard 500. This checker
closes that gap by resolving every static specifier against the filesystem with
the same extension-substitution + index rules the bundler uses.

Scope notes:

- Bare specifiers (``react``, ``next/server``, ``katex/dist/katex.min.css``) are
  resolved by Node/bundler and intentionally skipped.
- Test doubles (``vi.mock``/``jest.mock``) are skipped: a mock may name a module
  that is absent without affecting the shipped app.
- Specifiers inside string literals or comments are not imports, so a textual
  scan tracks quoting/comments and only reports code-level specifiers.

Run from myrm-agent-frontend root::

    python3 scripts/check_module_resolution.py
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_PRUNE_DIRS = frozenset({"node_modules", ".next", "dist", "build", ".turbo"})
_SOURCE_SUFFIXES = (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs")
_SUBSTITUTIONS = ("", ".ts", ".tsx", ".mts", ".js", ".jsx", ".mjs", ".cjs", ".json", ".css", ".scss")
_INDEX_NAMES = ("index.ts", "index.tsx", "index.mts", "index.js", "index.jsx", "index.mjs", "index.json")

# Static specifiers only. Computed specifiers (template literals, variables) are
# out of scope: they cannot be resolved without executing the module graph.
_SPECIFIER_RE = re.compile(
    r"""(?:^|[^\w$])(?:"""
    r"""from\s*|"""
    r"""import\s*|"""
    r"""import\(\s*|"""
    r"""require\(\s*"""
    r""")['"]([^'"]+)['"]"""
)


def _code_mask(text: str) -> list[bool]:
    """Mark each character index as code (True) vs string/comment (False)."""
    mask = [False] * len(text)
    state = "code"
    i = 0
    length = len(text)
    while i < length:
        char = text[i]
        nxt = text[i + 1] if i + 1 < length else ""
        if state == "code":
            if char == "/" and nxt == "/":
                state = "line_comment"
                i += 2
                continue
            if char == "/" and nxt == "*":
                state = "block_comment"
                i += 2
                continue
            if char in "'\"`":
                state = {"'": "single", '"': "double", "`": "template"}[char]
                i += 1
                continue
            mask[i] = True
            i += 1
        elif state == "line_comment":
            if char == "\n":
                state = "code"
            i += 1
        elif state == "block_comment":
            if char == "*" and nxt == "/":
                state = "code"
                i += 2
                continue
            i += 1
        else:  # inside single/double/template literal
            closing = {"single": "'", "double": '"', "template": "`"}[state]
            if char == "\\":
                i += 2
                continue
            if char == closing:
                state = "code"
            i += 1
    return mask


def _alias_targets(frontend_root: Path) -> tuple[tuple[str, Path], ...]:
    """Mirror the `paths` mapping in tsconfig.json."""
    return (
        ("@/", frontend_root / "src"),
        ("#locales/", frontend_root / "locales"),
        ("@shared/", frontend_root.parent / "shared"),
    )


def _candidate_bases(frontend_root: Path, source: Path, specifier: str) -> list[Path] | None:
    """Return filesystem bases to probe, or None when the specifier is not ours to resolve."""
    raw = specifier.split("?")[0].split("#")[0]
    if not raw:
        return None
    for alias, target in _alias_targets(frontend_root):
        if raw.startswith(alias):
            return [target / raw[len(alias) :]]
    if raw.startswith("./") or raw.startswith("../"):
        return [source.parent / raw]
    return None


def _resolves(base: Path) -> bool:
    for suffix in _SUBSTITUTIONS:
        candidate = base if not suffix else Path(f"{base}{suffix}")
        if candidate.is_file():
            return True
    if base.is_dir():
        if any((base / name).is_file() for name in _INDEX_NAMES):
            return True
    return False


def _iter_sources(frontend_root: Path) -> list[Path]:
    src_root = frontend_root / "src"
    files: list[Path] = []
    for path in sorted(src_root.rglob("*")):
        if not path.is_file() or path.suffix not in _SOURCE_SUFFIXES:
            continue
        if any(part in _PRUNE_DIRS for part in path.parts):
            continue
        files.append(path)
    return files


def find_unresolved(frontend_root: Path) -> list[tuple[str, str]]:
    """Return ``(relative_source, specifier)`` for every dangling static specifier."""
    violations: list[tuple[str, str]] = []
    for source in _iter_sources(frontend_root):
        try:
            text = source.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        mask = _code_mask(text)
        seen: set[str] = set()
        for match in _SPECIFIER_RE.finditer(text):
            if not mask[match.start()]:
                continue  # specifier text inside a string literal or comment
            specifier = match.group(1)
            if specifier in seen:
                continue
            seen.add(specifier)
            bases = _candidate_bases(frontend_root, source, specifier)
            if bases is None:
                continue
            if not any(_resolves(base) for base in bases):
                violations.append((source.relative_to(frontend_root).as_posix(), specifier))
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--frontend-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
    )
    args = parser.parse_args(argv)

    frontend_root: Path = args.frontend_root.resolve()
    violations = find_unresolved(frontend_root)

    if violations:
        print("ERROR: import specifiers resolve to nothing on disk:", file=sys.stderr)
        for source, specifier in violations:
            print(f"  - {source} -> '{specifier}'", file=sys.stderr)
        print(
            "Restore the deleted module or fix the specifier. A missing target "
            "compiles fine under tsc but breaks the app at runtime.",
            file=sys.stderr,
        )
        return 1

    print(f"OK (module resolution, {len(_iter_sources(frontend_root))} sources).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
