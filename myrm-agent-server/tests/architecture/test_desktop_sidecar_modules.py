"""Every first-party module the server loads at run time is in the sidecar bundle.

PyInstaller bundles what its scan of `import` statements reaches. The channel registry loads its providers with
`importlib.import_module` over a table of names, so a provider no other code imports was left out of the packaged
backend: the build passed, the backend started, and twenty channel types answered "unavailable" in the installed app
only. `sidecar/bundle_inventory.py` therefore hands PyInstaller every `.py` file of `app/` and of the harness package,
and `bundle_verify.py` reads the finished bundle back. This pins the inventory against the registry and the tree, the
SDKs the bundle leaves out against the code that imports them, the verifier against a bundle that lost a module, and
the channel types the launch smoke creates against the registry and the SDKs.
"""

from __future__ import annotations

import ast
import importlib.util
import os
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from types import ModuleType

import pytest

from tests.support.desktop_release import sidecar_build_module, sidecar_module, smoke_channels_module

# The conftest leaves test_desktop_* to desktop-contracts.yml; this mark also puts the file in the architecture gate.
pytestmark = pytest.mark.architecture

# Code that loads Python from a file path rather than by module name. Such a file is not a module: it has to be shipped
# as data (`script_data_options`), so a new reader must be registered here with how its files reach the bundle.
_PATH_LOADERS = {
    "myrm_agent_harness/toolkits/browser/tools/manage.py": "browser domain skill tool scripts, shipped by domain_tool_scripts",
}
_PATH_LOADING_CALLS = frozenset({"spec_from_file_location", "SourceFileLoader", "run_path"})

# Provider code that imports an SDK at module level, where the import fails without the package: that channel cannot be
# loaded, which the registry reports (`probe_sdk_channel_issues`). Everything else must load without the SDKs.
_SDK_AT_MODULE_LEVEL = {"discord": "app/channels/providers/discord/"}

_PRUNED_DIRS = frozenset({"__pycache__", "node_modules"})
# Under `slack`, `wecom`, ... every channel is a package or a module the registry names; this one is a registry entry.
_A_PROVIDER_MODULE = "app.channels.providers.wecom.aibot_channel"


@pytest.fixture(scope="module")
def build() -> ModuleType:
    return sidecar_build_module()


@pytest.fixture(scope="module")
def inventory() -> ModuleType:
    return sidecar_module("bundle_inventory")


@pytest.fixture(scope="module")
def verify() -> ModuleType:
    return sidecar_module("bundle_verify")


@pytest.fixture(scope="module")
def channels() -> ModuleType:
    return smoke_channels_module()


def _python_files(tree: Path) -> Iterator[Path]:
    for directory, subdirs, names in os.walk(tree):
        subdirs[:] = [name for name in subdirs if name not in _PRUNED_DIRS]
        yield from (Path(directory) / name for name in names if name.endswith(".py"))


def _modules(build: ModuleType, inventory: ModuleType) -> dict[str, list[str]]:
    return inventory.first_party_modules(build.SERVER_ROOT / "app", build.HARNESS_SOURCE_DIR)


def _all_module_names(build: ModuleType, inventory: ModuleType) -> set[str]:
    return {name for names in _modules(build, inventory).values() for name in names}


def test_every_provider_the_channel_registry_imports_by_name_is_in_the_inventory(
    build: ModuleType, inventory: ModuleType
) -> None:
    from app.channels.providers import registry

    # The registry's own table of provider modules, the one `importlib.import_module` is called with.
    wanted = {
        name: importlib.util.resolve_name(spec.module, registry.__package__) for name, spec in registry._BUILTIN_SPECS.items()
    }
    in_inventory = set(_modules(build, inventory)[inventory.SERVER_PACKAGE])

    assert {name: module for name, module in wanted.items() if module not in in_inventory} == {}


def test_every_python_file_of_the_server_and_the_harness_is_a_module_or_a_shipped_script(
    build: ModuleType, inventory: ModuleType
) -> None:
    modules = _modules(build, inventory)
    scripts = inventory.domain_tool_scripts(build.HARNESS_SOURCE_DIR)

    # A file the inventory skipped changes these counts, which are taken by a walk of their own.
    assert len(modules[inventory.SERVER_PACKAGE]) == len(list(_python_files(build.SERVER_ROOT / "app")))
    assert len(modules[inventory.HARNESS_PACKAGE]) + len(scripts) == len(list(_python_files(build.HARNESS_SOURCE_DIR)))
    for names in modules.values():
        assert len(names) == len(set(names)), "a module appears twice"


