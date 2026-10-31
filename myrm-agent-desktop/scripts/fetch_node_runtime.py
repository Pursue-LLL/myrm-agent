"""Fetch the pinned Node.js runtime from nodejs.org, verified against a pinned SHA-256.

Two consumers share this one pin:

- The desktop shell starts its bundled Next.js server with it. The release bundle declares it as a Tauri
  `externalBin` (`binaries/myrm-node`); while it compiles the shell, Tauri expects
  `src-tauri/binaries/myrm-node-<rust target triple>[.exe]` and later places that file next to the app executable.
- The frontend dev server (`myrm-agent-frontend/scripts/node-runtime.ts`) fetches it into `--output-dir` as `node`
  on a machine that has no usable Node.js, so a self-hosted install runs Next on the same Node.js bytes as the app.

The pinned SHA-256 in `node_runtime.json` keeps what runs identical to what was reviewed, and fetching keeps a
100 MB binary out of the repository. `MYRM_NODE_DIST_URL` points the download at a mirror of nodejs.org/dist; the
digest check makes the mirror untrusted.

Usage (from the repository root):

    python myrm-agent-desktop/scripts/fetch_node_runtime.py [--target <rust target triple>] [--name node]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

DESKTOP_ROOT = Path(__file__).resolve().parent.parent
PINS_FILE = Path(__file__).with_name("node_runtime.json")
OUTPUT_DIR = DESKTOP_ROOT / "src-tauri" / "binaries"
DIST_URL = "https://nodejs.org/dist"
DIST_URL_ENV = "MYRM_NODE_DIST_URL"

# Stem of the `bundle.externalBin` entry in tauri.conf.json and of the executable that
# src-tauri/src/runtime/node_runtime.rs launches; tests/architecture/test_desktop_node_runtime.py enforces both.
SIDECAR_NAME = "myrm-node"

DOWNLOAD_RETRIES = 3
DOWNLOAD_MAX_SEC = 900
VERSION_CHECK_TIMEOUT_SEC = 30


@dataclass(frozen=True)
class NodeDist:
    """Where the official archive of one Rust target triple lives and where `node` sits inside it."""

    platform: str  # nodejs.org platform-architecture tag, e.g. `darwin-arm64`
    extension: str  # archive format: `tar.gz` or `zip`
    member: str  # the node executable, relative to the archive's top-level `node-v<version>-<platform>/` folder


# One entry per target the release workflow ships; a new target needs an entry here and a pin in node_runtime.json.
DISTS: dict[str, NodeDist] = {
    "aarch64-apple-darwin": NodeDist("darwin-arm64", "tar.gz", "bin/node"),
    "x86_64-pc-windows-msvc": NodeDist("win-x64", "zip", "node.exe"),
    "x86_64-unknown-linux-gnu": NodeDist("linux-x64", "tar.gz", "bin/node"),
}


class FetchError(RuntimeError):
    """The runtime could not be fetched, or what was fetched does not match its pin."""


@dataclass(frozen=True)
class Pins:
    version: str
    sha256: dict[str, str]  # Rust target triple -> SHA-256 of the official archive


def load_pins(path: Path = PINS_FILE) -> Pins:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return Pins(
        version=str(raw["version"]),
        sha256={str(k): str(v) for k, v in raw["sha256"].items()},
    )


def parse_host_triple(rustc_verbose: str) -> str | None:
    """The `host:` line of `rustc -vV`."""
    for line in rustc_verbose.splitlines():
        if line.startswith("host:"):
            return line.removeprefix("host:").strip()
    return None


# (platform.system(), platform.machine()) of the machines a pinned runtime exists for -> its Rust target triple.
_PLATFORM_TRIPLES = {
    ("Darwin", "arm64"): "aarch64-apple-darwin",
    ("Windows", "AMD64"): "x86_64-pc-windows-msvc",
    ("Linux", "x86_64"): "x86_64-unknown-linux-gnu",
}


def platform_triple() -> str | None:
    """The target of the machine running this script, for hosts without a Rust toolchain; None if none is pinned."""
    return _PLATFORM_TRIPLES.get((platform.system(), platform.machine()))


def host_triple() -> str | None:
    """The triple Tauri names an externalBin after when no `--target` is given: the one `rustc` reports, else this machine's."""
    try:
        completed = subprocess.run(
            ["rustc", "-vV"], capture_output=True, text=True, check=True
        )
    except (OSError, subprocess.CalledProcessError):
        return platform_triple()
    return parse_host_triple(completed.stdout) or platform_triple()


def archive_name(version: str, dist: NodeDist) -> str:
    return f"node-v{version}-{dist.platform}.{dist.extension}"


def sidecar_file_name(target: str) -> str:
    """The name Tauri looks for: the sidecar stem, the target triple, and `.exe` on Windows."""
    return f"{SIDECAR_NAME}-{target}{'.exe' if 'windows' in target else ''}"


