"""Which sources make a running Dev Gate coordinator stale.

The coordinator is a daemon that imports its code once. A fingerprint of the modification times of the sources
it executes is stamped when it starts; a later mismatch means it runs code that is no longer on disk, and the next
caller restarts it when no live session pins the generation.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

# Paths relative to the dev lib root. A directory stands for every module of that package, so a module added to
# the package is covered without editing this list.
COORDINATOR_CODE_SOURCES: tuple[str, ...] = (
    "dev_gate/coordinator.py",
    "dev_gate/cli.py",
    "dev_gate/contract.py",
    "dev_gate/cleanup_observed_seal.py",
    "dev_gate/owner_identity.py",
    "dev_gate/session.py",
    "dev_gate/private_resource_controller.py",
    "dev_gate/private_admission.py",
    "dev_gate/store",
    "e2e_core/stale_lease_reap.py",
    "e2e_core/pytest_dedupe.py",
    "e2e_session_runtime/registry.py",
    "e2e_core/stack_mutation_policy.py",
)


def source_fingerprint(lib_root: Path, sources: Iterable[str]) -> str:
    """`name:mtime_ns` of every existing source, joined by `|`; a package entry lists each of its modules."""
    parts: list[str] = []
    for name in sources:
        path = lib_root / name
        if path.is_dir():
            parts.extend(f"{name}/{module.name}:{module.stat().st_mtime_ns}" for module in sorted(path.glob("*.py")))
        elif path.is_file():
            parts.append(f"{name}:{path.stat().st_mtime_ns}")
    return "|".join(parts)


def coordinator_code_fingerprint() -> str:
    # The dev lib root is the parent of the dev_gate package this module lives in.
    return source_fingerprint(Path(__file__).resolve().parent.parent, COORDINATOR_CODE_SOURCES)
