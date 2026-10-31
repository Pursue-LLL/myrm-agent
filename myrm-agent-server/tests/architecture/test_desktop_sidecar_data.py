"""Every data file the server reads from its source tree ships in the sidecar bundle.

PyInstaller archives Python only. Code that opens a file by a path built from `__file__` finds it in a source
checkout and finds nothing in the packaged app, where the registries answer with empty lists and no health check
fails: no skills, no agent templates, no integration catalog, no search providers, and untranslated channel texts.
`SERVER_DATA` in `sidecar/build.py` is what the bundle adds. This pins it against the tree and against the code that
reads it, so data added without a bundle entry, or a new reader nobody asked the bundling question of, fails here
instead of in an installed app.
"""

from __future__ import annotations

import ast
import os
from collections.abc import Callable, Iterator
from pathlib import Path, PurePosixPath
from types import ModuleType

import pytest

from tests.support.desktop_release import sidecar_build_module

# server-architecture.yml runs `-m architecture` on every change under app/ and assets/, which is when this can break.
pytestmark = pytest.mark.architecture

# Modules that open data through a path built from `__file__`, and the path they open (under the server root).
_DATA_READERS = {
    "app/ai_agents/subagent_catalog.py": "app/config/subagents",
    "app/ai_agents/subagent_presets.py": "app/config/subagents",
    "app/api/integrations/hardware/model_specs.py": "assets/cookbook_specs.json",
    "app/channels/i18n/engine.py": "app/channels/i18n/locales",
    "app/channels/providers/whatsapp/helpers.py": "app/channels/providers/whatsapp/bridge",
    "app/core/eval/locomo.py": "app/core/eval/fixtures",
    "app/core/integrations/catalog/registry.py": "app/core/integrations/catalog/data",
    "app/core/integrations/search_catalog/registry.py": "app/core/integrations/search_catalog/manifest.json",
    "app/core/skills/prebuilt_sync.py": "assets/prebuilt_skills",
    "app/services/agent/template_utils.py": "assets/prebuilt_agents",
    "app/services/kanban/pipeline/spec_io.py": "assets/prebuilt_skills",
}

# Modules that use `__file__` for something else, and why a bundle without that file is fine.
_OTHER_FILE_USES = {
    "app/config/settings.py": "BASE_DIR, the base of paths the settings let the environment override",
    "app/core/infra/frontend_launcher.py": "starts the Next.js dev server of a checkout; the shell starts the bundled one",
    "app/services/agent/params/providers.py": "reads the provider remap from the bundle's shared/config before any checkout path",
    "app/startup/env_loader.py": "optional .env files and the checkout's harness browser directory, both skipped when absent",
    "app/startup/local_search_bootstrap.py": "docker-compose.yaml of a checkout, skipped with a warning when absent",
}

# A `Path("assets/...")` built from a literal finds the file in a checkout run from the server root and nothing in an
# installed app, which starts the backend in its own data directory. Only a literal that starts at one of these roots
# is flagged, and the modules below are the exceptions, with the reason.
_CWD_RELATIVE_ROOTS = frozenset({"app", "assets", "shared"})
_CWD_RELATIVE_OK = {
    "app/services/agent/params/providers.py": "the last candidate for the provider remap, tried after the bundle's own copy",
}

# What counts as data in the tree: everything under assets/, and under app/ every file that is not Python, not a
# cache and not documentation (the code reads no markdown from app/; the skills it does read live in assets/).
_PRUNED_DIRS = frozenset({"__pycache__", "node_modules"})
_NOT_DATA_SUFFIXES = frozenset({".py", ".pyc", ".md"})


@pytest.fixture(scope="module")
def build() -> ModuleType:
    return sidecar_build_module()


def _data_files(server_root: Path) -> list[str]:
    found: list[str] = []
    for top in ("app", "assets"):
        for directory, subdirs, names in os.walk(server_root / top):
            subdirs[:] = [name for name in subdirs if name not in _PRUNED_DIRS]
            for name in names:
                if name == ".DS_Store" or (top == "app" and Path(name).suffix in _NOT_DATA_SUFFIXES):
                    continue
                found.append((Path(directory) / name).relative_to(server_root).as_posix())
    return sorted(found)


def _app_modules(server_root: Path) -> Iterator[Path]:
    for directory, subdirs, names in os.walk(server_root / "app"):
        subdirs[:] = [name for name in subdirs if name not in _PRUNED_DIRS]
        yield from (Path(directory) / name for name in names if name.endswith(".py"))


def _uses_file(source: str) -> bool:
    """True when the code names `__file__`; a docstring or comment that mentions it does not count."""
    return "__file__" in source and any(
        isinstance(node, ast.Name) and node.id == "__file__" for node in ast.walk(ast.parse(source))
    )


def _names_data_relative_to_cwd(source: str) -> bool:
    """True when the code builds a `Path` from a literal that starts at a bundled data root, e.g. `Path("assets/x")`."""
    if "Path(" not in source:
        return False
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Path" and node.args:
            literal = node.args[0]
            if isinstance(literal, ast.Constant) and isinstance(literal.value, str):
                if PurePosixPath(literal.value).parts[:1] and PurePosixPath(literal.value).parts[0] in _CWD_RELATIVE_ROOTS:
                    return True
    return False


def _modules_where(server_root: Path, detector: Callable[[str], bool]) -> set[str]:
    return {
        path.relative_to(server_root).as_posix()
        for path in _app_modules(server_root)
        if detector(path.read_text(encoding="utf-8"))
    }