def test_the_walk_finds_modules_whatever_the_init_files_say(inventory: ModuleType, tmp_path: Path) -> None:
    tree = tmp_path / "pkg"
    files = ("__init__.py", "a/__init__.py", "a/m.py", "b/n.py", "b/c/o.py", "node_modules/x/gyp.py", "__pycache__/z.py")
    for relative in files:
        (tree / relative).parent.mkdir(parents=True, exist_ok=True)
        (tree / relative).write_text("", encoding="utf-8")
    (tree / "data.txt").write_text("", encoding="utf-8")

    # `b` has no __init__.py: the shape that a scan by package walks past.
    assert inventory.package_modules(tree, "pkg") == ["pkg", "pkg.a", "pkg.a.m", "pkg.b.n", "pkg.b.c.o"]


def test_a_python_file_that_is_no_module_and_no_declared_script_fails_the_build(inventory: ModuleType, tmp_path: Path) -> None:
    script = tmp_path / "pkg" / "x-com" / "tool.py"
    script.parent.mkdir(parents=True)
    script.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="cannot be imported by name"):
        inventory.package_modules(tmp_path / "pkg", "pkg")
    assert inventory.package_modules(tmp_path / "pkg", "pkg", {script}) == []


def test_the_domain_tool_scripts_are_the_python_files_of_the_builtin_skills_and_ship_as_data(
    build: ModuleType, inventory: ModuleType
) -> None:
    harness = build.HARNESS_SOURCE_DIR
    declared = set(inventory.domain_tool_scripts(harness))
    on_disk = set(_python_files(harness / inventory.DOMAIN_SKILLS_DIR))
    sep = ";" if build.SYSTEM == "windows" else ":"
    cmd = build.pyinstaller_command(Path("python"), Path("work"))
    added = {
        Path(source): PurePosixPath(destination)
        for spec in (value for flag, value in zip(cmd, cmd[1:], strict=False) if flag == "--add-data")
        for source, destination in [spec.rsplit(sep, 1)]
    }

    assert declared, "the built-in domain skills declare no tool script: nothing for the loader to read"
    assert all(script.is_file() for script in declared), "a manifest names a script that is not there"
    assert on_disk == declared, "a Python file under the built-in skills that no manifest names is shipped by nothing"
    for script in declared:
        mirrored = PurePosixPath(inventory.HARNESS_PACKAGE, *script.parent.relative_to(harness).parts)
        assert added.get(script) == mirrored, f"{script.name} must land at {mirrored} inside the bundle"


def _loads_python_from_a_path(source: str) -> bool:
    if not any(name in source for name in _PATH_LOADING_CALLS):
        return False
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else ""
            if name in _PATH_LOADING_CALLS:
                return True
    return False


def test_every_code_path_that_loads_python_from_a_file_is_registered(build: ModuleType, inventory: ModuleType) -> None:
    trees = {inventory.SERVER_PACKAGE: build.SERVER_ROOT / "app", inventory.HARNESS_PACKAGE: build.HARNESS_SOURCE_DIR}
    loaders = {
        f"{package}/{path.relative_to(tree).as_posix()}"
        for package, tree in trees.items()
        for path in _python_files(tree)
        if _loads_python_from_a_path(path.read_text(encoding="utf-8"))
    }

    assert loaders - set(_PATH_LOADERS) == set(), (
        "these modules load Python from a file path; such files are not modules, so ship them as data "
        "(script_data_options in sidecar/bundle_inventory.py) and register the reader in _PATH_LOADERS"
    )
    assert set(_PATH_LOADERS) - loaders == set(), "these modules no longer load Python from a path; drop them from the registry"
    assert _loads_python_from_a_path("import importlib.util as u\nu.spec_from_file_location('m', path)")
    assert not _loads_python_from_a_path("from importlib.util import find_spec\nfind_spec('m')")


def test_the_command_runs_the_inventory_hooks_and_leaves_out_the_channel_sdks(build: ModuleType, inventory: ModuleType) -> None:
    cmd = build.pyinstaller_command(Path("python"), Path("work"))
    options = set(zip(cmd, cmd[1:], strict=False))

    assert ("--additional-hooks-dir", str(Path("work") / inventory.HOOKS_DIR)) in options
    # The harness hook runs when the package is part of the build; the server's runs because its entry script imports it.
    assert ("--hidden-import", inventory.HARNESS_PACKAGE) in options
    assert {("--exclude-module", sdk) for sdk in inventory.CHANNEL_SDKS_NOT_SHIPPED} <= options


