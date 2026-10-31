"""What the packaged-shell launch smoke (`scripts/ci/desktop-release/smoke_launch_shell.py`) launches with, and how
the release workflow wires it in.

The smoke starts a built bundle the way a user does: the launcher's working directory, no Node.js on PATH, a fresh
profile. These tests pin that launch environment and the workflow steps that run the smoke against each built bundle.
The smoke's behaviour against bundles that work or misbehave is pinned in `test_desktop_launch_smoke_run.py`.
"""

from __future__ import annotations

import plistlib
import re
import textwrap
import tomllib
from pathlib import Path
from types import ModuleType

import pytest

from tests.support.desktop_release import DESKTOP, expanded_release_steps, smoke_launch_shell_module

_BUILD_JOBS = ("build-macos-arm", "build-windows", "build-linux")


@pytest.fixture(scope="module")
def smoke() -> ModuleType:
    return smoke_launch_shell_module()


def test_the_smoke_uses_the_binary_and_ports_the_shell_defines(smoke: ModuleType) -> None:
    cargo = tomllib.loads((DESKTOP / "src-tauri/Cargo.toml").read_text(encoding="utf-8"))
    config = (DESKTOP / "src-tauri/src/config.rs").read_text(encoding="utf-8")
    frontend_port = re.search(r"pub const DESKTOP_FRONTEND_PORT: u16 = (\d+);", config)
    backend_default = config[config.index("pub fn from_system_config") :].split("\n    }\n", 1)[0]

    assert smoke.MAIN_BINARY == cargo["package"]["name"]
    assert frontend_port is not None
    assert smoke.FRONTEND_PORT == int(frontend_port.group(1))
    assert re.search(rf"\b{smoke.BACKEND_PORT}\b", backend_default), "the shell's default backend port changed"


class TestLaunchEnvironment:
    def test_the_unix_path_holds_no_user_installed_runtime(self, smoke: ModuleType) -> None:
        assert smoke.launch_path("darwin", {"PATH": "/opt/homebrew/bin"}) == "/usr/bin:/bin:/usr/sbin:/sbin"
        assert smoke.launch_path("linux", {}) == "/usr/bin:/bin:/usr/sbin:/sbin"

    def test_the_windows_path_holds_only_system_directories(self, smoke: ModuleType) -> None:
        path = smoke.launch_path("win32", {"SYSTEMROOT": r"D:\Win"})

        assert path.split(";") == [r"D:\Win\System32", r"D:\Win", r"D:\Win\System32\Wbem"]

    def test_unix_starts_from_nothing_but_the_profile_and_the_display(self, smoke: ModuleType, tmp_path: Path) -> None:
        inherited = {"PATH": "/opt/homebrew/bin", "NODE_OPTIONS": "--inspect", "DISPLAY": ":99", "USER": "ci", "SECRET": "x"}

        env = smoke.launch_env("linux", tmp_path, inherited)

        assert env == {
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": str(tmp_path),
            "USER": "ci",
            "LANG": "en_US.UTF-8",
            "TMPDIR": str(tmp_path / "tmp"),
            "DISPLAY": ":99",
        }

    def test_windows_keeps_the_user_environment_and_narrows_only_the_path(self, smoke: ModuleType, tmp_path: Path) -> None:
        inherited = {"PATH": r"C:\Program Files\nodejs", "SYSTEMROOT": r"C:\Windows", "APPDATA": r"C:\Users\u\AppData"}

        env = smoke.launch_env("win32", tmp_path, inherited)

        assert env["APPDATA"] == inherited["APPDATA"]
        assert "nodejs" not in env["PATH"]


class TestLaunchCwd:
    def test_finder_starts_an_application_in_the_unwritable_filesystem_root(self, smoke: ModuleType, tmp_path: Path) -> None:
        assert smoke.launch_cwd("darwin", tmp_path / "MyrmAgent.app", tmp_path / "profile") == Path("/")

    def test_a_start_menu_shortcut_starts_in_the_install_directory(self, smoke: ModuleType, tmp_path: Path) -> None:
        assert smoke.launch_cwd("win32", tmp_path / "install", tmp_path / "profile") == tmp_path / "install"

    def test_linux_stands_in_the_profile_for_the_launcher_directory(self, smoke: ModuleType, tmp_path: Path) -> None:
        assert smoke.launch_cwd("linux", tmp_path / "squashfs-root", tmp_path / "profile") == tmp_path / "profile"


