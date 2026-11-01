"""finalize-release.sh and verify-release.sh run end to end against a stand-in `gh` and `curl`.

The stand-ins serve a directory of files the way GitHub serves a release, so the scripts' own logic runs for real:
which asset becomes which OTA platform, which sidecars are written, what is uploaded, and what a failure says. The
run's step log needs a sign-in to read, so every failure must also be an `::error` annotation, which does not.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import TypedDict, cast

import pytest

_SCRIPTS = Path(__file__).resolve().parents[3] / "scripts/ci/desktop-release"
_REPO = "owner/repo"
_TAG = "v0.1.40"
_ALL_PLATFORMS = "darwin-aarch64 windows-x86_64 linux-x86_64"
_ANNOTATION = "::error title=desktop release::"

# The assets v0.1.40 holds before its manifest is regenerated: Linux ships a signed bare AppImage, no archive.
_SIGNED = [
    "MyrmAgent.app.tar.gz",
    "MyrmAgent_x64-setup.exe",
    "MyrmAgent_0.1.40_amd64.AppImage",
    "MyrmAgent_0.1.40_x64_en-US.msi",
]
_UNSIGNED = ["MyrmAgent_0.1.40_aarch64.dmg"]


class _Manifest(TypedDict):
    version: str
    platforms: dict[str, dict[str, str]]


_GH = """#!/usr/bin/env bash
# Serves $RELEASE_DIR as the release $RELEASE_TAG; every call is logged to $CALLS_LOG.
echo "gh $*" >>"$CALLS_LOG"
if [[ -n "${GH_FAIL:-}" && "$1 $2" == "$GH_FAIL"* ]]; then echo "stand-in failure of $GH_FAIL" >&2; exit 1; fi
args=("$@")
for ((i = 0; i < ${#args[@]}; i++)); do
  case "${args[i]}" in
    --jq) jq_filter="${args[i + 1]}" ;;
    --dir) download_dir="${args[i + 1]}" ;;
  esac
done
# Like the real CLI: JSON on stdout, or the raw result of --jq.
emit() { if [[ -n "${jq_filter:-}" ]]; then jq -r "$jq_filter"; else cat; fi; }
case "$1 $2" in
  "release view")
    [[ "$3" == "$RELEASE_TAG" ]] || { echo "release not found" >&2; exit 1; }
    ls -1 "$RELEASE_DIR" | jq -R '{name: .}' | jq -s '{assets: .}' | emit ;;
  "release download") cp "$RELEASE_DIR"/* "$download_dir"/ ;;
  "release upload")
    for arg in "${@:3}"; do [[ -f "$arg" ]] && cp "$arg" "$RELEASE_DIR"/; done
    exit 0 ;;
  "api repos/"*) echo '{"published_at": "2026-11-01T00:00:00Z", "body": "notes"}' | emit ;;
  *) echo "unexpected gh call: $*" >&2; exit 99 ;;
esac
"""

_CURL = """#!/usr/bin/env bash
# The public download URL of latest.json serves what the release holds.
[[ -f "$RELEASE_DIR/latest.json" ]] || { echo "curl: (22) The requested URL returned error: 404" >&2; exit 22; }
cat "$RELEASE_DIR/latest.json"
"""

# The scripts need jq and sha256sum. CI always has them, so a missing tool there fails the run instead of skipping it.
pytestmark = pytest.mark.skipif(
    not os.environ.get("CI") and not all(shutil.which(tool) for tool in ("jq", "sha256sum")),
    reason="the release scripts need jq and sha256sum",
)


class Release:
    """A directory standing in for a GitHub release, plus the environment that points the scripts at it."""

    def __init__(self, root: Path) -> None:
        self.assets = root / "release"
        self.calls_log = root / "calls.log"
        self.assets.mkdir()
        stand_ins = root / "bin"
        stand_ins.mkdir()
        for name, body in (("gh", _GH), ("curl", _CURL)):
            (stand_ins / name).write_text(body)
            (stand_ins / name).chmod(0o755)
        self._path = f"{stand_ins}{os.pathsep}{os.environ['PATH']}"
        for name in _SIGNED:
            (self.assets / name).write_text(f"bytes of {name}")
            (self.assets / f"{name}.sig").write_text(f"signature of {name}\n")
        for name in _UNSIGNED:
            (self.assets / name).write_text(f"bytes of {name}")

    def run(self, script: str, tag: str = _TAG, **extra_env: str) -> subprocess.CompletedProcess[str]:
        env = {
            **os.environ,
            "PATH": self._path,
            "RELEASE_DIR": str(self.assets),
            "RELEASE_TAG": _TAG,
            "CALLS_LOG": str(self.calls_log),
            "GITHUB_REPOSITORY": _REPO,
            "GITHUB_ACTIONS": "true",
            "TAG": tag,
            **extra_env,
        }
        return subprocess.run(["bash", str(_SCRIPTS / script)], env=env, capture_output=True, text=True, check=False)

    def finalize(self, tag: str = _TAG) -> subprocess.CompletedProcess[str]:
        return self.run("finalize-release.sh", tag, REQUIRED_OTA_PLATFORM_KEYS=_ALL_PLATFORMS)

    def verify(self) -> subprocess.CompletedProcess[str]:
        return self.run(
            "verify-release.sh",
            REQUIRE_MIN_OTA_PLATFORMS="3",
            REQUIRED_OTA_PLATFORM_KEYS=_ALL_PLATFORMS,
            REQUIRED_INSTALLER_GLOBS="*aarch64*.dmg *.msi",
            REQUIRE_BARE_LINUX_APPIMAGE="1",
        )

    def manifest(self) -> _Manifest:
        return cast("_Manifest", json.loads((self.assets / "latest.json").read_text()))


@pytest.fixture
def release(tmp_path: Path) -> Release:
    return Release(tmp_path)


def test_finalize_lists_every_platform_of_the_real_release_layout(release: Release) -> None:
    done = release.finalize()

    assert done.returncode == 0, done.stderr
    platforms = release.manifest()["platforms"]
    assert set(platforms) == set(_ALL_PLATFORMS.split())
    linux = platforms["linux-x86_64"]
    assert linux["url"].endswith(f"/releases/download/{_TAG}/MyrmAgent_0.1.40_amd64.AppImage")
    assert linux["signature"] == "signature of MyrmAgent_0.1.40_amd64.AppImage"
    # Every installer and updater bundle gets a checksum; signatures and the manifest do not.
    assert {path.name for path in release.assets.glob("*.sha256")} == {f"{name}.sha256" for name in _SIGNED + _UNSIGNED}


def test_a_tag_without_the_v_prefix_names_the_same_release(release: Release) -> None:
    assert release.finalize(" 0.1.40 ").returncode == 0
    assert release.manifest()["version"] == "0.1.40"


def test_verify_accepts_what_finalize_wrote(release: Release) -> None:
    assert release.finalize().returncode == 0

    verified = release.verify()

    assert verified.returncode == 0, verified.stderr
    assert _ANNOTATION not in verified.stdout


def test_an_unknown_release_fails_with_the_reason(release: Release) -> None:
    done = release.finalize("v9.9.9")

    assert done.returncode == 1
    annotations = [line for line in done.stdout.splitlines() if line.startswith(_ANNOTATION)]
    assert len(annotations) == 1
    assert "cannot read release v9.9.9" in annotations[0]
    assert "release not found" in annotations[0]
    assert not (release.assets / "latest.json").exists()


def test_a_malformed_tag_fails_before_any_release_call(release: Release) -> None:
    done = release.finalize("latest")

    assert done.returncode == 1
    assert "Release tag must look like v1.2.3, got 'latest'" in done.stdout
    assert not release.calls_log.exists()


def test_a_required_platform_without_a_signature_names_the_platform(release: Release) -> None:
    (release.assets / "MyrmAgent_0.1.40_amd64.AppImage.sig").unlink()

    done = release.finalize()

    assert done.returncode == 1
    assert f"{_ANNOTATION}[finalize-release] required OTA platform linux-x86_64 missing .sig" in done.stdout
    assert not (release.assets / "latest.json").exists()


@pytest.mark.parametrize(
    ("failing_call", "what"),
    [
        ("release download", "downloading the assets of v0.1.40 failed"),
        ("api repos/", "cannot read the metadata of release v0.1.40"),
        ("release upload", "uploading the manifest and checksums to v0.1.40 failed"),
    ],
)
def test_a_failing_gh_call_names_its_step_and_carries_gh_own_words(release: Release, failing_call: str, what: str) -> None:
    done = release.run("finalize-release.sh", REQUIRED_OTA_PLATFORM_KEYS=_ALL_PLATFORMS, GH_FAIL=failing_call)

    assert done.returncode == 1
    assert f"{_ANNOTATION}[finalize-release] {what}: stand-in failure of {failing_call}" in done.stdout


def test_verify_names_the_manifest_it_could_not_fetch(release: Release) -> None:
    done = release.verify()

    assert done.returncode == 1
    manifest_url = f"https://github.com/{_REPO}/releases/download/{_TAG}/latest.json"
    assert f"{_ANNOTATION}[verify-release] cannot fetch {manifest_url}: curl: (22)" in done.stdout


def test_verify_names_every_platform_the_manifest_lacks(release: Release) -> None:
    (release.assets / "latest.json").write_text(json.dumps({"version": "0.1.40", "platforms": {"darwin-aarch64": {}}}))

    done = release.verify()

    assert done.returncode == 1
    assert f"{_ANNOTATION}[verify-release] latest.json has 1 OTA platform(s), require >= 3" in done.stdout


def test_outside_github_actions_errors_stay_plain_log_lines(release: Release) -> None:
    done = release.run("finalize-release.sh", "latest", GITHUB_ACTIONS="")

    assert done.returncode == 1
    assert "Release tag must look like v1.2.3" in done.stderr
    assert "::error" not in done.stdout
