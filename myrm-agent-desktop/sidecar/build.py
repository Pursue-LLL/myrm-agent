#!/usr/bin/env python3
"""Tauri Desktop Sidecar Builder

Builds the desktop sidecar binary for the Tauri desktop app:
- Python Backend: PyInstaller → standalone executable
"""

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
SERVER_ROOT = PROJECT_ROOT / "myrm-agent-server"
HARNESS_ROOT = Path(
    os.environ.get(
        "MYRM_HARNESS_ROOT",
        PROJECT_ROOT.parent / "myrm-agent-harness",
    )
)
OUTPUT_DIR = PROJECT_ROOT / "myrm-agent-desktop" / "src-tauri" / "binaries"

SYSTEM = platform.system().lower()
target_arch = os.environ.get("TARGET_ARCH", platform.machine().lower())

if SYSTEM == "darwin":
    if target_arch in ("arm64", "aarch64"):
        BINARY_NAME = "myrmagent-backend-aarch64-apple-darwin"
    else:
        BINARY_NAME = "myrmagent-backend-x86_64-apple-darwin"
elif SYSTEM == "linux":
    BINARY_NAME = "myrmagent-backend-x86_64-unknown-linux-gnu"
elif SYSTEM == "windows":
    BINARY_NAME = "myrmagent-backend-x86_64-pc-windows-msvc.exe"
else:
    raise RuntimeError(f"Unsupported platform: {SYSTEM}")


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


def _install_harness_from_source_build() -> None:
    """Build production wheels from a local harness clone (MYRM_HARNESS_INSTALL_MODE=source)."""
    if not HARNESS_ROOT.is_dir():
        raise FileNotFoundError(
            f"Harness source not found at {HARNESS_ROOT}. "
            "Set MYRM_HARNESS_ROOT or use default PyPI install (MYRM_HARNESS_INSTALL_MODE=pypi)."
        )

    print("\nBuilding harness production wheels from local clone (source mode)...")
    subprocess.run(
        ["uv", "sync", "--group", "build"],
        cwd=HARNESS_ROOT,
        check=True,
    )
    venv_python = HARNESS_ROOT / ".venv" / "bin" / "python"
    if not venv_python.exists():
        venv_python = HARNESS_ROOT / ".venv" / "Scripts" / "python.exe"
    subprocess.run(
        [
            str(venv_python),
            "scripts/assemble_production.py",
            "--install",
            str(SERVER_ROOT),
        ],
        cwd=HARNESS_ROOT,
        check=True,
    )


def _resolve_harness_install_mode() -> str:
    """Mirror maintainer install_harness.sh auto resolution for local monorepo builds."""
    explicit = os.environ.get("MYRM_HARNESS_INSTALL_MODE", "auto")
    if explicit != "auto":
        return explicit
    if HARNESS_ROOT.is_dir():
        return "source"
    return "pypi"


def _install_editable_harness() -> None:
    """Install editable harness from local clone (monorepo maintainer path)."""
    if not HARNESS_ROOT.is_dir():
        raise FileNotFoundError(
            f"Harness source not found at {HARNESS_ROOT}. "
            "Set MYRM_HARNESS_ROOT or run ./myrm harness install first."
        )

    print("\nInstalling editable harness from local clone...")
    subprocess.run(
        [
            "uv",
            "sync",
            "--frozen",
            "--no-install-package",
            "myrm-agent-harness",
            "--no-sources-package",
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
    subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "-e",
            f"{HARNESS_ROOT}[file-parsers,web,fastapi,retrieval,qdrant,image-processing,browser,computer-use]",
        ],
        cwd=SERVER_ROOT,
        check=True,
    )


def ensure_production_harness_wheels() -> None:
    """Install harness into the server venv before PyInstaller bundling."""
    install_mode = _resolve_harness_install_mode()
    if install_mode == "source":
        _install_harness_from_source_build()
        return
    if install_mode == "editable":
        _install_editable_harness()
        return

    print("\nInstalling server + harness from PyPI (desktop production venv)...")
    sync_args = [
        "uv",
        "sync",
        "--frozen",
        "--all-extras",
        "--no-group",
        "dev",
        "--no-extra",
        "matrix-e2ee",
        "--no-extra",
        "voice-tts",
        "--no-extra",
        "wechat-silk",
    ]
    subprocess.run(sync_args, cwd=SERVER_ROOT, check=True)


