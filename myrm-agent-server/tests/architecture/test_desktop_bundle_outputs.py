"""The release scripts pick up a bundle's outputs, never the files inside the bundle.

Tauri writes its outputs (`.dmg`, `.app.tar.gz`, installers, AppImage) directly into
`release/bundle/<kind>/`, next to the `.app` / `.AppDir` they were built from. A one-folder sidecar
puts thousands of files in that bundle, archives included (python-dateutil ships
`dateutil-zoneinfo.tar.gz`); a suffix match over the whole directory signed such an archive and would
have published it as a release asset.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from tests.support.desktop_release import CI_SCRIPTS

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="bash release scripts")

_BUNDLE_PATHS = CI_SCRIPTS / "bundle-paths.sh"
_COLLECT_ASSETS = CI_SCRIPTS / "collect-bundle-assets.sh"
_SIGN_UPDATER_BUNDLES = CI_SCRIPTS / "sign-updater-bundles.sh"

_MAC = "target/aarch64-apple-darwin/release/bundle/macos"
_NESTED_ARCHIVE = (
    f"{_MAC}/MyrmAgent.app/Contents/Resources/binaries/myrmagent-backend/_internal/dateutil/zoneinfo/dateutil-zoneinfo.tar.gz"
)
_APPDIR_ARCHIVE = "target/release/bundle/appimage/MyrmAgent.AppDir/usr/lib/MyrmAgent/data.tar.gz"

# Real outputs, then the same kinds of file found inside a bundle.
_OUTPUTS = (
    f"{_MAC}/MyrmAgent.app.tar.gz",
    f"{_MAC}/MyrmAgent.app.tar.gz.sig",
    "target/aarch64-apple-darwin/release/bundle/dmg/MyrmAgent_1.0.0_aarch64.dmg",
    "target/release/bundle/nsis/MyrmAgent_x64-setup.exe",
    "target/release/bundle/msi/MyrmAgent_1.0.0_x64_en-US.msi",
    "target/release/bundle/appimage/MyrmAgent_1.0.0_amd64.AppImage",
    "target/release/bundle/deb/MyrmAgent_1.0.0_amd64.deb",
)
_BUNDLE_CONTENTS = (
    _NESTED_ARCHIVE,
    f"{_NESTED_ARCHIVE}.sig",
    f"{_MAC}/MyrmAgent.app/Contents/MacOS/myrm-agent",
    _APPDIR_ARCHIVE,
    "target/release/bundle/nsis/x64/installer-helper.exe",
)
_UPDATER_OUTPUTS = (
    f"{_MAC}/MyrmAgent.app.tar.gz",
    "target/release/bundle/nsis/MyrmAgent_x64-setup.exe",
)


def _bash(snippet: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", f'source "{_BUNDLE_PATHS}"; {snippet}', "bash", *args],
        check=False,
        capture_output=True,
        text=True,
    )


def _touch(root: Path, relative: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    return path


@pytest.mark.parametrize("path", _OUTPUTS)
def test_every_tauri_output_is_a_release_bundle_path(path: str) -> None:
    assert _bash('is_release_bundle_path "$1"', path).returncode == 0


@pytest.mark.parametrize("path", _BUNDLE_CONTENTS)
def test_files_inside_a_bundle_are_not_release_bundle_paths(path: str) -> None:
    assert _bash('is_release_bundle_path "$1"', path).returncode != 0


def test_only_updater_packages_are_updater_bundles() -> None:
    for path in _OUTPUTS:
        expected = path in _UPDATER_OUTPUTS
        assert (_bash('is_updater_bundle_path "$1"', path).returncode == 0) is expected, path
    for path in _BUNDLE_CONTENTS:
        assert _bash('is_updater_bundle_path "$1"', path).returncode != 0, path


def test_windows_separators_are_classified_like_posix_ones() -> None:
    windows = r"target\release\bundle\nsis\MyrmAgent_x64-setup.exe"
    nested = r"target\release\bundle\nsis\x64\installer-helper.exe"

    assert _bash('is_updater_bundle_path "$1"', windows).returncode == 0
    assert _bash('is_release_bundle_path "$1"', nested).returncode != 0


def test_collect_bundle_assets_lists_outputs_and_skips_bundle_contents(tmp_path: Path) -> None:
    for relative in (*_OUTPUTS, *_BUNDLE_CONTENTS):
        _touch(tmp_path, relative)

    completed = subprocess.run(
        ["bash", str(_COLLECT_ASSETS), str(tmp_path / "target")],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    listed = {Path(line).relative_to(tmp_path).as_posix() for line in completed.stdout.splitlines()}
    # collect-bundle-assets publishes archives, packages and signatures; the AppImage package itself
    # is published through its own `.AppImage` entry, hence all seven outputs.
    assert listed == set(_OUTPUTS)


def test_updater_signing_signs_only_updater_packages(tmp_path: Path) -> None:
    desktop = tmp_path / "desktop"
    target = desktop / "src-tauri/target"
    for relative in (*_OUTPUTS, *_BUNDLE_CONTENTS):
        # `.sig` files already present are left alone; the rest must be signed or skipped by the script.
        if not relative.endswith(".sig"):
            _touch(target.parent, relative)
    signed_log = tmp_path / "signed.log"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_bun = fake_bin / "bun"
    fake_bun.write_text(
        '#!/usr/bin/env bash\nartifact="${@: -1}"\necho "$artifact" >> "$SIGNED_LOG"\ntouch "${artifact}.sig"\n',
        encoding="utf-8",
    )
    fake_bun.chmod(fake_bun.stat().st_mode | stat.S_IXUSR)

    completed = subprocess.run(
        ["bash", str(_SIGN_UPDATER_BUNDLES), str(target), str(desktop)],
        env={
            **os.environ,
            "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
            "SIGNED_LOG": str(signed_log),
            "TAURI_SIGNING_PRIVATE_KEY": "test-key",
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    signed = sorted(line.removeprefix("src-tauri/") for line in signed_log.read_text(encoding="utf-8").splitlines())
    assert signed == sorted(_UPDATER_OUTPUTS)
    assert not (target.parent / f"{_NESTED_ARCHIVE}.sig").exists()
