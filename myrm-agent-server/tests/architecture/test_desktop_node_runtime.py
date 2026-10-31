"""Contract and behaviour of the Node.js runtime the desktop bundle ships.

The shell starts its bundled Next.js server with a Node.js it carries itself: a machine launching the app from
Finder or the Start menu has no Node.js on PATH. The runtime is a Tauri `externalBin` that
`scripts/fetch_node_runtime.py` downloads from nodejs.org against a pinned SHA-256. The Tauri config, the fetch
script, its pins, the Rust resolver, the release workflow and the macOS entitlements must agree; this test pins them
together so a one-sided change fails here instead of in a release build, and runs the fetch script against offline
archives.
"""

from __future__ import annotations

import io
import json
import plistlib
import re
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path
from types import ModuleType
from typing import cast

import pytest

from tests.support.desktop_release import (
    DESKTOP,
    REPO_ROOT,
    Platform,
    YamlMapping,
    bundle_config,
    expanded_release_steps,
    fetch_node_runtime_module,
    release_jobs,
)

_BUILD_JOBS = ("build-macos-arm", "build-windows", "build-linux")
# The target a hosted runner's `rustc` compiles for when the job passes no `--target` to Tauri.
_RUNNER_HOST_TRIPLE = {"windows": "x86_64-pc-windows-msvc", "ubuntu": "x86_64-unknown-linux-gnu"}
_PIN_VERSION = "1.2.3"
_POSIX_ONLY = pytest.mark.skipif(sys.platform == "win32", reason="the stand-in node is a shell script")
_NEEDS_CURL = pytest.mark.skipif(shutil.which("curl") is None, reason="curl is the download transport")


@pytest.fixture(scope="module")
def fetch() -> ModuleType:
    return fetch_node_runtime_module()


def _target_flag(text: str) -> str | None:
    match = re.search(r"--target\s+(\S+)", text)
    return match.group(1) if match else None


def _tauri_step(job_id: str) -> YamlMapping:
    return next(
        step for step in expanded_release_steps(job_id) if str(step.get("uses", "")).startswith("tauri-apps/tauri-action")
    )


def _fetch_step(job_id: str) -> YamlMapping | None:
    return next((step for step in expanded_release_steps(job_id) if "fetch_node_runtime.py" in str(step.get("run", ""))), None)


def _bundle_target(job_id: str) -> str:
    """The Rust target Tauri compiles the job's shell for."""
    args = str(cast("YamlMapping", _tauri_step(job_id)["with"]).get("args", ""))
    return _target_flag(args) or _RUNNER_HOST_TRIPLE[str(release_jobs()[job_id]["runs-on"]).split("-")[0]]


@pytest.mark.parametrize("platform", ["macos", "windows", "linux"])
def test_tauri_ships_the_runtime_as_an_external_binary_on_every_platform(fetch: ModuleType, platform: Platform) -> None:
    assert bundle_config(platform)["externalBin"] == [f"binaries/{fetch.SIDECAR_NAME}"]


def test_the_rust_resolver_launches_the_file_tauri_places(fetch: ModuleType) -> None:
    source = (DESKTOP / "src-tauri/src/runtime/node_runtime.rs").read_text(encoding="utf-8")

    # Tauri strips the target triple from an externalBin it copies next to the app and keeps `.exe` on Windows.
    assert f'"{fetch.SIDECAR_NAME}.exe"' in source
    assert f'"{fetch.SIDECAR_NAME}"' in source


def test_the_fetched_file_is_named_the_way_tauri_looks_for_it(fetch: ModuleType) -> None:
    assert fetch.sidecar_file_name("aarch64-apple-darwin") == "myrm-node-aarch64-apple-darwin"
    assert fetch.sidecar_file_name("x86_64-pc-windows-msvc") == "myrm-node-x86_64-pc-windows-msvc.exe"
    assert fetch.sidecar_file_name("x86_64-unknown-linux-gnu") == "myrm-node-x86_64-unknown-linux-gnu"


def test_pins_cover_exactly_the_downloadable_targets(fetch: ModuleType) -> None:
    pins = fetch.load_pins()

    assert set(pins.sha256) == set(fetch.DISTS)
    assert all(re.fullmatch(r"[0-9a-f]{64}", digest) for digest in pins.sha256.values())
    assert re.fullmatch(r"\d+\.\d+\.\d+", pins.version)


@pytest.mark.parametrize("job_id", _BUILD_JOBS)
def test_every_platform_job_fetches_the_runtime_for_its_own_target_before_bundling(fetch: ModuleType, job_id: str) -> None:
    fetch_step = _fetch_step(job_id)
    assert fetch_step is not None, f"{job_id} never fetches the Node.js runtime"
    steps = expanded_release_steps(job_id)

    assert steps.index(fetch_step) < steps.index(_tauri_step(job_id)), "the runtime must exist before Tauri compiles the shell"
    assert _target_flag(str(fetch_step["run"])) == _bundle_target(job_id)
    assert _bundle_target(job_id) in fetch.DISTS


