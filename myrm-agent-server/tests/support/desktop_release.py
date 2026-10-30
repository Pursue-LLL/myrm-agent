"""Locations and workflow accessors shared by the desktop release contract tests.

[INPUT]
- myrm-agent-desktop/sidecar/build.py: the sidecar build script, imported as a module
- .github/workflows/desktop-release.yml: the release workflow, parsed into job and step mappings
- .github/actions/*/action.yml: the local composite actions the release jobs call

[OUTPUT]
- REPO_ROOT / DESKTOP / FRONTEND / CI_SCRIPTS / WORKFLOWS / ACTIONS / TAURI_CONF: locations inside the OSS repo
- sidecar_build_module(): `sidecar/build.py`, imported once
- release_jobs() / release_steps(): the release workflow's jobs, and the steps of one job as written
- expanded_release_steps(): the steps of one job with every local composite action replaced by its own steps
- bundle_config(platform): the `bundle` section Tauri compiles for a platform (base config + platform patch)

[POS]
桌面发版契约测试共享的路径与工作流读取；sidecar 布局与发版输入两个测试读同一份定义，不各抄一份。
"""

from __future__ import annotations

import importlib.util
import json
from functools import cache
from pathlib import Path
from types import ModuleType
from typing import Literal, cast

import yaml

YamlMapping = dict[str, object]

REPO_ROOT = Path(__file__).resolve().parents[3]
DESKTOP = REPO_ROOT / "myrm-agent-desktop"
FRONTEND = REPO_ROOT / "myrm-agent-frontend"
CI_SCRIPTS = REPO_ROOT / "scripts/ci/desktop-release"
WORKFLOWS = REPO_ROOT / ".github/workflows"
ACTIONS = REPO_ROOT / ".github/actions"
TAURI_CONF = DESKTOP / "src-tauri/tauri.conf.json"

Platform = Literal["macos", "windows", "linux"]


@cache
def sidecar_build_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("desktop_sidecar_build", DESKTOP / "sidecar/build.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def release_jobs() -> dict[str, YamlMapping]:
    workflow = cast("YamlMapping", yaml.safe_load((WORKFLOWS / "desktop-release.yml").read_text(encoding="utf-8")))
    return cast("dict[str, YamlMapping]", workflow["jobs"])


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
