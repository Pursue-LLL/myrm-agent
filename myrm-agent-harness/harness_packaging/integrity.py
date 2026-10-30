"""Map manifest module files to import names, source paths, and drift-gate checks."""

from __future__ import annotations

import re
import zipfile
from collections.abc import Sequence
from enum import StrEnum
from pathlib import Path

from harness_packaging.manifest import load_core_manifest, repo_root
from harness_packaging.native_arch import HEADER_BYTES, native_binary_machines
from harness_packaging.platforms import platform_spec_for_key
from harness_packaging.release import manifest_source_paths


def module_file_to_import_name(module_file: Path, src_root: Path) -> str:
    """Return the dotted import path for a module file under ``myrm_agent_harness``."""
    rel = module_file.relative_to(src_root)
    if rel.name == "__init__.py":
        parts = rel.parent.parts
    else:
        parts = rel.with_suffix("").parts
    return f"myrm_agent_harness.{'.'.join(parts)}"


def module_file_to_source_relpath(module_file: Path, src_root: Path) -> str:
    """Return wheel/source path relative to ``myrm_agent_harness/``."""
    rel = module_file.relative_to(src_root)
    return rel.as_posix()


def manifest_import_names() -> tuple[str, ...]:
    """Return deduplicated import paths for manifest modules."""
    manifest = load_core_manifest()
    src_root = repo_root() / "src" / "myrm_agent_harness"
    seen: dict[str, None] = {}
    for module_file in manifest.module_paths:
        seen[module_file_to_import_name(module_file, src_root)] = None
    return tuple(seen)


def manifest_source_relpaths() -> tuple[str, ...]:
    """Return ``myrm_agent_harness/``-relative ``.py`` paths for manifest modules."""
    manifest = load_core_manifest()
    src_root = repo_root() / "src" / "myrm_agent_harness"
    return tuple(module_file_to_source_relpath(module_file, src_root) for module_file in manifest.module_paths)


def verify_manifest_imports() -> None:
    """Import every manifest module (post-install CI/Docker verification)."""
    import importlib

    for import_name in manifest_import_names():
        importlib.import_module(import_name)


DISTRIBUTION_PUBLIC_MARKER = "@distribution-public"

_MARKER_SCAN_BYTES = 4096

# Sibling zones: new subdirectories/files outside known public trees need manifest or marker.
_PARENT_WATCH_ZONES: tuple[tuple[str, frozenset[str]], ...] = (
    (
        "agent/skills/",
        frozenset(
            {
                "autonomous_visualization",
                "bundle_warmup",
                "curator",
                "market",
                "mcp",
                "optimization",
                "packaging",
                "runtime",
                "security",
                "sync",
            }
        ),
    ),
    (
        "agent/context_management/",
        frozenset(
            {
                "archive_checkpoint",
                "capability_matrix",
                "desktop_repl",
                "downshift",
                "infra",
                "prefix_caching_ledger",
                "scratchpad_promotion",
                "strategies",
                "title_recovery",
                "tracking",
                "two_stage_search_extract",
                "eviction_marks",
            }
        ),
    ),
    (
        "toolkits/memory/",
        frozenset(
            {
                "graph",
                "integration",
                "protocols",
                "relational",
                "_manager",
                "conversation_search",
                "_internal",
                "agent_surface",
                "external_providers",
                "handoff",
                "onboarding",
                # Feature packages shipped as readable source; list a package in core_manifest.yaml to compile it.
                "budget_packing",
                "chunking",
                "ephemeral",
                "ephemeral_delta",
                "mem_cube",
                "private_notebook",
                "score_honesty",
                "two_layer_dialectic",
            }
        ),
    ),
)


def _file_has_public_marker(module_file: Path) -> bool:
    head = module_file.read_bytes()[:_MARKER_SCAN_BYTES].decode("utf-8", errors="ignore")
    return DISTRIBUTION_PUBLIC_MARKER in head