class TestShellCommand:
    def test_macos_runs_the_executable_the_bundle_declares(self, smoke: ModuleType, tmp_path: Path) -> None:
        app = tmp_path / "MyrmAgent.app"
        (app / "Contents").mkdir(parents=True)
        (app / "Contents/Info.plist").write_bytes(plistlib.dumps({"CFBundleExecutable": "myrm-agent"}))

        assert smoke.shell_command("darwin", app) == [str(app / "Contents/MacOS/myrm-agent")]

    def test_windows_runs_the_installed_exe(self, smoke: ModuleType, tmp_path: Path) -> None:
        assert smoke.shell_command("win32", tmp_path) == [str(tmp_path / "myrm-agent.exe")]

    def test_linux_runs_the_apprun_of_the_extracted_image(self, smoke: ModuleType, tmp_path: Path) -> None:
        assert smoke.shell_command("linux", tmp_path) == [str(tmp_path / "AppRun")]


class TestProcessTable:
    table = textwrap.dedent(
        """\
          1     0 /sbin/launchd
        100     1 /Applications/MyrmAgent.app/Contents/MacOS/myrm-agent
        101   100 /Applications/MyrmAgent.app/Contents/Resources/binaries/myrmagent-backend/myrmagent-backend --port 8080
        102   100 next-server (v16.3.0)
        103   102 /bin/sh -c worker
        200     1 /usr/bin/unrelated
        garbage line
        """
    )

    def test_rows_become_processes_and_noise_is_skipped(self, smoke: ModuleType) -> None:
        processes = smoke.parse_process_table(self.table)

        assert [process.pid for process in processes] == [1, 100, 101, 102, 103, 200]
        assert processes[2].command.endswith("--port 8080")

    def test_descendants_cover_every_depth_and_nothing_else(self, smoke: ModuleType) -> None:
        found = smoke.descendants(smoke.parse_process_table(self.table), 100)

        assert sorted(process.pid for process in found) == [101, 102, 103]


def _step_runs(job_id: str) -> list[str]:
    return [str(step.get("run", "")) for step in expanded_release_steps(job_id)]


@pytest.mark.parametrize("job_id", _BUILD_JOBS)
def test_every_platform_job_launches_the_built_bundle_after_bundling(job_id: str) -> None:
    steps = expanded_release_steps(job_id)
    bundled = next(i for i, step in enumerate(steps) if str(step.get("uses", "")).startswith("tauri-apps/tauri-action"))
    launches = [i for i, run in enumerate(_step_runs(job_id)) if "smoke_launch_shell.py --bundle " in run]

    assert launches, f"{job_id} never launches what it built"
    assert min(launches) > bundled


@pytest.mark.parametrize("job_id", ["build-macos-arm", "build-linux"])
def test_extracted_bundles_are_launched_read_only(job_id: str) -> None:
    # The shell and its servers must live with an install directory they cannot write to (a mounted AppImage,
    # a translocated .app).
    extracted = [run for run in _step_runs(job_id) if "smoke_launch_shell.py" in run and "EXTRACTED" in run]

    assert extracted, f"{job_id}: no launch of an extracted bundle"
    for run in extracted:
        assert run.index("chmod -R a-w") < run.index("smoke_launch_shell.py"), job_id


def test_the_linux_launch_has_a_display() -> None:
    launch = next(run for run in _step_runs("build-linux") if "smoke_launch_shell.py" in run)
    installed = next(run for run in _step_runs("build-linux") if "apt-get install" in run)

    assert "xvfb-run -a python " in launch
    assert "xvfb" in installed.split()


def test_the_windows_launch_runs_what_the_installer_installed() -> None:
    launch = next(run for run in _step_runs("build-windows") if "smoke_launch_shell.py" in run)

    assert launch.index("-ArgumentList '/S'") < launch.index("smoke_launch_shell.py")
