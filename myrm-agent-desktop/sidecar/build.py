"""Tauri Desktop Sidecar Builder

Builds the desktop sidecar for the Tauri desktop app:
- Python Backend: PyInstaller one-folder build -> src-tauri/binaries/myrmagent-backend/

One-folder on purpose: a one-file executable unpacks its whole payload (hundreds of MB) into a temp
directory on every launch, which dominates cold-start time. The folder is shipped as a Tauri resource,
so the unpacking happens once, at install time.
"""

import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath

PROJECT_ROOT = Path(__file__).parent.parent.parent
SERVER_ROOT = PROJECT_ROOT / "myrm-agent-server"
HARNESS_ROOT = PROJECT_ROOT / "myrm-agent-harness"
OUTPUT_DIR = PROJECT_ROOT / "myrm-agent-desktop" / "src-tauri" / "binaries"
SHARED_PROVIDER_REMAP = PROJECT_ROOT / "shared" / "config" / "provider_legacy_remap.json"
STDIO_RUNTIME_HOOK = Path(__file__).parent / "stdio_runtime_hook.py"

# Server data that code opens by a path relative to its own module (`Path(__file__)...`), as paths under the server
# root. PyInstaller archives Python only, so each entry is a build input of its own, and a forgotten one breaks
# nothing at build or start: the endpoint that reads it answers with an empty list. The bundle mirrors the source
# layout, because that is where the code looks: a directory keeps its path, a file goes into its parent.
# tests/architecture/test_desktop_sidecar_data.py fails when a data file is neither listed here nor accounted for below.
SERVER_DATA = (
    "app/config/subagents",
    "app/channels/i18n/locales",
    "app/core/eval/fixtures",
    "app/core/integrations/catalog/data",
    "app/core/integrations/search_catalog/manifest.json",
    "assets",
)

# Server data left out of the bundle on purpose, with the reason.
SERVER_DATA_NOT_SHIPPED = {
    "app/channels/providers/whatsapp/bridge": (
        "the bridge runs `npm install` inside its own directory and starts the Node.js found on PATH; an installed "
        "app has neither a writable directory there nor a Node.js on a launcher's PATH"
    ),
}

SYSTEM = platform.system().lower()
if SYSTEM not in ("darwin", "linux", "windows"):
    raise RuntimeError(f"Unsupported platform: {SYSTEM}")

# Folder name and entry-executable stem. Must match tauri.conf.json (bundle.resources) and
# src-tauri/src/runtime/sidecar_path.rs; tests/architecture/test_desktop_sidecar_layout.py enforces it.
SIDECAR_NAME = "myrmagent-backend"
SIDECAR_DIR = OUTPUT_DIR / SIDECAR_NAME
SIDECAR_EXECUTABLE = SIDECAR_DIR / (f"{SIDECAR_NAME}.exe" if SYSTEM == "windows" else SIDECAR_NAME)

TARGET_ARCH = os.environ.get("TARGET_ARCH", platform.machine().lower())


def check_pyinstaller() -> None:
    """Ensure PyInstaller is available in the server venv."""
    server_python = _server_python()
    try:
        subprocess.run(
            [str(server_python), "-m", "PyInstaller", "--version"],
            check=True,
            capture_output=True,
        )
        print("[OK] PyInstaller is installed in server venv")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("PyInstaller not found in server venv, installing via uv pip...")
        subprocess.run(
            ["uv", "pip", "install", "pyinstaller"],
            cwd=SERVER_ROOT,
            check=True,
        )


def ensure_production_harness_wheels() -> None:
    """Sync the server venv from uv.lock, then install the in-repo harness as a wheel.

    uv.lock resolves the harness as an editable path source; the bundle ships a built wheel
    instead, so every harness dependency still comes from the lock.
    """
    print("\nInstalling server dependencies + in-repo harness wheel (desktop production venv)...")
    subprocess.run(
        [
            "uv",
            "sync",
            "--frozen",
            "--no-install-package",
            "myrm-agent-harness",
            "--all-extras",
            "--no-group",
            "dev",
            "--no-extra",
            "matrix-e2ee",
            "--no-extra",
            "voice-tts",
            "--no-extra",
            "wechat-silk",
        ],
        cwd=SERVER_ROOT,
        check=True,
    )
    with tempfile.TemporaryDirectory() as wheel_dir:
        subprocess.run(
            ["uv", "build", "--wheel", "-o", wheel_dir],
            cwd=HARNESS_ROOT,
            check=True,
        )
        wheel = next(Path(wheel_dir).glob("myrm_agent_harness-*.whl"))
        subprocess.run(
            ["uv", "pip", "install", "--no-deps", str(wheel)],
            cwd=SERVER_ROOT,
            check=True,
        )


def _server_python() -> Path:
    venv_python = SERVER_ROOT / ".venv" / "bin" / "python"
    if not venv_python.exists():
        venv_python = SERVER_ROOT / ".venv" / "Scripts" / "python.exe"
    if not venv_python.exists():
        raise FileNotFoundError(
            f"Server venv not found under {SERVER_ROOT / '.venv'}. Run: cd myrm-agent-server && uv sync"
        )
    return venv_python


def _server_data_options(data_sep: str) -> list[str]:
    """`--add-data` options that place every SERVER_DATA entry at its own relative path inside the bundle."""
    options: list[str] = []
    for relative in SERVER_DATA:
        source = SERVER_ROOT / relative
        destination = relative if source.is_dir() else str(PurePosixPath(relative).parent)
        options += ["--add-data", f"{source}{data_sep}{destination}"]
    return options