def manifest_watch_violations() -> tuple[str, ...]:
    """Return ``myrm_agent_harness/``-relative paths missing manifest coverage or public marker.

    Coverage is judged by ``manifest_source_paths()``, the very list the release wheel
    strips and ``build_core.py`` compiles. Reading that list here keeps a single source
    of truth: a module covered by the manifest can never be silently shipped in clear,
    and no second registry has to be kept in step. A package ``__init__.py`` is skipped
    because the manifest intentionally leaves those as readable re-export stubs.
    """
    manifest_relpaths = frozenset(manifest_source_paths())
    src_root = repo_root() / "src" / "myrm_agent_harness"
    violations: list[str] = []

    for parent_prefix, public_subdirs in _PARENT_WATCH_ZONES:
        zone_root = src_root / parent_prefix
        if not zone_root.is_dir():
            continue
        for module_file in sorted(zone_root.rglob("*.py")):
            rel = module_file.relative_to(src_root).as_posix()
            if module_file.name == "__init__.py":
                continue
            rel_to_parent = module_file.relative_to(zone_root)
            if len(rel_to_parent.parts) == 1:
                continue
            if rel_to_parent.parts[0] in public_subdirs:
                continue
            if f"myrm_agent_harness/{rel}" in manifest_relpaths:
                continue
            if _file_has_public_marker(module_file):
                continue
            violations.append(rel)

    return tuple(violations)


def stale_public_subdirs() -> tuple[str, ...]:
    """Return allowlist paths in ``_PARENT_WATCH_ZONES`` that no longer name a directory.

    A ``<zone>/<name>`` entry outliving its directory would exempt any directory later created
    under it from the manifest-or-marker check in ``manifest_watch_violations``. A zone whose own
    directory is gone is reported as the zone path itself, because ``manifest_watch_violations``
    skips such a zone and the watch would otherwise stop without any failure.
    """
    src_root = repo_root() / "src" / "myrm_agent_harness"
    stale: list[str] = []
    for parent_prefix, public_subdirs in _PARENT_WATCH_ZONES:
        zone_root = src_root / parent_prefix
        if not zone_root.is_dir():
            stale.append(parent_prefix)
            continue
        stale.extend(f"{parent_prefix}{name}" for name in sorted(public_subdirs) if not (zone_root / name).is_dir())
    return tuple(stale)


class DistributionWheelRole(StrEnum):
    """Built wheel kind for distribution artifact verification."""

    RELEASE = "release"
    CORE = "core"


class DistributionWheelArtifactError(ValueError):
    """Raised when a built wheel violates release or core artifact rules."""


_FORBIDDEN_DEBUG_SUFFIXES: tuple[str, ...] = (".map", ".c.src")

_CORE_PACKAGE_INIT_RELPATH = "myrm_agent_harness_core/__init__.py"
_UNKNOWN_PLATFORM_KEY_MARKER = '__platform_key__: str = "unknown"'
_STAMPED_PLATFORM_KEY = re.compile(r'^__platform_key__: str = "(?P<key>[^"]+)"', re.MULTILINE)
_NATIVE_SUFFIXES = (".so", ".pyd")
_PREVIEW_ITEMS = 3


def _manifest_compiled_prefix(manifest_py: str) -> str:
    """Return the wheel entry prefix for a manifest module's Nuitka artifact."""
    if not manifest_py.endswith(".py"):
        msg = f"Expected manifest path ending in .py, got: {manifest_py!r}"
        raise ValueError(msg)
    if manifest_py.endswith("/__init__.py"):
        parent_dir = manifest_py[: -len("/__init__.py")]
        stem = parent_dir.rsplit("/", 1)[-1]
        return f"{parent_dir}/{stem}."
    return f"{manifest_py[:-3]}."


def manifest_compiled_artifact_prefix(manifest_wheel_py: str) -> str:
    """Return the wheel zip entry prefix for a manifest module's compiled artifact."""
    return _manifest_compiled_prefix(manifest_wheel_py)


def _wheel_zip_entries(wheel_path: Path) -> tuple[str, ...]:
    with zipfile.ZipFile(wheel_path, "r") as zf:
        return tuple(zf.namelist())