def test_the_cargo_gate_compiles_without_the_runtime() -> None:
    script = (DESKTOP / "scripts/ci/cargo-check.sh").read_text(encoding="utf-8")
    override = re.search(r"TAURI_CONFIG='(\{.*\})'", script)
    assert override is not None, "cargo-check.sh no longer overrides the Tauri config"

    bundle = json.loads(override.group(1))["bundle"]
    # tauri-build fails when a declared resource or external binary is missing, even for `cargo check`.
    assert bundle["resources"] == []
    assert bundle["externalBin"] == []


def test_the_entitlements_give_the_bundled_node_the_memory_v8_needs() -> None:
    """Tauri re-signs an `externalBin` with the app's identity and entitlements, replacing Node's own signature.

    A hardened-runtime Node without these two keys dies at start-up ("Failed to reserve virtual memory for
    CodeRange"), and the unsigned CI builds never apply the hardened runtime, so only this check sees it.
    """
    macos = cast("dict[str, object]", bundle_config("macos")["macOS"])
    entitlements = plistlib.loads((DESKTOP / "src-tauri" / str(macos["entitlements"])).read_bytes())

    for key in ("com.apple.security.cs.allow-jit", "com.apple.security.cs.allow-unsigned-executable-memory"):
        assert entitlements.get(key) is True, f"{key} is missing from the macOS entitlements"


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
def test_the_fetched_file_is_not_committed(fetch: ModuleType) -> None:
    fetched = DESKTOP / "src-tauri/binaries" / fetch.sidecar_file_name("aarch64-apple-darwin")

    ignored = subprocess.run(["git", "check-ignore", "-q", str(fetched)], cwd=REPO_ROOT, check=False)

    assert ignored.returncode == 0, f"{fetched} would be committed"