def test_each_generated_hook_is_named_after_its_package_and_lists_exactly_its_modules(
    build: ModuleType, inventory: ModuleType, tmp_path: Path
) -> None:
    inventory.write_inventory_hooks(tmp_path / "hooks", build.SERVER_ROOT / "app", build.HARNESS_SOURCE_DIR)

    for package, modules in _modules(build, inventory).items():
        tree = ast.parse((tmp_path / "hooks" / f"hook-{package}.py").read_text(encoding="utf-8"))
        assigned = [node for node in tree.body if isinstance(node, ast.Assign)]
        assert [target.id for node in assigned for target in node.targets if isinstance(target, ast.Name)] == ["hiddenimports"]
        assert ast.literal_eval(assigned[0].value) == modules


def test_every_channel_sdk_left_out_belongs_to_a_channel_the_registry_reports_when_it_is_missing(
    inventory: ModuleType,
) -> None:
    from app.channels.providers import registry

    for sdk, left_out in inventory.CHANNEL_SDKS_NOT_SHIPPED.items():
        spec = registry._BUILTIN_SPECS.get(left_out.channel)
        assert spec is not None and spec.sdk_package, f"{sdk}: {left_out.channel} is no channel that names an SDK"
        assert left_out.channel in registry._LAZY_SDK_CHANNEL_NAMES, f"{sdk}: the settings page would not report it"
        assert left_out.reason.strip(), f"{sdk}: a package left out of the bundle needs the reason"


def _module_level_sdk_imports(source: str, sdks: frozenset[str]) -> set[str]:
    """SDK packages imported by a statement of the module body itself; `try`, `if` and function bodies are not."""
    if not any(sdk in source for sdk in sdks):
        return set()
    found: set[str] = set()
    for node in ast.parse(source).body:
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module.split(".")[0])
    return found & sdks


def test_only_the_provider_that_needs_its_sdk_at_import_fails_to_load_without_the_sdks(
    build: ModuleType, inventory: ModuleType
) -> None:
    sdks = frozenset(inventory.CHANNEL_SDKS_NOT_SHIPPED)
    server = build.SERVER_ROOT
    importers = [
        path.relative_to(server).as_posix()
        for path in _python_files(server / "app")
        if _module_level_sdk_imports(path.read_text(encoding="utf-8"), sdks)
    ]

    stray = [path for path in importers if not any(path.startswith(prefix) for prefix in _SDK_AT_MODULE_LEVEL.values())]
    assert stray == [], (
        "these modules import a channel SDK at module level, so their channel cannot load in a bundle without the SDK; "
        f"import it lazily or guard the import: {stray}"
    )
    for channel, prefix in _SDK_AT_MODULE_LEVEL.items():
        assert any(path.startswith(prefix) for path in importers), f"{channel} no longer needs its SDK at import: drop it"
    assert _module_level_sdk_imports("import discord.opus\nx = 1", sdks) == {"discord"}
    assert _module_level_sdk_imports("try:\n    import mautrix\nexcept ImportError:\n    pass\n", sdks) == set()
    assert _module_level_sdk_imports("def f():\n    import mautrix\n", sdks) == set()


def test_the_launch_smoke_creates_exactly_the_channel_types_the_registry_offers(channels: ModuleType) -> None:
    from app.channels.providers import registry

    assert sorted(channels.CHANNEL_TYPES) == sorted(registry._BUILTIN_SPECS), "update CHANNEL_TYPES in smoke_channels.py"


def test_the_launch_smoke_accepts_a_refusal_only_where_the_provider_cannot_load_without_its_sdk(
    channels: ModuleType, inventory: ModuleType
) -> None:
    left_out_channels = {left_out.channel for left_out in inventory.CHANNEL_SDKS_NOT_SHIPPED.values()}

    assert channels.UNAVAILABLE_WITHOUT_SDK == frozenset(_SDK_AT_MODULE_LEVEL)
    assert channels.UNAVAILABLE_WITHOUT_SDK <= left_out_channels


