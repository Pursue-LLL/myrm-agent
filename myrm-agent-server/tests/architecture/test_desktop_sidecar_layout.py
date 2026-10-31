"""Static + behavioural contract for the desktop sidecar layout.

The sidecar ships as a PyInstaller one-folder tree, mapped by Tauri to the resource
``binaries/myrmagent-backend/``. On Linux the same tree is placed under ``usr/share`` of the AppImage
instead, because linuxdeploy resolves and rewrites every ELF file below ``usr/lib``. The build script,
the Tauri resource map, the Rust resolver and the release workflow must agree on that layout; this test
pins them together so a one-sided change fails here instead of in a release build.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import cast

import pytest

from tests.support.desktop_release import (
    ACTIONS,
    CI_SCRIPTS,
    DESKTOP,
    REPO_ROOT,
    TAURI_CONF,
    WORKFLOWS,
    Platform,
    YamlMapping,
    bundle_config,
    release_jobs,
    release_steps,
    sidecar_build_module,
)

_EXPORT_APPLE_ENV_SH = CI_SCRIPTS / "export-apple-signing-env.sh"

# Leftovers of the removed layouts: triple-named single-file sidecar, agent-runner sidecar, the
# sidecar version manager, the Linux dummy-ELF swap and the separate tokenizer-cache resource.
_REMOVED_LAYOUT_MARKERS = (
    "agent-runner",
    "AGENT_RUNNER",
    "myrmagent-backend-",
    "--bundle-app",
    "linux-appimage-sidecar-workaround",
    "prepare-check-stub-sidecars",
    "SidecarVersionManager",
    "sidecar_version_manager",
    "tiktoken_cache",
    "TIKTOKEN_CACHE",
)


@pytest.fixture(scope="module")
def build_module() -> ModuleType:
    return sidecar_build_module()


def test_pyinstaller_builds_a_one_folder_bundle_named_after_the_sidecar(build_module: ModuleType) -> None:
    work_dir = Path("work")
    cmd = build_module.pyinstaller_command(Path("python"), work_dir)

    assert "--onedir" in cmd
    assert "--onefile" not in cmd
    assert cmd[cmd.index("--name") + 1] == build_module.SIDECAR_NAME
    assert cmd[cmd.index("--distpath") + 1] == str(build_module.OUTPUT_DIR)
    # Scratch files must never land inside the folder that gets shipped.
    assert cmd[cmd.index("--workpath") + 1] == str(work_dir / "build")
    assert cmd[cmd.index("--specpath") + 1] == str(work_dir)


@pytest.mark.parametrize("platform", ["macos", "windows"])
def test_tauri_resource_map_ships_the_folder_the_build_writes(build_module: ModuleType, platform: Platform) -> None:
    resource = f"binaries/{build_module.SIDECAR_NAME}"
    resources = cast("dict[str, str]", bundle_config(platform)["resources"])

    assert resources.get(resource) == resource
    assert (DESKTOP / "src-tauri" / resource).resolve() == build_module.SIDECAR_DIR.resolve()


def test_linux_appimage_keeps_the_folder_where_linuxdeploy_does_not_look(build_module: ModuleType) -> None:
    resource = f"binaries/{build_module.SIDECAR_NAME}"
    bundle = bundle_config("linux")
    product = json.loads(TAURI_CONF.read_text(encoding="utf-8"))["productName"]
    appimage_files = cast("dict[str, str]", cast("dict[str, dict[str, object]]", bundle["linux"])["appimage"]["files"])

    # In the resource map the tree would land in usr/lib/<product>, where linuxdeploy fails on its libraries.
    assert resource not in cast("dict[str, str]", bundle["resources"])
    assert appimage_files == {f"usr/share/{product}/{resource}": resource}
    assert (DESKTOP / "src-tauri" / resource).resolve() == build_module.SIDECAR_DIR.resolve()
    # A deb/rpm built from this config would ship without a backend.
    assert bundle["targets"] == ["appimage"]


def test_rust_resolver_constants_match_the_build_layout(build_module: ModuleType) -> None:
    source = (DESKTOP / "src-tauri/src/runtime/sidecar_path.rs").read_text(encoding="utf-8")
    name = build_module.SIDECAR_NAME

    resource_dir = re.search(r'const RESOURCE_DIR: &str = "([^"]+)";', source)
    assert resource_dir is not None
    assert resource_dir.group(1) == f"binaries/{name}"
    assert f'"{name}.exe"' in source
    assert f'"{name}"' in source

    share_dir = re.search(r'const LINUX_SHARE_DIR: &str = "([^"]+)";', source)
    assert share_dir is not None
    appimage_files = cast("dict[str, dict[str, dict[str, str]]]", bundle_config("linux")["linux"])["appimage"]["files"]
    assert all(dest.startswith(f"usr/{share_dir.group(1)}/") for dest in appimage_files)


def test_the_release_shell_gives_the_sidecar_its_own_working_directory() -> None:
    # The backend creates its `.myrm/` state directories in its working directory while it is imported. A child that
    # inherits the shell's directory gets `/` when Finder launches the app and the read-only `usr` directory of the
    # image when AppRun does, and exits at startup.
    source = (DESKTOP / "src-tauri/src/runtime/python_backend.rs").read_text(encoding="utf-8")
    release_branch = source.split("bundled_executable(&app)?", 1)[1].split("\n    };", 1)[0]

    assert "sidecar_workdir(&app)?" in release_branch
    assert ".current_dir(" in release_branch


def test_no_removed_sidecar_layout_remains_in_build_and_ci_files() -> None:
    files = [
        DESKTOP / "sidecar/build.py",
        *sorted(CI_SCRIPTS.glob("*.sh")),
        *sorted(CI_SCRIPTS.glob("*.ps1")),
        *sorted((DESKTOP / "scripts/ci").glob("*.sh")),
        *sorted(WORKFLOWS.glob("desktop-*.yml")),
        *sorted(ACTIONS.rglob("action.yml")),
        *sorted((DESKTOP / "src-tauri/src").rglob("*.rs")),
    ]
    offenders = [
        f"{path.relative_to(REPO_ROOT)}: {marker}"
        for path in files
        for marker in _REMOVED_LAYOUT_MARKERS
        if marker in path.read_text(encoding="utf-8")
    ]

    assert not offenders, "removed sidecar layout still referenced:\n" + "\n".join(offenders)


def test_apple_signing_env_is_exported_only_when_configured() -> None:
    # A defined-but-empty APPLE_* variable makes the bundler attempt a keychain import and fail.
    steps = release_steps("build-macos-arm")
    tauri_index = next(i for i, step in enumerate(steps) if str(step.get("uses", "")).startswith("tauri-apps/tauri-action"))
    export_index = next(i for i, step in enumerate(steps) if "export-apple-signing-env.sh" in str(step.get("run", "")))

    assert export_index < tauri_index, "Apple env must be exported before the bundle step"
    tauri_env = cast("YamlMapping", steps[tauri_index].get("env", {}))
    declared = [key for key in tauri_env if key.startswith("APPLE_")]
    assert not declared, f"tauri-action must not declare APPLE_* env: {declared}"


def _parse_github_env(text: str) -> dict[str, str]:
    """Parse a GITHUB_ENV file: `NAME=value` lines and `NAME<<DELIMITER ... DELIMITER` blocks."""
    parsed: dict[str, str] = {}
    lines = iter(text.splitlines())
    for line in lines:
        if "<<" in line:
            name, delimiter = line.split("<<", 1)
            body: list[str] = []
            for body_line in lines:
                if body_line == delimiter:
                    break
                body.append(body_line)
            parsed[name] = "\n".join(body)
        elif "=" in line:
            name, value = line.split("=", 1)
            parsed[name] = value
    return parsed


def _run_export_apple_env(tmp_path: Path, apple_env: dict[str, str]) -> tuple[subprocess.CompletedProcess[str], str]:
    env_file = tmp_path / "github_env"
    env_file.touch()
    inherited = {key: value for key, value in os.environ.items() if not key.startswith("APPLE_")}
    completed = subprocess.run(
        ["bash", str(_EXPORT_APPLE_ENV_SH)],
        env={**inherited, **apple_env, "GITHUB_ENV": str(env_file)},
        check=False,
        capture_output=True,
        text=True,
    )
    return completed, env_file.read_text(encoding="utf-8")


@pytest.mark.skipif(sys.platform == "win32", reason="bash script")
class TestAppleEnvExport:
    def test_exports_only_configured_values_and_keeps_multi_line_ones_whole(self, tmp_path: Path) -> None:
        certificate = "first-line\nsecond-line"

        completed, env_text = _run_export_apple_env(
            tmp_path, {"APPLE_ID": "dev@example.com", "APPLE_CERTIFICATE": certificate, "APPLE_TEAM_ID": ""}
        )

        assert completed.returncode == 0, completed.stderr
        assert _parse_github_env(env_text) == {"APPLE_ID": "dev@example.com", "APPLE_CERTIFICATE": certificate}

    def test_defines_nothing_when_no_secret_is_configured(self, tmp_path: Path) -> None:
        completed, env_text = _run_export_apple_env(tmp_path, {"APPLE_ID": "", "APPLE_PASSWORD": ""})

        assert completed.returncode == 0, completed.stderr
        assert env_text == ""
        assert "unsigned" in completed.stdout


def test_only_tag_runs_publish_to_a_release() -> None:
    assert "refs/tags/v" in str(release_jobs()["publish-release"]["if"])

    for job_id in ("build-macos-arm", "build-windows", "build-linux"):
        for step in release_steps(job_id):
            if "gh release upload" in str(step.get("run", "")):
                assert step.get("if") == "github.ref_type == 'tag'", f"{job_id}: upload must be tag-only"