def pyinstaller_command(server_python: Path, work_dir: Path) -> list[str]:
    """PyInstaller invocation that writes the one-folder bundle to SIDECAR_DIR."""
    data_sep = ";" if SYSTEM == "windows" else ":"
    cmd = [
        str(server_python),
        "-m",
        "PyInstaller",
        str(SERVER_ROOT / "app" / "main.py"),
        "--name", SIDECAR_NAME,
        "--onedir",
        "--clean",
        "--noconfirm",
        "--hidden-import", "uvicorn",
        "--hidden-import", "fastapi",
        "--hidden-import", "sqlalchemy",
        "--hidden-import", "qdrant_client",
        "--hidden-import", "myrm_agent_harness",
        "--hidden-import", "myrm_agent_harness.api",
        "--collect-data", "litellm",
        "--collect-data", "tiktoken",
        "--collect-submodules", "tiktoken",
        "--collect-submodules", "tiktoken_ext",
        "--hidden-import", "tiktoken_ext.openai_public",
        "--collect-data", "myrm_agent_harness",
        "--collect-submodules", "myrm_agent_harness",
        *_server_data_options(data_sep),
        "--add-data", f"{SHARED_PROVIDER_REMAP}{data_sep}shared/config",
        "--exclude-module", "matplotlib",
        "--exclude-module", "tkinter",
        "--exclude-module", "PyQt5",
        "--runtime-hook", str(STDIO_RUNTIME_HOOK),
        "--distpath", str(OUTPUT_DIR),
        "--workpath", str(work_dir / "build"),
        "--specpath", str(work_dir),
    ]
    if SYSTEM == "windows":
        cmd.append("--noconsole")
    return cmd


def _assert_macos_architecture(executable: Path) -> None:
    """PyInstaller cannot cross-compile: the bundle takes the architecture of the build Python."""
    expected = "arm64" if TARGET_ARCH in ("arm64", "aarch64") else "x86_64"
    archs = subprocess.run(
        ["lipo", "-archs", str(executable)], check=True, capture_output=True, text=True
    ).stdout.split()
    if archs != [expected]:
        raise RuntimeError(
            f"Sidecar architecture {archs} does not match TARGET_ARCH={expected}. "
            "Build it with a Python interpreter of the target architecture."
        )


def build_backend(*, skip_harness_install: bool = False) -> None:
    """Build the Python backend into the one-folder sidecar bundle via PyInstaller."""
    print("\n" + "=" * 60)
    print("Building Python Backend Sidecar")
    print("=" * 60)

    if not skip_harness_install:
        ensure_production_harness_wheels()

    main_script = SERVER_ROOT / "app" / "main.py"
    if not main_script.exists():
        raise FileNotFoundError(f"Main script not found: {main_script}")
    if not SHARED_PROVIDER_REMAP.is_file():
        raise FileNotFoundError(f"Missing cross-end provider remap artifact: {SHARED_PROVIDER_REMAP}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # Start from nothing at the target path (directory, file or symlink) so no file of an earlier build survives.
    if SIDECAR_DIR.is_dir() and not SIDECAR_DIR.is_symlink():
        shutil.rmtree(SIDECAR_DIR)
    else:
        SIDECAR_DIR.unlink(missing_ok=True)

    # Work files stay outside OUTPUT_DIR: everything under it is shipped or ignored by git, never scratch.
    with tempfile.TemporaryDirectory(prefix="myrm-sidecar-build-") as work_dir:
        cmd = pyinstaller_command(_server_python(), Path(work_dir))
        print("\nRunning PyInstaller...")
        print(f"Command: {' '.join(cmd)}\n")
        result = subprocess.run(cmd, cwd=SERVER_ROOT, check=False)

    if result.returncode != 0:
        print(f"\n[ERROR] Build failed with exit code {result.returncode}")
        sys.exit(1)
    if not SIDECAR_EXECUTABLE.is_file():
        print(f"\n[ERROR] Output executable not found: {SIDECAR_EXECUTABLE}")
        sys.exit(1)

    if SYSTEM != "windows":
        os.chmod(SIDECAR_EXECUTABLE, 0o755)  # noqa: S103 - the entry point must be executable for every user of the install
    if SYSTEM == "darwin":
        _assert_macos_architecture(SIDECAR_EXECUTABLE)

    size_mb = sum(f.stat().st_size for f in SIDECAR_DIR.rglob("*") if f.is_file()) / (1024 * 1024)
    print("\n[OK] Build successful!")
    print(f"Output: {SIDECAR_DIR}")
    print(f"Size: {size_mb:.2f} MB")


def main() -> None:
    print("MyrmAgent - Sidecar Builder")
    print(f"Platform: {SYSTEM} ({TARGET_ARCH})\n")

    ensure_production_harness_wheels()
    check_pyinstaller()
    build_backend(skip_harness_install=True)

    print("\n" + "=" * 60)
    print("[OK] Sidecar build complete!")
    print("=" * 60)
    print(f"\nBackend: {SIDECAR_DIR}")
    print("\nNext: cd myrm-agent-desktop && python scripts/fetch_node_runtime.py && cargo tauri build")


if __name__ == "__main__":
    main()