def installed_file_name(target: str, name: str | None) -> str:
    """`name` (plus `.exe` on Windows) when the caller picks one, else the name Tauri looks for."""
    if name is None:
        return sidecar_file_name(target)
    return f"{name}{'.exe' if 'windows' in target else ''}"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, destination: Path) -> None:
    """Fetch `url` with curl: it trusts the operating system's certificate store (a corporate proxy's root
    included, which Python builds without bundled certificates do not) and retries transient failures."""
    command = [
        "curl",
        "--fail",
        "--location",
        "--silent",
        "--show-error",
        "--retry",
        str(DOWNLOAD_RETRIES),
        "--retry-all-errors",
        "--max-time",
        str(DOWNLOAD_MAX_SEC),
        "--output",
        str(destination),
        url,
    ]
    try:
        subprocess.run(command, capture_output=True, text=True, check=True)
    except FileNotFoundError as exc:
        raise FetchError(
            "curl is required to download the Node.js runtime and was not found on PATH"
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise FetchError(
            f"download of {url} failed: {exc.stderr.strip() or exc}"
        ) from exc


def download_verified(url: str, expected_sha256: str, destination: Path) -> None:
    """Fetch `url` into `destination`; a body whose SHA-256 differs from the pin is never accepted."""
    download(url, destination)
    actual = sha256_of(destination)
    if actual != expected_sha256:
        raise FetchError(
            f"SHA-256 mismatch for {url}: pinned {expected_sha256}, got {actual}"
        )


def extract_executable(archive: Path, member: str, destination: Path) -> None:
    """Copy the single `member` out of `archive` to `destination`, atomically and executable."""
    partial = destination.with_name(f"{destination.name}.part")
    try:
        with partial.open("wb") as out:
            if archive.suffix == ".zip":
                with (
                    zipfile.ZipFile(archive) as zip_archive,
                    zip_archive.open(member) as source,
                ):
                    shutil.copyfileobj(source, out)
            else:
                with tarfile.open(archive) as tar_archive:
                    member_file = tar_archive.extractfile(member)
                    if member_file is None:
                        raise KeyError(member)
                    with member_file:
                        shutil.copyfileobj(member_file, out)
        partial.chmod(0o755)
        os.replace(partial, destination)
    except KeyError as exc:
        raise FetchError(f"{archive.name} does not contain {member}") from exc
    finally:
        partial.unlink(missing_ok=True)


def reports_version(executable: Path, version: str) -> bool:
    """Whether `executable --version` runs and names exactly the pinned version."""
    try:
        completed = subprocess.run(
            [str(executable), "--version"],
            capture_output=True,
            text=True,
            timeout=VERSION_CHECK_TIMEOUT_SEC,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0 and completed.stdout.strip() == f"v{version}"


def fetch(
    target: str,
    output_dir: Path,
    *,
    pins: Pins,
    base_url: str = DIST_URL,
    run_check: bool,
    name: str | None = None,
) -> Path:
    """Place the pinned runtime for `target` into `output_dir` and return its path.

    `run_check` executes the result and compares its version with the pin; it only makes sense when
    `target` is the machine's own platform. The same check lets a repeated call return early.
    `name` replaces Tauri's `myrm-node-<target>` file name.
    """
    dist = DISTS.get(target)
    if dist is None:
        raise FetchError(
            f"no Node.js runtime is pinned for target {target}; supported: {', '.join(sorted(DISTS))}"
        )
    expected = pins.sha256.get(target)
    if expected is None:
        raise FetchError(f"node_runtime.json has no SHA-256 for target {target}")

    destination = output_dir / installed_file_name(target, name)
    if run_check and reports_version(destination, pins.version):
        print(f"[node-runtime] {destination} is already Node.js v{pins.version}")
        return destination

    output_dir.mkdir(parents=True, exist_ok=True)
    archive = archive_name(pins.version, dist)
    url = f"{base_url}/v{pins.version}/{archive}"
    with tempfile.TemporaryDirectory() as workdir:
        downloaded = Path(workdir) / archive
        print(f"[node-runtime] downloading {url}")
        download_verified(url, expected, downloaded)
        extract_executable(
            downloaded,
            f"node-v{pins.version}-{dist.platform}/{dist.member}",
            destination,
        )

    if run_check and not reports_version(destination, pins.version):
        destination.unlink(missing_ok=True)
        raise FetchError(
            f"{archive} verified, but its node does not report v{pins.version} when run on this machine"
        )
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--target",
        help="Rust target triple the shell is built for (default: the `rustc` host, else this machine)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help="where Tauri looks for externalBin files",
    )
    parser.add_argument(
        "--name",
        help="install the executable under this file name instead of `myrm-node-<target>`",
    )
    args = parser.parse_args(argv)

    host = host_triple()
    target = args.target or host
    base_url = os.environ.get(DIST_URL_ENV, "").strip().rstrip("/") or DIST_URL
    try:
        if target is None:
            raise FetchError(
                f"no Node.js runtime is pinned for this machine ({platform.system()} {platform.machine()}); "
                f"supported: {', '.join(sorted(DISTS))}. Install Node.js from https://nodejs.org, or pass --target"
            )
        path = fetch(
            target,
            args.output_dir,
            pins=load_pins(),
            base_url=base_url,
            run_check=target == host,
            name=args.name,
        )
    except FetchError as exc:
        print(f"[node-runtime] FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"[node-runtime] ready: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
