"""First-party Python that the sidecar bundle must contain, read off the source trees instead of the import scan.

PyInstaller bundles the modules that its scan of `import` statements reaches. The server also loads parts of itself
under a name it computes at run time (the channel registry calls `importlib.import_module` on a table of provider
modules) and nothing in the scan connects such a string to a file: a provider that no code imports is left out of the
bundle, the build succeeds, the backend starts, and the channel answers "unavailable" in the packaged app only.

So the build does not trust the scan for first-party code. Every `.py` file of the server's `app/` and of the harness
package becomes a hidden import, whatever imports it and whether or not its directory has an `__init__.py`. One
generated hook per top-level package carries the list, which keeps the PyInstaller command line short.

One kind of Python file is not a module: the tool scripts of the built-in browser domain skills. The harness reads each
as text from `domain_skills/builtin/<skill>/<path in the skill's manifest>` and executes it. They are shipped as data at
their own relative path, because `--collect-data` leaves `.py` files out and a skill directory such as `x-com` is not an
importable name.

The data files the harness reads by `__file__` are shipped by `--collect-data`; the build does not take that on trust
either, and bundle_verify.py looks for the files this module lists.

[INPUT]
- The server's `app/` and the harness package source trees (POS: the first-party code the bundle must contain)
- The build's Python interpreter (POS: asked where an installed package lives, without importing it)

[OUTPUT]
- first_party_modules, write_inventory_hooks: every first-party module as a hidden import, one generated hook per
  top-level package
- domain_tool_scripts, script_data_options: the domain skills' tool scripts, shipped as data at their own relative path
- harness_data_files, HARNESS_DATA_DIRS: the data files the harness reads by `__file__`
- CHANNEL_SDKS_NOT_SHIPPED, exclude_options: the channel SDKs the bundle leaves out
- installed_package_dir: the directory the build's Python imports a package from
- HARNESS_PACKAGE, HOOKS_DIR: the harness package's import name and the directory name of the generated hooks

[POS]
Single source of truth for what the sidecar bundle must contain and which channel SDKs stay out: build.py turns it
into PyInstaller options and bundle_verify.py checks the finished bundle against it.
"""

from __future__ import annotations

import json
import keyword
import os
import subprocess
from collections.abc import Collection
from pathlib import Path, PurePosixPath
from typing import NamedTuple

SERVER_PACKAGE = "app"
HARNESS_PACKAGE = "myrm_agent_harness"
# Name of the directory, under the build's work directory, that holds the generated hooks.
HOOKS_DIR = "hooks"

# Where the harness keeps its built-in domain skills, relative to the harness package.
DOMAIN_SKILLS_DIR = PurePosixPath("toolkits/browser/domain_skills/builtin")

# Data the harness reads by ``__file__`` and cannot serve a model call without, relative to the harness package: the
# model catalog (context windows, prices and capabilities) and the token-count tables. A bundle that lacks one still
# builds and starts, and the catalog then answers with nothing and token counts reach for the network.
HARNESS_DATA_DIRS = (PurePosixPath("toolkits/llms/catalog/data"), PurePosixPath("utils/_tiktoken_tables"))

# Directories that hold no first-party code: caches, and what a developer's `npm install` leaves in the WhatsApp bridge.
_PRUNED_DIRS = frozenset({"__pycache__", "node_modules"})


class LeftOut(NamedTuple):
    """A third-party package the bundle leaves out although first-party code imports it."""

    channel: str  # the channel type that needs the package; the settings page reports it as unavailable
    reason: str


# Channel SDKs left out of the desktop bundle: the providers that use them load the SDK at start-up, which lengthens
# every launch and enlarges the bundle, and whether the desktop app offers these channels is an open product decision.
# With every provider in the inventory PyInstaller scans their `import discord` / `import mautrix` statements and would
# pull the SDKs in; `--exclude-module` keeps them out, and bundle_verify.py proves they are out. The architecture test
# test_desktop_sidecar_modules.py ties each entry to a channel that the registry reports when its SDK is missing.
CHANNEL_SDKS_NOT_SHIPPED = {
    "discord": LeftOut("discord", "discord.py (extra channels-sdk), imported at module level by the Discord provider"),
    "davey": LeftOut("discord", "end-to-end encryption of Discord voice, installed with discord.py[voice]"),
    "mautrix": LeftOut("matrix", "the Matrix client library (extra matrix)"),
    "aiohttp_socks": LeftOut("matrix", "SOCKS proxy support of the Matrix client (extra matrix)"),
}