def _covers(entry: str, path: str) -> bool:
    """Whether `entry` (a file or a directory, relative to the server root) is `path` or holds it."""
    return path == entry or path.startswith(f"{entry}/")


def _accounted_for(path: str, build: ModuleType) -> bool:
    return any(_covers(entry, path) for entry in (*build.SERVER_DATA, *build.SERVER_DATA_NOT_SHIPPED))


def test_every_module_that_builds_a_path_from_file_is_accounted_for(build: ModuleType) -> None:
    using = _modules_where(build.SERVER_ROOT, _uses_file)
    known = set(_DATA_READERS) | set(_OTHER_FILE_USES)

    assert using - known == set(), (
        "these modules build a path from __file__; register what they open in _DATA_READERS (it must be bundled) "
        "or why it does not matter in _OTHER_FILE_USES"
    )
    assert known - using == set(), "these modules no longer use __file__; drop them from the registry"


def test_no_module_names_bundled_data_relative_to_the_working_directory(build: ModuleType) -> None:
    offenders = _modules_where(build.SERVER_ROOT, _names_data_relative_to_cwd)

    assert offenders - set(_CWD_RELATIVE_OK) == set(), (
        "these modules build a Path from a literal rooted at a bundled data directory, which only resolves when the "
        "process starts in the server root; anchor it on __file__ (and register the reader in _DATA_READERS)"
    )
    assert set(_CWD_RELATIVE_OK) - offenders == set(), "these modules no longer do; drop them from _CWD_RELATIVE_OK"


def test_the_data_each_reader_opens_is_bundled_or_declared_not_shipped(build: ModuleType) -> None:
    unaccounted = {
        module: opened
        for module, opened in _DATA_READERS.items()
        if not (build.SERVER_ROOT / opened).exists() or not _accounted_for(opened, build)
    }

    assert unaccounted == {}, "add each missing path to SERVER_DATA in sidecar/build.py (or fix the registry)"


def test_every_data_file_under_app_and_assets_is_bundled_or_declared_not_shipped(build: ModuleType) -> None:
    unaccounted = [path for path in _data_files(build.SERVER_ROOT) if not _accounted_for(path, build)]

    assert unaccounted == [], (
        f"{len(unaccounted)} data files are in no SERVER_DATA entry, the packaged app would not have them: {unaccounted[:10]}"
    )


def test_the_bundle_list_names_existing_paths_and_never_both_ships_and_drops_one(build: ModuleType) -> None:
    root = build.SERVER_ROOT
    missing = [entry for entry in (*build.SERVER_DATA, *build.SERVER_DATA_NOT_SHIPPED) if not (root / entry).exists()]
    contradictions = [
        (shipped, dropped)
        for shipped in build.SERVER_DATA
        for dropped in build.SERVER_DATA_NOT_SHIPPED
        if _covers(shipped, dropped) or _covers(dropped, shipped)
    ]
    unexplained = [entry for entry, reason in build.SERVER_DATA_NOT_SHIPPED.items() if not reason.strip()]

    assert missing == [], "these paths are not in the tree: PyInstaller would fail on them, or the entry is stale"
    assert contradictions == [], "these paths are both shipped and declared not shipped"
    assert unexplained == [], "a path left out of the bundle needs the reason"


def test_pyinstaller_places_every_entry_at_its_own_relative_path(build: ModuleType) -> None:
    sep = ";" if build.SYSTEM == "windows" else ":"
    cmd = build.pyinstaller_command(Path("python"), Path("work"))
    added = {
        Path(source): PurePosixPath(destination)
        for spec in (value for flag, value in zip(cmd, cmd[1:], strict=False) if flag == "--add-data")
        for source, destination in [spec.rsplit(sep, 1)]
    }

    for entry in build.SERVER_DATA:
        source = build.SERVER_ROOT / entry
        mirrored = PurePosixPath(entry) if source.is_dir() else PurePosixPath(entry).parent
        assert added.get(source) == mirrored, f"{entry} must land at {mirrored} inside the bundle"
    assert added[build.SHARED_PROVIDER_REMAP] == PurePosixPath("shared/config")


def test_the_detector_flags_an_unbundled_file_and_accepts_a_bundled_or_dropped_one(build: ModuleType) -> None:
    assert _accounted_for("assets/prebuilt_skills/x/SKILL.md", build)
    assert _accounted_for("app/core/integrations/search_catalog/manifest.json", build)
    assert _accounted_for("app/channels/providers/whatsapp/bridge/package.json", build)
    assert not _accounted_for("app/core/new_feature/data.json", build)
    # A sibling directory that merely shares a prefix is not covered.
    assert not _accounted_for("assets_extra/data.json", build)
    assert not _covers("app/config/subagents", "app/config/subagents_other/x.yaml")
    assert _uses_file("from pathlib import Path\nP = Path(__file__).parent")
    assert not _uses_file('"""Resolved from __file__."""\nx = 1  # __file__')
    assert _names_data_relative_to_cwd('from pathlib import Path\nP = Path("assets/prebuilt_skills") / name')
    assert _names_data_relative_to_cwd('from pathlib import Path\nP = Path("shared") / "config"')
    assert not _names_data_relative_to_cwd('from pathlib import Path\nP = Path(__file__).parent / "assets"')
    assert not _names_data_relative_to_cwd('from pathlib import Path\nP = Path("/opt/homebrew/bin/bun")')
    assert not _names_data_relative_to_cwd('print("assets/example.html")')
