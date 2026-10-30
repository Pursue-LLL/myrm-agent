#!/usr/bin/env python3
"""Requirement lines for the LangChain-family packages pyproject.toml declares.

[INPUT]
- pyproject.toml (POS: ``[project].dependencies`` and ``[project].optional-dependencies``)

[OUTPUT]
- framework_requirements(): the declared requirements of langchain-* / langgraph-* packages, one per package
- main(): ``--floor`` prints ``name==lowest allowed``, ``--latest`` prints ``name`` with its full range, ``--check``
  exits 1 when a package lacks a ``>=`` floor or a ``<`` upper bound

[POS]
The weekly framework canary (``harness-framework-canary.yml``) installs these lines, so the versions it tests are the
ones pyproject.toml declares and cannot drift from them. ``--check`` is the same rule the architecture gate enforces.
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

_PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"
_FAMILY_PREFIXES = ("langchain", "langgraph")
_UPPER_OPERATORS = frozenset({"<", "<="})


def _is_framework(name: str) -> bool:
    return any(name == prefix or name.startswith(f"{prefix}-") for prefix in _FAMILY_PREFIXES)


def framework_requirements(pyproject_text: str) -> list[Requirement]:
    """The first declaration of each LangChain-family package, by package name."""
    project = tomllib.loads(pyproject_text)["project"]
    declared = [
        *project.get("dependencies", []),
        *(spec for extra in project.get("optional-dependencies", {}).values() for spec in extra),
    ]
    found: dict[str, Requirement] = {}
    for spec in declared:
        requirement = Requirement(spec)
        name = canonicalize_name(requirement.name)
        if _is_framework(name):
            found.setdefault(name, requirement)
    return [found[name] for name in sorted(found)]


def floor_of(requirement: Requirement) -> str:
    floors = [s.version for s in requirement.specifier if s.operator == ">="]
    if len(floors) != 1:
        raise ValueError(
            f"{requirement.name} must declare exactly one '>=' floor, found {str(requirement.specifier)!r}"
        )
    return floors[0]


def has_upper_bound(requirement: Requirement) -> bool:
    return any(s.operator in _UPPER_OPERATORS for s in requirement.specifier)


def problems(requirements: list[Requirement]) -> list[str]:
    found: list[str] = []
    for requirement in requirements:
        try:
            floor_of(requirement)
        except ValueError as error:
            found.append(str(error))
        if not has_upper_bound(requirement):
            found.append(f"{requirement.name} must declare a '<' upper bound, found {str(requirement.specifier)!r}")
    return found


def main(argv: list[str]) -> int:
    mode = argv[0] if argv else "--check"
    requirements = framework_requirements(_PYPROJECT.read_text(encoding="utf-8"))
    if mode == "--check":
        found = problems(requirements)
        if found:
            print("\n".join(found), file=sys.stderr)
        return 1 if found else 0
    if mode == "--floor":
        print("\n".join(f"{canonicalize_name(r.name)}=={floor_of(r)}" for r in requirements))
        return 0
    if mode == "--latest":
        print("\n".join(f"{canonicalize_name(r.name)}{r.specifier}" for r in requirements))
        return 0
    print(f"unknown mode {mode!r}; use --floor, --latest or --check", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