def _write_archive(path: Path, extension: str, member: str, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if extension == "zip":
        with zipfile.ZipFile(path, "w") as zip_archive:
            zip_archive.writestr(member, body)
        return
    with tarfile.open(path, "w:gz") as tar_archive:
        info = tarfile.TarInfo(member)
        info.size = len(body)
        info.mode = 0o755
        tar_archive.addfile(info, io.BytesIO(body))


def _publish(
    fetch: ModuleType, mirror: Path, target: str, body: bytes, *, version: str = _PIN_VERSION, member: str | None = None
) -> str:
    """Lay an archive for `target` out the way nodejs.org does under `mirror`; returns its SHA-256."""
    dist = fetch.DISTS[target]
    archive = mirror / f"v{version}" / fetch.archive_name(version, dist)
    _write_archive(archive, dist.extension, member or f"node-v{version}-{dist.platform}/{dist.member}", body)
    return str(fetch.sha256_of(archive))


def _fetch_from(fetch: ModuleType, mirror: Path, target: str, digest: str, out: Path, *, run_check: bool) -> Path:
    pins = fetch.Pins(version=_PIN_VERSION, sha256={target: digest})
    return cast("Path", fetch.fetch(target, out, pins=pins, base_url=mirror.as_uri(), run_check=run_check))


def _stand_in_node(version: str) -> bytes:
    return f"#!/bin/sh\necho v{version}\n".encode()


@_NEEDS_CURL
@_POSIX_ONLY
class TestFetchOnThisMachine:
    target = "x86_64-unknown-linux-gnu"

    def test_places_the_verified_runtime_where_tauri_expects_it(self, fetch: ModuleType, tmp_path: Path) -> None:
        digest = _publish(fetch, tmp_path / "mirror", self.target, _stand_in_node(_PIN_VERSION))

        path = _fetch_from(fetch, tmp_path / "mirror", self.target, digest, tmp_path / "out", run_check=True)

        assert path == tmp_path / "out" / "myrm-node-x86_64-unknown-linux-gnu"
        assert (
            subprocess.run([str(path), "--version"], capture_output=True, text=True, check=True).stdout.strip()
            == f"v{_PIN_VERSION}"
        )
        assert [entry.name for entry in path.parent.iterdir()] == [path.name], "no partial file may remain"

    def test_a_repeated_call_downloads_nothing(self, fetch: ModuleType, tmp_path: Path) -> None:
        digest = _publish(fetch, tmp_path / "mirror", self.target, _stand_in_node(_PIN_VERSION))
        first = _fetch_from(fetch, tmp_path / "mirror", self.target, digest, tmp_path / "out", run_check=True)

        again = _fetch_from(fetch, tmp_path / "gone", self.target, digest, tmp_path / "out", run_check=True)

        assert again == first

    def test_a_runtime_reporting_another_version_is_not_kept(self, fetch: ModuleType, tmp_path: Path) -> None:
        digest = _publish(fetch, tmp_path / "mirror", self.target, _stand_in_node("9.9.9"))

        with pytest.raises(fetch.FetchError, match=f"does not report v{_PIN_VERSION}"):
            _fetch_from(fetch, tmp_path / "mirror", self.target, digest, tmp_path / "out", run_check=True)

        assert not any((tmp_path / "out").iterdir())


@_NEEDS_CURL
class TestFetchRefusesWhatItCannotVouchFor:
    target = "x86_64-unknown-linux-gnu"

    def test_a_body_that_differs_from_the_pin_is_rejected(self, fetch: ModuleType, tmp_path: Path) -> None:
        _publish(fetch, tmp_path / "mirror", self.target, b"tampered")

        with pytest.raises(fetch.FetchError, match="SHA-256 mismatch"):
            _fetch_from(fetch, tmp_path / "mirror", self.target, "0" * 64, tmp_path / "out", run_check=False)

        assert not any((tmp_path / "out").iterdir())

    def test_an_archive_without_the_executable_is_reported(self, fetch: ModuleType, tmp_path: Path) -> None:
        digest = _publish(fetch, tmp_path / "mirror", self.target, b"x", member="node-v1.2.3-linux-x64/README.md")

        with pytest.raises(fetch.FetchError, match=r"does not contain node-v1\.2\.3-linux-x64/bin/node"):
            _fetch_from(fetch, tmp_path / "mirror", self.target, digest, tmp_path / "out", run_check=False)

        assert not any((tmp_path / "out").iterdir())

    def test_a_download_that_fails_names_the_address(
        self, fetch: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(fetch, "DOWNLOAD_RETRIES", 0)  # a missing file would otherwise be retried with back-off
        with pytest.raises(fetch.FetchError, match=r"download of file://\S*node-v1\.2\.3-linux-x64\.tar\.gz failed"):
            _fetch_from(fetch, tmp_path / "gone", self.target, "0" * 64, tmp_path / "out", run_check=False)


@_NEEDS_CURL
def test_a_windows_archive_yields_an_exe_named_for_its_target(fetch: ModuleType, tmp_path: Path) -> None:
    target = "x86_64-pc-windows-msvc"
    digest = _publish(fetch, tmp_path / "mirror", target, b"MZ stand-in")

    path = _fetch_from(fetch, tmp_path / "mirror", target, digest, tmp_path / "out", run_check=False)

    assert path.name == "myrm-node-x86_64-pc-windows-msvc.exe"
    assert path.read_bytes() == b"MZ stand-in"


def test_an_unsupported_target_lists_the_supported_ones(fetch: ModuleType, tmp_path: Path) -> None:
    expected = "no Node.js runtime is pinned for target x86_64-apple-darwin; supported: aarch64-apple-darwin"

    with pytest.raises(fetch.FetchError, match=expected):
        fetch.fetch("x86_64-apple-darwin", tmp_path, pins=fetch.load_pins(), run_check=False)


def test_a_target_without_a_pin_is_refused(fetch: ModuleType, tmp_path: Path) -> None:
    with pytest.raises(fetch.FetchError, match="has no SHA-256 for target aarch64-apple-darwin"):
        fetch.fetch("aarch64-apple-darwin", tmp_path, pins=fetch.Pins(version=_PIN_VERSION, sha256={}), run_check=False)


def test_a_missing_curl_is_a_clear_error(fetch: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def no_curl(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("curl")

    monkeypatch.setattr(fetch.subprocess, "run", no_curl)

    with pytest.raises(fetch.FetchError, match="curl is required"):
        fetch.download("https://example.invalid/node.tar.gz", tmp_path / "node.tar.gz")


def test_the_host_triple_is_the_rustc_host_line(fetch: ModuleType) -> None:
    verbose = "rustc 1.90.0 (abcdef 2026-01-01)\nbinary: rustc\nhost: aarch64-apple-darwin\nrelease: 1.90.0\n"

    assert fetch.parse_host_triple(verbose) == "aarch64-apple-darwin"
    assert fetch.parse_host_triple("no host here") is None


def test_the_command_line_reports_a_refusal_with_a_failing_exit_code(
    fetch: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert fetch.main(["--target", "x86_64-apple-darwin", "--output-dir", str(tmp_path)]) == 1

    assert "[node-runtime] FAIL: no Node.js runtime is pinned for target x86_64-apple-darwin" in capsys.readouterr().err
