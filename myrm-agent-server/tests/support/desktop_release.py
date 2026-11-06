"""Locations and workflow accessors shared by the desktop release contract tests.

[INPUT]
- myrm-agent-desktop/sidecar/build.py: the sidecar build script, imported as a module
- myrm-agent-desktop/sidecar/bundle_inventory.py / bundle_verify.py: the modules `build.py` imports from its own directory
- myrm-agent-desktop/scripts/fetch_node_runtime.py: the Node.js runtime fetch script, imported as a module
- scripts/ci/desktop-release/smoke_launch_shell.py: the packaged-shell launch smoke, imported as a module
- scripts/ci/desktop-release/smoke_channels.py: the channel creation check the smoke imports from its own directory
- .github/workflows/desktop-release*.yml: the release workflow and the repair workflow, parsed into job and step mappings
- .github/actions/*/action.yml: the local composite actions the release jobs call

[OUTPUT]
- REPO_ROOT / DESKTOP / FRONTEND / CI_SCRIPTS / WORKFLOWS / ACTIONS / TAURI_CONF: locations inside the OSS repo
- sidecar_build_module() / fetch_node_runtime_module() / smoke_launch_shell_module(): those scripts, each imported once
- sidecar_module(name): a module next to `build.py`, the very object `build.py` imported
- smoke_channels_module(): the module next to the launch smoke, the very object the smoke imported
- workflow_jobs(): the jobs of one workflow file
- release_jobs() / release_steps(): the release workflow's jobs, and the steps of one job as written
- expanded_release_steps(): the steps of one job with every local composite action replaced by its own steps
- bundle_config(platform): the `bundle` section Tauri compiles for a platform (base config + platform patch)

[POS]
桌面发版契约测试共享的路径与工作流读取；sidecar 布局与发版输入两个测试读同一份定义，不各抄一份。
"""

from __future__ import annotations

import importlib.util
import json
import sys
from functools import cache
from pathlib import Path
from types import ModuleType
from typing import Literal, cast

import yaml

YamlMapping = dict[str, object]

REPO_ROOT = Path(__file__).resolve().parents[3]
DESKTOP = REPO_ROOT / "myrm-agent-desktop"
SIDECAR = DESKTOP / "sidecar"
FRONTEND = REPO_ROOT / "myrm-agent-frontend"
CI_SCRIPTS = REPO_ROOT / "scripts/ci/desktop-release"
WORKFLOWS = REPO_ROOT / ".github/workflows"
ACTIONS = REPO_ROOT / ".github/actions"
TAURI_CONF = DESKTOP / "src-tauri/tauri.conf.json"

Platform = Literal["macos", "windows", "linux"]


def _import_script(name: str, path: Path) -> ModuleType:
    """Import a script that is not on the package path; `dataclass` resolves annotations through `sys.modules`."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _put_on_path(directory: Path) -> None:
    """`python script.py` finds the modules next to it because its directory leads `sys.path`; an import has to say so."""
    if str(directory) not in sys.path:
        sys.path.append(str(directory))


@cache
def sidecar_build_module() -> ModuleType:
    _put_on_path(SIDECAR)
    return _import_script("desktop_sidecar_build", SIDECAR / "build.py")


@cache
def sidecar_module(name: str) -> ModuleType:
    """A module that sits next to `build.py` (`bundle_inventory`, `bundle_verify`), the very one `build.py` imported."""
    _put_on_path(SIDECAR)
    return importlib.import_module(name)


@cache
def fetch_node_runtime_module() -> ModuleType:
    return _import_script("desktop_fetch_node_runtime", DESKTOP / "scripts/fetch_node_runtime.py")


@cache
def smoke_launch_shell_module() -> ModuleType:
    _put_on_path(CI_SCRIPTS)
    return _import_script("desktop_smoke_launch_shell", CI_SCRIPTS / "smoke_launch_shell.py")


@cache
def smoke_channels_module() -> ModuleType:
    """The module next to the launch smoke, the very one the smoke imported."""
    _put_on_path(CI_SCRIPTS)
    return importlib.import_module("smoke_channels")


def workflow_jobs(name: str) -> dict[str, YamlMapping]:
    """The jobs of `.github/workflows/<name>`, keyed by job id."""
    workflow = cast("YamlMapping", yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8")))
    return cast("dict[str, YamlMapping]", workflow["jobs"])


def release_jobs() -> dict[str, YamlMapping]:
    return workflow_jobs("desktop-release.yml")


def release_steps(job_id: str) -> list[YamlMapping]:
    return cast("list[YamlMapping]", release_jobs()[job_id]["steps"])


def expanded_release_steps(job_id: str) -> list[YamlMapping]:
    """The steps a runner executes for `job_id`: each call of a local composite action is replaced by its steps."""
    expanded: list[YamlMapping] = []
    for step in release_steps(job_id):
        uses = str(step.get("uses", ""))
        if not uses.startswith("./.github/actions/"):
            expanded.append(step)
            continue
        action = cast("YamlMapping", yaml.safe_load((REPO_ROOT / uses / "action.yml").read_text(encoding="utf-8")))
        expanded.extend(cast("list[YamlMapping]", cast("YamlMapping", action["runs"])["steps"]))
    return expanded


def _merge_patch(target: object, patch: object) -> object:
    """RFC 7396 JSON Merge Patch, the way Tauri overlays `tauri.<platform>.conf.json` on `tauri.conf.json`."""
    if not isinstance(patch, dict):
        return patch
    merged = dict(target) if isinstance(target, dict) else {}
    for key, value in patch.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = _merge_patch(merged.get(key), value)
    return merged


def bundle_config(platform: Platform) -> dict[str, object]:
    """The `bundle` section of the config Tauri compiles for `platform`."""
    config: object = json.loads(TAURI_CONF.read_text(encoding="utf-8"))
    platform_conf = TAURI_CONF.with_name(f"tauri.{platform}.conf.json")
    if platform_conf.exists():
        config = _merge_patch(config, json.loads(platform_conf.read_text(encoding="utf-8")))
    return cast("dict[str, object]", cast("dict[str, object]", config)["bundle"])