def installed_package_dir(python: Path, package: str) -> Path:
    """The directory `python` imports `package` from, found without importing the package."""
    probe = (
        "import importlib.util, sys\n"
        "spec = importlib.util.find_spec(sys.argv[1])\n"
        "print(spec.submodule_search_locations[0] if spec and spec.submodule_search_locations else '')"
    )
    # UTF-8 on both ends: the child encodes its output with the locale's code page otherwise, and a path in a user
    # name the code page cannot hold would not survive the pipe.
    found = subprocess.run(
        [str(python), "-X", "utf8", "-c", probe, package], check=True, capture_output=True, encoding="utf-8"
    ).stdout.strip()
    if not found:
        raise FileNotFoundError(f"{package} is not installed for {python}")
    return Path(found)


def domain_tool_scripts(harness_dir: Path) -> list[Path]:
    """The Python tool scripts that the built-in domain skills name in their manifests (`python_tools.<tool>.path`)."""
    manifests = sorted((harness_dir / DOMAIN_SKILLS_DIR).glob("*/manifest.json"))
    return [
        manifest.parent / tool["path"]
        for manifest in manifests
        for tool in json.loads(manifest.read_text(encoding="utf-8")).get("python_tools", {}).values()
    ]


def harness_data_files(harness_dir: Path) -> list[Path]:
    """Every data file under HARNESS_DATA_DIRS; a directory that holds none is an error, since nothing would ship it."""
    files: list[Path] = []
    for directory in HARNESS_DATA_DIRS:
        found = sorted(
            path
            for path in (harness_dir / directory).rglob("*")
            if path.is_file() and path.suffix != ".py" and not _PRUNED_DIRS.intersection(path.parts)
        )
        if not found:
            raise FileNotFoundError(f"{directory} holds no data file under {harness_dir}: update HARNESS_DATA_DIRS")
        files += found
    return files


def package_modules(package_dir: Path, package: str, scripts: Collection[Path] = ()) -> list[str]:
    """Dotted names of every module under `package_dir`, the directory of the top-level package `package`.

    `scripts` are files that are not modules. Any other `.py` file that cannot be imported by name is an error: it
    would be neither bundled nor noticed.
    """
    modules: list[str] = []
    for directory, subdirs, names in os.walk(package_dir):
        subdirs[:] = sorted(name for name in subdirs if name not in _PRUNED_DIRS)
        for name in sorted(names):
            path = Path(directory) / name
            if path.suffix != ".py" or path in scripts:
                continue
            parts = [package, *path.relative_to(package_dir).with_suffix("").parts]
            if parts[-1] == "__init__":
                parts.pop()
            if not all(part.isidentifier() and not keyword.iskeyword(part) for part in parts):
                raise ValueError(f"{path} cannot be imported by name and no manifest declares it as a tool script")
            modules.append(".".join(parts))
    return modules


def first_party_modules(app_dir: Path, harness_dir: Path) -> dict[str, list[str]]:
    """The modules the bundle must contain, per top-level package."""
    scripts = frozenset(domain_tool_scripts(harness_dir))
    return {
        SERVER_PACKAGE: package_modules(app_dir, SERVER_PACKAGE),
        HARNESS_PACKAGE: package_modules(harness_dir, HARNESS_PACKAGE, scripts),
    }


def write_inventory_hooks(hooks_dir: Path, app_dir: Path, harness_dir: Path) -> None:
    """Write `hook-<package>.py` for each top-level package: PyInstaller runs it when the package is in the build."""
    hooks_dir.mkdir(parents=True, exist_ok=True)
    header = "# Generated by sidecar/bundle_inventory.py: every module of the package, however it is loaded.\n"
    for package, modules in first_party_modules(app_dir, harness_dir).items():
        listing = "".join(f"    {name!r},\n" for name in modules)
        (hooks_dir / f"hook-{package}.py").write_text(f"{header}hiddenimports = [\n{listing}]\n", encoding="utf-8")


def script_data_options(harness_dir: Path, data_sep: str) -> list[str]:
    """`--add-data` options that place each domain tool script at its own relative path inside the bundle."""
    options: list[str] = []
    for script in domain_tool_scripts(harness_dir):
        destination = PurePosixPath(HARNESS_PACKAGE, *script.parent.relative_to(harness_dir).parts)
        options += ["--add-data", f"{script}{data_sep}{destination}"]
    return options


def exclude_options() -> list[str]:
    """`--exclude-module` options for CHANNEL_SDKS_NOT_SHIPPED."""
    return [option for package in CHANNEL_SDKS_NOT_SHIPPED for option in ("--exclude-module", package)]