def _forbidden_debug_entries(entries: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(name for name in entries if name.endswith(_FORBIDDEN_DEBUG_SUFFIXES))


def _has_compiled_artifact(entries: tuple[str, ...], manifest_py: str) -> bool:
    prefix = _manifest_compiled_prefix(manifest_py)
    return any(name.startswith(prefix) and name.endswith(_NATIVE_SUFFIXES) for name in entries)


def _preview(items: Sequence[str]) -> str:
    """First few entries of a violation list, with the count of the rest."""
    shown = ", ".join(items[:_PREVIEW_ITEMS])
    return f"{shown} (+{len(items) - _PREVIEW_ITEMS} more)" if len(items) > _PREVIEW_ITEMS else shown


def _read_wheel_entry_text(wheel_path: Path, entry_name: str) -> str | None:
    with zipfile.ZipFile(wheel_path, "r") as zf:
        try:
            return zf.read(entry_name).decode("utf-8")
        except KeyError:
            return None


def _compiled_architecture_violations(
    wheel_path: Path, entries: tuple[str, ...], platform_key: str, machine: str
) -> tuple[str, ...]:
    """Compiled modules that hold no code for ``machine``: the loader rejects code built for another CPU."""
    wrong: list[str] = []
    with zipfile.ZipFile(wheel_path, "r") as zf:
        for name in entries:
            if not name.endswith(_NATIVE_SUFFIXES):
                continue
            with zf.open(name) as artifact:
                found = native_binary_machines(artifact.read(HEADER_BYTES))
            if machine not in found:
                wrong.append(f"{name.rsplit('/', 1)[-1]} ({'/'.join(sorted(found)) or 'not an x64/arm64 binary'})")
    if not wrong:
        return ()
    return (f"Compiled modules must hold {machine} code for platform key {platform_key}: {_preview(wrong)}",)


def _core_wheel_platform_violations(wheel_path: Path, entries: tuple[str, ...]) -> tuple[str, ...]:
    """Fail closed when a core wheel has no stamped platform key or its binaries are for another CPU."""
    init_text = _read_wheel_entry_text(wheel_path, _CORE_PACKAGE_INIT_RELPATH)
    if init_text is None:
        return (
            f"Core wheel missing {_CORE_PACKAGE_INIT_RELPATH} "
            "(expected stamped myrm_agent_harness_core package metadata).",
        )
    if _UNKNOWN_PLATFORM_KEY_MARKER in init_text:
        return (
            "Core wheel platform key is still 'unknown'; rebuild with scripts/build_core.py / assemble_production.",
        )
    stamped = _STAMPED_PLATFORM_KEY.search(init_text)
    if stamped is None:
        return (f"Core wheel does not stamp __platform_key__ in {_CORE_PACKAGE_INIT_RELPATH}.",)
    platform_key = stamped.group("key")
    try:
        machine = platform_spec_for_key(platform_key).machine
    except ValueError:
        return (f"Core wheel platform key {platform_key!r} is not a platform the release builds.",)
    return _compiled_architecture_violations(wheel_path, entries, platform_key, machine)


def distribution_wheel_artifact_violations(
    wheel_path: Path,
    *,
    role: DistributionWheelRole,
) -> tuple[str, ...]:
    """Return human-readable violations for a release or platform core wheel."""
    if not wheel_path.is_file():
        return (f"Wheel file not found: {wheel_path}",)

    try:
        entries = _wheel_zip_entries(wheel_path)
    except zipfile.BadZipFile:
        return (f"Invalid wheel zip: {wheel_path.name}",)

    entry_set = frozenset(entries)
    violations: list[str] = []

    manifest_paths = manifest_source_paths()
    leaked = [path for path in manifest_paths if path in entry_set]
    if leaked:
        violations.append(f"Manifest .py source must not ship in wheel: {_preview(leaked)}")

    debug_entries = _forbidden_debug_entries(entries)
    if debug_entries:
        violations.append(f"Debug mapping artifacts must not ship in wheel: {_preview(debug_entries)}")

    if role is DistributionWheelRole.CORE:
        missing_compiled = [path for path in manifest_paths if not _has_compiled_artifact(entries, path)]
        if missing_compiled:
            violations.append(f"Missing Nuitka .so/.pyd for manifest modules: {_preview(missing_compiled)}")

        violations.extend(_core_wheel_platform_violations(wheel_path, entries))

    return tuple(violations)


def verify_distribution_wheel_artifact(
    wheel_path: Path,
    *,
    role: DistributionWheelRole,
) -> None:
    """Fail closed when a built wheel violates distribution artifact rules."""
    violations = distribution_wheel_artifact_violations(wheel_path, role=role)
    if not violations:
        return
    joined = "\n  - ".join(violations)
    msg = f"Distribution wheel artifact violations ({role.value}) in {wheel_path.name}:\n  - {joined}"
    raise DistributionWheelArtifactError(msg)