def _bundle_with(tmp_path: Path, build: ModuleType, inventory: ModuleType, *, scripts: bool = True, data: bool = True) -> Path:
    """A bundle directory whose `_internal` holds the domain tool scripts and the harness data files (or not)."""
    executable = tmp_path / "bundle" / "backend"
    executable.parent.mkdir(parents=True)
    harness = build.HARNESS_SOURCE_DIR
    shipped = [
        *(inventory.domain_tool_scripts(harness) if scripts else []),
        *(inventory.harness_data_files(harness) if data else []),
    ]
    for file in shipped:
        target = executable.parent / "_internal" / inventory.HARNESS_PACKAGE / file.relative_to(harness)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("", encoding="utf-8")
    return executable


def _problems(
    verify: ModuleType, monkeypatch: pytest.MonkeyPatch, build: ModuleType, executable: Path, bundled: set[str]
) -> list[str]:
    monkeypatch.setattr(verify, "bundled_module_names", lambda _executable: bundled)
    return verify.bundle_problems(executable, build.SERVER_ROOT / "app", build.HARNESS_SOURCE_DIR)


def test_the_verifier_accepts_a_bundle_that_holds_everything_the_inventory_asks_for(
    build: ModuleType, inventory: ModuleType, verify: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = _bundle_with(tmp_path, build, inventory)

    assert _problems(verify, monkeypatch, build, executable, _all_module_names(build, inventory)) == []


def test_the_verifier_names_a_lost_module_a_channel_sdk_that_got_in_and_a_script_that_is_absent(
    build: ModuleType, inventory: ModuleType, verify: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    everything = _all_module_names(build, inventory)
    assert _A_PROVIDER_MODULE in everything
    executable = _bundle_with(tmp_path, build, inventory, scripts=False)

    problems = _problems(verify, monkeypatch, build, executable, {*everything - {_A_PROVIDER_MODULE}, "mautrix.client"})

    assert len(problems) == 3
    assert "1 of" in problems[0] and _A_PROVIDER_MODULE in problems[0]
    assert "mautrix" in problems[1]
    assert "domain tool scripts are not in the bundle" in problems[2]


def test_the_verifier_names_each_harness_data_file_the_bundle_lost(
    build: ModuleType, inventory: ModuleType, verify: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = _bundle_with(tmp_path, build, inventory, data=False)

    problems = _problems(verify, monkeypatch, build, executable, _all_module_names(build, inventory))

    data_files = inventory.harness_data_files(build.HARNESS_SOURCE_DIR)
    assert len(problems) == 1
    assert f"{len(data_files)} of {len(data_files)} harness data files are not in the bundle" in problems[0]
    assert all(file.name in problems[0] for file in data_files)


def test_the_verifier_names_only_the_data_file_that_is_missing(
    build: ModuleType, inventory: ModuleType, verify: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = _bundle_with(tmp_path, build, inventory)
    data_files = inventory.harness_data_files(build.HARNESS_SOURCE_DIR)
    lost = next(path for path in data_files if path.name != "model_catalog.json")
    (executable.parent / "_internal" / inventory.HARNESS_PACKAGE / lost.relative_to(build.HARNESS_SOURCE_DIR)).unlink()

    problems = _problems(verify, monkeypatch, build, executable, _all_module_names(build, inventory))

    assert len(problems) == 1
    assert lost.name in problems[0] and "model_catalog.json" not in problems[0]


def test_the_harness_data_the_runtime_reads_by_path_is_the_catalog_and_the_token_tables(
    build: ModuleType, inventory: ModuleType
) -> None:
    files = inventory.harness_data_files(build.HARNESS_SOURCE_DIR)
    relative = {PurePosixPath(*file.relative_to(build.HARNESS_SOURCE_DIR).parts) for file in files}

    assert PurePosixPath("toolkits/llms/catalog/data/model_catalog.json") in relative
    assert sum(path.parent == PurePosixPath("utils/_tiktoken_tables") for path in relative) == 3


def test_a_data_directory_the_harness_moved_fails_the_build_instead_of_shipping_nothing(
    inventory: ModuleType, tmp_path: Path
) -> None:
    for directory in inventory.HARNESS_DATA_DIRS:
        (tmp_path / directory).mkdir(parents=True)
        (tmp_path / directory / "data.json").write_text("{}", encoding="utf-8")
    assert len(inventory.harness_data_files(tmp_path)) == len(inventory.HARNESS_DATA_DIRS)

    only_code = tmp_path / inventory.HARNESS_DATA_DIRS[0]
    (only_code / "data.json").unlink()
    (only_code / "helper.py").write_text("", encoding="utf-8")
    (only_code / "__pycache__").mkdir()
    (only_code / "__pycache__" / "cached.dat").write_text("", encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="holds no data file"):
        inventory.harness_data_files(tmp_path)
