"""Static + behavioural contract for the desktop sidecar layout.

The sidecar ships as a PyInstaller one-folder tree, mapped by Tauri to the resource
``binaries/myrmagent-backend/``. On Linux the same tree is placed under ``usr/share`` of the AppImage
instead, because linuxdeploy resolves and rewrites every ELF file below ``usr/lib``. The build script,
the Tauri resource map, the Rust resolver, the CI smoke scripts and the release workflow must agree on
that layout; this test pins them together so a one-sided change fails here instead of in a release build.
"""

from __future__ import annotations

import json
import os
import re
import socket
import stat
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

_SMOKE_SH = CI_SCRIPTS / "smoke-launch-runtime.sh"
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
    for job_id in ("build-macos-arm", "build-macos-x64"):
        steps = release_steps(job_id)
        tauri_index = next(i for i, step in enumerate(steps) if str(step.get("uses", "")).startswith("tauri-apps/tauri-action"))
        export_index = next(i for i, step in enumerate(steps) if "export-apple-signing-env.sh" in str(step.get("run", "")))

        assert export_index < tauri_index, f"{job_id}: Apple env must be exported before the bundle step"
        tauri_env = cast("YamlMapping", steps[tauri_index].get("env", {}))
        declared = [key for key in tauri_env if key.startswith("APPLE_")]
        assert not declared, f"{job_id}: tauri-action must not declare APPLE_* env: {declared}"


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

    for job_id in ("build-macos-arm", "build-macos-x64", "build-windows", "build-linux"):
        for step in release_steps(job_id):
            if "gh release upload" in str(step.get("run", "")):
                assert step.get("if") == "github.ref_type == 'tag'", f"{job_id}: upload must be tag-only"


def test_every_platform_job_smokes_the_built_bundle() -> None:
    def runs(job_id: str) -> str:
        return "\n".join(str(step.get("run", "")) for step in release_steps(job_id))

    assert "smoke-launch-runtime.sh --bundle " in runs("build-macos-arm")
    assert "smoke-launch-runtime.ps1 -BundleDir" in runs("build-windows")
    assert "smoke-launch-runtime.sh --bundle " in runs("build-linux")


def test_extracted_bundles_are_smoked_read_only() -> None:
    # The backend must live with an install directory it cannot write to (a mounted AppImage, a translocated .app).
    for job_id in ("build-macos-arm", "build-linux"):
        extracted_runs = [
            str(step["run"])
            for step in release_steps(job_id)
            if 'smoke-launch-runtime.sh --bundle "$EXTRACTED' in str(step.get("run", ""))
        ]
        assert extracted_runs, f"{job_id}: no smoke of an extracted bundle"
        for run in extracted_runs:
            assert "chmod -R a-w" in run, f"{job_id}: the extracted bundle must be read-only during the smoke"
            assert run.index("chmod -R a-w") < run.index("smoke-launch-runtime.sh"), job_id


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


_HEALTH_SERVER = f"""#!{sys.executable}
import os
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


HTTPServer(("127.0.0.1", int(os.environ["PORT"])), Handler).serve_forever()
"""


# Proportions of a real bundle: the backend executable is far larger than the Next server.js, so the
# size threshold that rejects a placeholder backend must not be applied to server.js.
_BACKEND_BYTES = 32_768
_SERVER_JS_BYTES = 8_192
_MIN_BINARY_BYTES = 16_384


def _padded(body: str, size: int) -> str:
    return body + "#" * max(0, size - len(body))