def _server_python() -> Path:
    venv_python = SERVER_ROOT / ".venv" / "bin" / "python"
    if not venv_python.exists():
        venv_python = SERVER_ROOT / ".venv" / "Scripts" / "python.exe"
    if not venv_python.exists():
        raise FileNotFoundError(
            f"Server venv not found under {SERVER_ROOT / '.venv'}. Run: cd myrm-agent-server && uv sync"
        )
    return venv_python


def build_backend(*, skip_harness_install: bool = False):
    """Build Python backend into standalone binary via PyInstaller."""
    print("\n" + "=" * 60)
    print("Building Python Backend Sidecar")
    print("=" * 60)

    if not skip_harness_install:
        ensure_production_harness_wheels()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    main_script = SERVER_ROOT / "app" / "main.py"

    if not main_script.exists():
        raise FileNotFoundError(f"Main script not found: {main_script}")

    server_python = _server_python()
    shared_json = PROJECT_ROOT / "shared" / "config" / "provider_legacy_remap.json"
    if not shared_json.is_file():
        raise FileNotFoundError(f"Missing cross-end provider remap artifact: {shared_json}")

    cmd = [
        str(server_python),
        "-m",
        "PyInstaller",
        str(main_script),
        "--name", BINARY_NAME.replace(".exe", ""),
        "--onefile",
        "--clean",
        "--noconfirm",
        "--hidden-import", "uvicorn",
        "--hidden-import", "fastapi",
        "--hidden-import", "sqlalchemy",
        "--hidden-import", "qdrant_client",
        "--hidden-import", "myrm_agent_harness",
        "--hidden-import", "myrm_agent_harness.api",
        "--exclude-module", "matplotlib",
        "--exclude-module", "tkinter",
        "--exclude-module", "PyQt5",
        "--distpath", str(OUTPUT_DIR),
        "--workpath", str(OUTPUT_DIR / "build"),
        "--specpath", str(OUTPUT_DIR),
    ]
    if SYSTEM == "windows":
        cmd.append("--noconsole")
    data_sep = ";" if SYSTEM == "windows" else ":"
    cmd.extend(["--add-data", f"{shared_json}{data_sep}shared/config"])

    print("\nRunning PyInstaller...")
    print(f"Command: {' '.join(cmd)}\n")

    result = subprocess.run(cmd, capture_output=False, cwd=SERVER_ROOT)

    if result.returncode != 0:
        print(f"\n[ERROR] Build failed with exit code {result.returncode}")
        sys.exit(1)

    output_file = OUTPUT_DIR / BINARY_NAME
    if not output_file.exists():
        output_file_no_ext = OUTPUT_DIR / BINARY_NAME.replace(".exe", "")
        if output_file_no_ext.exists():
            if SYSTEM == "windows":
                shutil.move(str(output_file_no_ext), str(output_file))
            else:
                output_file = output_file_no_ext

    if output_file.exists():
        size_mb = output_file.stat().st_size / (1024 * 1024)
        print("\n[OK] Build successful!")
        print(f"Output: {output_file}")
        print(f"Size: {size_mb:.2f} MB")
        if SYSTEM != "windows":
            os.chmod(output_file, 0o755)
    else:
        print(f"\n[ERROR] Output file not found: {output_file}")
        sys.exit(1)

    build_dir = OUTPUT_DIR / "build"
    spec_file = OUTPUT_DIR / f"{BINARY_NAME.replace('.exe', '')}.spec"
    if build_dir.exists():
        shutil.rmtree(build_dir)
    if spec_file.exists():
        spec_file.unlink()
    print("[OK] Cleanup complete")


def main():
    print("MyrmAgent - Sidecar Builder")
    print(f"Platform: {SYSTEM}")
    print(f"Harness install mode: {_resolve_harness_install_mode()}")
    print(f"Backend binary: {BINARY_NAME}\n")

    ensure_production_harness_wheels()
    check_pyinstaller()
    build_backend(skip_harness_install=True)

    print("\n" + "=" * 60)
    print("[OK] Sidecar build complete!")
    print("=" * 60)
    print(f"\nBackend: {OUTPUT_DIR / BINARY_NAME}")
    print("\nNext: cd myrm-agent-desktop && cargo tauri build")


if __name__ == "__main__":
    main()