def _write_executable(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _make_bundle(
    root: Path,
    *,
    internal_dir: bool = True,
    executable: bool = True,
    backend_bytes: int = _BACKEND_BYTES,
    appimage_layout: bool = False,
) -> Path:
    if appimage_layout:
        # The sidecar tree sits in usr/share (linuxdeploy rewrites usr/lib); the frontend stays a resource in usr/lib.
        bundle = root / "squashfs-root"
        sidecar_root = bundle / "usr/share/MyrmAgent"
        frontend_root = bundle / "usr/lib/MyrmAgent"
    else:
        bundle = root / "MyrmAgent.app"
        sidecar_root = frontend_root = bundle / "Contents/Resources"
    backend = sidecar_root / "binaries/myrmagent-backend/myrmagent-backend"
    _write_executable(backend, _padded(_HEALTH_SERVER, backend_bytes))
    if not executable:
        backend.chmod(backend.stat().st_mode & ~(stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
    if internal_dir:
        (backend.parent / "_internal").mkdir()
    (frontend_root / "frontend/app").mkdir(parents=True)
    (frontend_root / "frontend/app/server.js").write_text(
        _padded("// next standalone stand-in\n", _SERVER_JS_BYTES), encoding="utf-8"
    )
    return bundle


def _run_smoke(bundle: Path, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    # The frontend runs through `node server.js`; a stand-in `node` serves the same health response.
    fake_bin = tmp_path / "fake-bin"
    _write_executable(fake_bin / "node", _HEALTH_SERVER)
    env = {
        **os.environ,
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "API_PORT": str(_free_port()),
        "WEBUI_PORT": str(_free_port()),
        "READY_TIMEOUT_SEC": "30",
        "MIN_BINARY_BYTES": str(_MIN_BINARY_BYTES),
    }
    return subprocess.run(
        ["bash", str(_SMOKE_SH), "--bundle", str(bundle)],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )


@pytest.mark.skipif(sys.platform == "win32", reason="bash smoke script")
class TestSmokeScriptOnAFolderBundle:
    def test_starts_the_bundled_sidecar_and_frontend(self, tmp_path: Path) -> None:
        completed = _run_smoke(_make_bundle(tmp_path), tmp_path)

        assert completed.returncode == 0, completed.stdout + completed.stderr
        assert "Backend /health ready" in completed.stdout
        assert "[launch-smoke] OK" in completed.stdout

    def test_starts_an_appimage_whose_sidecar_and_frontend_are_in_different_resource_dirs(self, tmp_path: Path) -> None:
        completed = _run_smoke(_make_bundle(tmp_path, appimage_layout=True), tmp_path)

        assert completed.returncode == 0, completed.stdout + completed.stderr
        assert "[launch-smoke] OK" in completed.stdout

    def test_reports_a_bundle_without_a_frontend(self, tmp_path: Path) -> None:
        bundle = _make_bundle(tmp_path)
        (bundle / "Contents/Resources/frontend/app/server.js").unlink()

        completed = _run_smoke(bundle, tmp_path)

        assert completed.returncode != 0
        assert "server.js not found" in completed.stderr

    def test_rejects_a_placeholder_sidecar(self, tmp_path: Path) -> None:
        completed = _run_smoke(_make_bundle(tmp_path, backend_bytes=len(_HEALTH_SERVER)), tmp_path)

        assert completed.returncode != 0
        assert "looks like a stub" in completed.stderr

    def test_rejects_a_sidecar_without_its_internal_folder(self, tmp_path: Path) -> None:
        completed = _run_smoke(_make_bundle(tmp_path, internal_dir=False), tmp_path)

        assert completed.returncode != 0
        assert "not a one-folder build" in completed.stderr

    def test_rejects_a_non_executable_sidecar(self, tmp_path: Path) -> None:
        completed = _run_smoke(_make_bundle(tmp_path, executable=False), tmp_path)

        assert completed.returncode != 0
        assert "not executable" in completed.stderr

    def test_rejects_a_bundle_with_two_sidecar_folders(self, tmp_path: Path) -> None:
        bundle = _make_bundle(tmp_path)
        (bundle / "Contents/Resources/nested/binaries/myrmagent-backend").mkdir(parents=True)

        completed = _run_smoke(bundle, tmp_path)

        assert completed.returncode != 0
        assert "expected one binaries/myrmagent-backend folder" in completed.stderr
